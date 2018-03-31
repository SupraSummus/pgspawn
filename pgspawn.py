from collections import namedtuple
import logging
import os
import socket
import sys


logger = logging.getLogger(__name__)


def bimap_dict(key_f, val_f, d):
    return {
        key_f(k): val_f(v)
        for k, v in d.items()
    }


class GraphException(Exception):
    pass


class Node(namedtuple('Node', ('command', 'inputs', 'outputs', 'sockets'))):
    @classmethod
    def from_dict(cls, description):
        unknown_keys = description.keys() - set(cls._fields)
        if len(unknown_keys) > 0:
            logger.warning("Unknown keys in node description dict: {}".format(unknown_keys))

        return cls(
            command=[str(p) for p in description['command']],
            inputs=bimap_dict(int, str, description.get('inputs', {})),
            outputs=bimap_dict(int, str, description.get('outputs', {})),
            sockets=bimap_dict(int, str, description.get('sockets', {})),
        )
        return n


class Graph(namedtuple('Graph', ('inputs', 'outputs', 'sockets', 'nodes'))):
    @classmethod
    def from_dict(cls, description):
        unknown_keys = description.keys() - set(cls._fields)
        if len(unknown_keys) > 0:
            logger.warning("Unknown keys in graph description dict: {}".format(unknown_keys))

        g = cls(
            inputs=bimap_dict(str, int, description.get('inputs', {})),
            outputs=bimap_dict(str, int, description.get('outputs', {})),
            sockets=bimap_dict(str, int, description.get('sockets', {})),
            nodes=list(map(Node.from_dict, description.get('nodes', []))),
        )

        g.check_for_pipe_collisions()
        g.check_pipe_directions()
        g.check_for_fd_collisions()
        g.check_sockets()
        g.check_for_dead_ends()

        return g

    def check_for_pipe_collisions(self):
        colliding = self.inputs.keys() & self.outputs.keys()
        if len(colliding) > 0:
            raise GraphException("Some pipes specified as both global inputs and outputs: {}".format(colliding))

    def check_pipe_directions(self):
        for node_id, node in enumerate(self.nodes):
            for pipe_name in self.inputs.keys():
                if pipe_name in node.outputs.values():
                    raise GraphException(
                        "Pipe named '{}', definded as global input, "
                        "is used as output in node {}.".format(
                            pipe_name, node_id,
                        )
                    )
            for pipe_name in self.outputs.keys():
                if pipe_name in node.inputs.values():
                    raise GraphException(
                        "Pipe named '{}', definded as global output, "
                        "is used as input in node {}.".format(
                            pipe_name, node_id,
                        )
                    )

    def check_for_fd_collisions(self):
        for node_id, node in enumerate(self.nodes):
            colliding_fds = (
                (node.inputs.keys() & node.outputs.keys()) |
                (node.inputs.keys() & node.sockets.keys()) |
                (node.outputs.keys() & node.sockets.keys())
            )
            if len(colliding_fds) > 0:
                raise GraphException(
                    "Multiple pipes/sockets specified for single fd. "
                    "I'm sorry, I'm afraid I can't connect that. (node {}, fds {})".format(
                        node_id, colliding_fds,
                    )
                )

    def check_for_dead_ends(self):
        written_pipes = set(self.inputs.keys())
        read_pipes = set(self.outputs.keys())
        for node in self.nodes:
            written_pipes.update(node.outputs.values())
            read_pipes.update(node.inputs.values())
        only_written = written_pipes - read_pipes
        only_read = read_pipes - written_pipes
        if len(only_written) > 0:
            logger.warning("Some pipes are never read: {}".format(only_written))
        if len(only_read) > 0:
            logger.warning("Some pipes are never written: {}".format(only_read))

    def check_sockets(self):
        # dict socket_id -> number of uses
        socket_uses = {}
        for node_id, node in enumerate(self.nodes):
            for socket_id in node.sockets.values():
                n = socket_uses.get(socket_id, 0)
                n += 1
                if n > 2:
                    logger.warning(
                        "Socket name '{}' is used more than two times (node {})."
                        "I can take this. And you can easily make mistake.".format(
                            socket_id, node_id,
                        )
                    )
                socket_uses[socket_id] = n
        for socket_id, n in socket_uses.items():
            if n == 1:
                logger.warning(
                        "Socket name '{}' is used only one time."
                        "The other end will be flapping in the breeze (untill we close it).".format(
                            socket_id,
                        )
                    )


