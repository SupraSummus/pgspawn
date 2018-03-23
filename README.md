PGSpawn
=======

Spawn graph of processes that communicate with each other via anonymous pipes.

    $ echo 123 | pgspawn examples/example.yml 
    start
    123
    end
    end2

Graph description
-----------------

Just a graph definition encoded in YAML. For example:

    nodes:
      - command: [cat]

It spawns `cat` program and doesn't do anything about file descriptors,
so child process inherits standard fds (probably stdin, stdout, stderr).

More complicated example (`examples/example2.yml`, it's a TCP chat with
expression evaluation):

    nodes:
      # ncat tcp server waiting for many connections
      - command: [ncat, -v, -l, -k, -p7000]
        inputs:
          0: send
        outputs:
          2: log
          1: received

      # periodic echo of current date is sent to opened connections
      - command: [bash, -c, 'while true; do date; sleep 10; done']
        outputs:
          1: send

      # log being saved to a file
      - command: [bash, -c, 'cat > logfile.txt']
        inputs:
          0: log

      # incoming data is echoed back but also processed by our fancy machinery
      - command: [tee, /proc/self/fd/3]
        inputs:
          0: received
        outputs:
          1: send
          3: unfiltered_exprs

      # pass only lines beginning with `#`
      - command: [sed, -rn, -u, 's/^#(.*)/\1/p']
        inputs:
          0: unfiltered_exprs
        outputs:
          1: exprs

      # evaluate expressions and send results
      - command: [xargs, -L1, expr]
        inputs:
          0: exprs
        outputs:
          1: send
          2: send
