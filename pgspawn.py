from collections import namedtuple
import logging
import os
import sys


logger = logging.getLogger(__name__)


class GraphException(Exception):
    pass


class Node(namedtuple('Node', ('command', 'inputs', 'outputs'))):
    @classmethod
    def from_dict(cls, description):
        unknown_keys = description.keys() - set(['command', 'inputs', 'outputs'])
        if len(unknown_keys) > 0:
            logger.warning("Unknown keys in node description dict: {}".format(unknown_keys))

        return cls(
            command=[str(p) for p in description['command']],
            inputs={int(fd): str(n) for fd, n in description.get('inputs', {}).items()},
            outputs={int(fd): str(n) for fd, n in description.get('outputs', {}).items()},
        )
        return n


class Graph(namedtuple('Graph', ('inputs', 'outputs', 'nodes'))):
    @classmethod
    def from_dict(cls, description):
        unknown_keys = description.keys() - set(['inputs', 'outputs', 'nodes'])
        if len(unknown_keys) > 0:
            logger.warning("Unknown keys in graph description dict: {}".format(unknown_keys))

        g = cls(
            inputs={str(n): int(fd) for n, fd in description.get('inputs', {}).items()},
            outputs={str(n): int(fd) for n, fd in description.get('outputs', {}).items()},
            nodes=list(map(Node.from_dict, description.get('nodes', []))),
        )

        g.check_for_pipe_collisions()
        g.check_pipe_directions()
        g.check_for_fd_collisions()
        try:
            g.check_for_dead_ends()
        except GraphException as e:
            logger.warning(str(e))

        return g

    @property
    def pipe_names(self):
        pipes = set()
        pipes.update(
            self.inputs.keys(),
            self.outputs.keys(),
        )
        for node in self.nodes:
            pipes.update(
                node.inputs.values(),
                node.outputs.values(),
            )
        return pipes

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
            colliding_fds = node.inputs.keys() & node.outputs.keys()
            if len(colliding_fds) > 0:
                raise GraphException(
                    "Multiple pipes specified for single fd. "
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
            raise GraphException("Some pipes are never read: {}".format(only_written))
        if len(only_read) > 0:
            raise GraphException("Some pipes are never written: {}".format(only_read))


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
            spawner.spawn(node.command, node.inputs, node.outputs)
        return spawner

    def __init__(self, inputs={}, outputs={}):
        self._reading_ends = {}
        self._writing_ends = {}
        self._processes = set()

        for pipe_id, fd in inputs.items():
            os.set_inheritable(fd, False)
            self._reading_ends[pipe_id] = fd
        for pipe_id, fd in outputs.items():
            os.set_inheritable(fd, False)
            self._writing_ends[pipe_id] = fd

    def spawn(self, command, inputs, outputs):
        fd_mapping = {}
        for subprocess_fd, pipe_id in inputs.items():
            assert(subprocess_fd not in fd_mapping)
            fd_mapping[subprocess_fd] = self._reading_end_fd(pipe_id)
        for subprocess_fd, pipe_id in outputs.items():
            assert(subprocess_fd not in fd_mapping)
            fd_mapping[subprocess_fd] = self._writing_end_fd(pipe_id)

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
            return pid

    def _reading_end_fd(self, pipe_id):
        if pipe_id not in self._reading_ends:
            self._make_pipe(pipe_id)
        return self._reading_ends[pipe_id]

    def _writing_end_fd(self, pipe_id):
        if pipe_id not in self._writing_ends:
            self._make_pipe(pipe_id)
        return self._writing_ends[pipe_id]

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
