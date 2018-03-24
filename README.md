PGSpawn
=======

Spawn graph of processes that communicate with each other via anonymous pipes.

Examples
--------

Check the `examples/` directory.

### id

As input it takes YAML file with graph description in it. For example single-node graph:

    $ cat examples/id.yml
    nodes:
      - command: [cat]
    $ echo abc | pgspawn examples/id.yml
    abc

It spawns `cat` program and doesn't do anything about file descriptors,
so child process inherits standard fds (probably stdin, stdout, stderr).

### yes

We can do more complex. Lets write `yes` program counterpart:

    $ cat examples/yes.yml
    nodes:
      - command: [cat]
        outputs:
          1: feedback
      - command: [tee, /proc/self/fd/3]
        inputs:
          0: feedback
        outputs:
          3: feedback
    $ echo y | pgspawn examples/yes.yml
    y
    y
    y
    ...

What it does is create pipe (named internally `feedback`) and use it to
feed output into input. Section `outputs: {1: feedback}` describes that
file descriptor 1 used by `cat` (it's stdout) is fed into our pipe.
Section `inputs: {0: feedback}` denotes that fd 0 of `tee` program is
read from `feedback` pipe.

### swap stdout-stderr

It's possible to use parent's program fds in `inputs` and `outputs` descriptions.
Just give them names and roll:

    $ cat examples/swap.yml
    outputs:
      stdout: 1
      stderr: 2
    nodes:
      - command: [bash, -c, echo "I'm stdout"; echo "I'm stderr" >&2;]
        outputs:
          1: stderr
          2: stdout
    $ pgspawn examples/swap.yml > /dev/null
    I'm stdout
    $ pgspawn examples/swap.yml 2> /dev/null
    I'm stderr

Similar you can do with `inputs` (see `examples/id_explicite.yml`).

### server

More complicated example is shown in `examples/server.yml`.
It's a TCP chat with expression evaluation.
