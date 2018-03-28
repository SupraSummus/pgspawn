#!/usr/bin/env bash
set -e

function assert {
	diff /proc/self/fd/0 <(echo -en "$1")
}

function assert_code {
	set +e
	$1 >/dev/null 2>&1
	CODE="$?"
	set -e
	if [ "$CODE" != "$2" ]; then
		echo "exit code of '$1' is $CODE (expected $2)"
		false
	fi
}

echo abcd | pgspawn examples/id.yml | assert 'abcd\n'
echo abcd | pgspawn examples/id_explicite.yml | assert 'abcd\n'

pgspawn examples/join.yml | sort | assert 'one\nthree\ntwo\n'
pgspawn examples/join_explicite.yml | sort | assert 'one\nthree\ntwo\n'
pgspawn examples/join_pipe.yml | sort | assert 'one\nthree\ntwo\n'

echo -en 'a\nb\nc\n' | pgspawn examples/split_pipe.yml | sort | assert 'a\nb\n'

assert_code "pgspawn examples_bad/id.yml" 1
assert_code "pgspawn examples_bad/fd_conflict.yml" 1
assert_code "pgspawn examples/orphaned_write_end.yml" 0
assert_code "pgspawn examples/orphaned_read_end.yml" 0
assert_code "pgspawn examples/write_input.yml" 1
assert_code "pgspawn examples/read_output.yml" 1
assert_code "pgspawn examples_bad/extra_keys.yml" 0
assert_code "pgspawn examples_bad/extra_keys.yml" 0
assert_code "pgspawn examples/exit_max.yml" 57
assert_code "pgspawn examples/empty.yml" 0
