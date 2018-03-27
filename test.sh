#!/usr/bin/env bash
set -e

function assert {
	diff /proc/self/fd/0 <(echo -en "$1")
}

echo abcd | pgspawn examples/id.yml | assert 'abcd\n'
echo abcd | pgspawn examples/id_explicite.yml | assert 'abcd\n'

pgspawn examples/join.yml | sort | assert 'one\nthree\ntwo\n'
pgspawn examples/join_explicite.yml | sort | assert 'one\nthree\ntwo\n'
pgspawn examples/join_pipe.yml | sort | assert 'one\nthree\ntwo\n'

echo -en 'a\nb\nc\n' | pgspawn examples/split_pipe.yml | sort | assert 'a\nb\n'
