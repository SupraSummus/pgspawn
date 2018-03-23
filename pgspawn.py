import logging
import os
import sys


logger = logging.getLogger(__name__)


class PipeGraph:
    def __init__(self):
        # dict command_id -> (dict command_fd -> our_fd)
        self._fd_mapping = {}
        # dict our_fd -> (command_id, command_fd)
        self._reverse_fd_mapping = {}
        self._processes = {}

    def _insert_mapping(self, command_id, command_fd, our_fd):
        command_fds = self._fd_mapping.setdefault(command_id, {})
        #assert(command_fd not in command_fds)
        command_fds[command_fd] = our_fd

        #assert(our_fd not in self._reverse_fd_mapping)
        self._reverse_fd_mapping[our_fd] = (command_id, command_fd)

    def make_pipes(self, pipes, our_id):
        for start, end in pipes:
            self._make_pipe(start, end, our_id)

    def _make_pipe(self, start, end, our_id):
        if start[0] == our_id:  # using parents fds
            logger.info("fd {} will be used as input for {}".format(start[1], end))
            self._insert_mapping(*end, start[1])
        elif end[0] == our_id:
            logger.info("fd {} will be used as output for {}".format(end[1], start))
            self._insert_mapping(*start, end[1])
        #elif end[1] in self._fd_mapping.get(end[0], {}):
        #    # pipe to the destination already created
        #    self._insert_mapping(*start, self._fd_mapping.get[end[0]][end[1]])
        #
        else:
            reading_end, writing_end = os.pipe()
            logger.info("pipe {} -> {} will be used to connect {} -> {}".format(writing_end, reading_end, start, end))
            self._insert_mapping(*start, writing_end)
            self._insert_mapping(*end, reading_end)

    def _dup(self, fd):
        new_fd = os.dup(fd)
        logger.debug('fd {} moved to {}'.format(fd, new_fd))
        self._insert_mapping(*self._reverse_fd_mapping[fd], new_fd)
        return new_fd

    def _dup2(self, fd, new_fd):
        os.dup2(fd, new_fd, inheritable=False)
        logger.debug('fd {} moved to {}'.format(fd, new_fd))
        self._insert_mapping(*self._reverse_fd_mapping[fd], new_fd)
        return new_fd

    def _move_fd(self, from_fd, to_fd):
        if from_fd == to_fd:
            # nothing to do
            logger.debug('fd {} already in place'.format(from_fd))
            return

        # if needed make target fd free
        if to_fd in self._reverse_fd_mapping:
            self._dup(to_fd)

        self._dup2(from_fd, to_fd)
        os.close(from_fd)
        del self._reverse_fd_mapping[from_fd]

    def spawn(self, commands):
        for command_id, command in commands.items():
            logger.debug("process '{}': moving required fds in place".format(command_id))
            fd_mapping = self._fd_mapping.get(command_id, {})

            # move fds in place
            for command_fd in fd_mapping.keys():
                self._move_fd(fd_mapping[command_fd], command_fd)

            # sanity check
            for command_fd, our_fd in fd_mapping.items():
                assert(command_fd == our_fd)
            # TODO warn on missing standard descriptors (as they are silently inherited from parent)

            pid = os.fork()
            if pid == 0:
                for fd in fd_mapping.values():
                    os.set_inheritable(fd, True)
                os.execvp(command[0], command)
            else:
                self._processes[pid] = command_id
                logger.info("process '{}' spawned cmd={}, fds={}, pid={}".format(
                    command_id, command,
                    sorted(fd_mapping.values()),
                    pid,
                ))

    def close_fds(self):
        for fd in self._reverse_fd_mapping.keys():
            logger.debug("fd {}: closing".format(fd))
            os.close(fd)

    def join(self):
        while len(self._processes) > 0:
            pid, status = os.wait()
            logger.info("process '{}' exited with status {}".format(self._processes[pid], status))
            del self._processes[pid]