def apply_fd_mapping(fd_mapping):
    """ Takes dict target fd -> present fd. Moves fds to match the mapping. """

    def _dup_mapping(fd, new_fd):
        logger.debug("fd {} duped to {}".format(fd, new_fd))
        for target_fd in fd_mapping.keys():
            if fd_mapping[target_fd] == fd:
                fd_mapping[target_fd] = new_fd

    for target_fd in fd_mapping.keys():
        fd = fd_mapping[target_fd]

        if fd == target_fd:
            # nothing to do
            logger.debug("fd {} already in place".format(fd))
            continue

        # if needed make target fd free
        if target_fd in fd_mapping.values():
            saved_fd = os.dup(target_fd)
            _dup_mapping(target_fd, saved_fd)

        os.dup2(fd, target_fd, inheritable=False)
        _dup_mapping(fd, target_fd)


class PipeGraphSpawner:
    @classmethod
    def from_graph(cls, graph):
        spawner = cls(
            inputs=graph.inputs,
            outputs=graph.outputs,
        )
        for node in graph.nodes:
            spawner.spawn(node.command, node.inputs, node.outputs, node.sockets)
        return spawner

    def __init__(self, inputs={}, outputs={}, sockets={}):
        self._reading_ends = {}
        self._writing_ends = {}
        self._socket_other_ends = {}
        self._processes = set()

        def register_fds(our_dict, input_dict):
            for id, fd in input_dict.items():
                os.set_inheritable(fd, False)
                our_dict[id] = fd

        register_fds(self._writing_ends, outputs)
        register_fds(self._reading_ends, inputs)
        register_fds(self._socket_other_ends, sockets)

    def spawn(self, command, inputs, outputs, sockets):
        fd_mapping = {}
        fds_to_be_closed_in_parent = []
        for subprocess_fd, pipe_id in inputs.items():
            assert(subprocess_fd not in fd_mapping)
            fd_mapping[subprocess_fd] = self._reading_end_fd(pipe_id)
        for subprocess_fd, pipe_id in outputs.items():
            assert(subprocess_fd not in fd_mapping)
            fd_mapping[subprocess_fd] = self._writing_end_fd(pipe_id)
        for subprocess_fd, socket_id in sockets.items():
            assert(subprocess_fd not in fd_mapping)
            fd = self._get_and_clear_socket_end(socket_id)
            fd_mapping[subprocess_fd] = fd
            fds_to_be_closed_in_parent.append(fd)

        pid = os.fork()
        if pid == 0:
            apply_fd_mapping(fd_mapping)
            for fd in fd_mapping.keys():
                os.set_inheritable(fd, True)
            os.execvp(command[0], command)
        else:
            self._processes.add(pid)
            logger.info("node {} spawned command={} fd_mapping={}".format(
                pid,
                command, fd_mapping,
            ))
            for fd in fds_to_be_closed_in_parent:
                logger.debug("fd {}: closing".format(fd))
                os.close(fd)
            return pid

    def _reading_end_fd(self, pipe_id):
        if pipe_id not in self._reading_ends:
            self._make_pipe(pipe_id)
        return self._reading_ends[pipe_id]

    def _writing_end_fd(self, pipe_id):
        if pipe_id not in self._writing_ends:
            self._make_pipe(pipe_id)
        return self._writing_ends[pipe_id]

    def _get_and_clear_socket_end(self, socket_id):
        """ Behold! This method is unexpectedly unpure!
        Calling this method twice will have different results.
        Caller is responsible for taking care of retrieved fd. Especially she should close it after use.
        """
        if socket_id in self._socket_other_ends:
            fd = self._socket_other_ends[socket_id]
            del self._socket_other_ends[socket_id]
            return fd
        else:
            def getfd(sock):
                fd = sock.detach()
                assert(fd >= 0)
                return fd
            fd_a, fd_b = map(getfd, socket.socketpair())
            logger.info("socket pair '{}' created, fds {} <-> {}".format(socket_id, fd_a, fd_b))
            self._socket_other_ends[socket_id] = fd_b
            return fd_a

    def _make_pipe(self, pipe_id):
        reading_end, writing_end = os.pipe()
        logger.info("pipe '{}' created, fds {} -> {}".format(pipe_id, writing_end, reading_end))
        assert(pipe_id not in self._writing_ends)
        self._writing_ends[pipe_id] = writing_end
        assert(pipe_id not in self._reading_ends)
        self._reading_ends[pipe_id] = reading_end

    def close_fds(self):
        for fd in self._writing_ends.values():
            logger.debug("fd {}: closing".format(fd))
            os.close(fd)
        for fd in self._reading_ends.values():
            logger.debug("fd {}: closing".format(fd))
            os.close(fd)
        for fd in self._socket_other_ends.values():
            logger.warning("fd {}: closing (unused socket end)".format(fd))
            os.close(fd)

    def join(self):
        statusses = {}
        while len(self._processes) > 0:
            pid, code = os.wait()
            if pid in self._processes:
                status = code // 256  # extract high byte which is exit code
                if status != 0:
                    logger.warning("node {} exited with unsuccessful code {}".format(pid, status))
                else:
                    logger.info("node {} exited with status {}".format(pid, status))
                self._processes.remove(pid)
                statusses[pid] = status
        return statusses
