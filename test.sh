#!/usr/bin/env bash
set -e

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

echo abcd | pgspawn examples/id.yml | ./stdin-eq 'abcd\n'
echo abcd | pgspawn examples/id_explicite.yml | ./stdin-eq 'abcd\n'

pgspawn examples/join.yml | sort | ./stdin-eq 'one\nthree\ntwo\n'
pgspawn examples/join_explicite.yml | sort | ./stdin-eq 'one\nthree\ntwo\n'
pgspawn examples/join_pipe.yml | sort | ./stdin-eq 'one\nthree\ntwo\n'

echo -en 'a\nb\nc\n' | pgspawn examples/split_pipe.yml | sort | ./stdin-eq 'a\nb\n'

pgspawn examples/socket.yml

assert_code "pgspawn examples_bad/id.yml" 1
assert_code "pgspawn examples_bad/fd_conflict.yml" 1
assert_code "pgspawn examples/orphaned_write_end.yml" 0
assert_code "pgspawn examples/orphaned_read_end.yml" 0
assert_code "pgspawn examples_bad/write_input.yml" 1
assert_code "pgspawn examples_bad/read_output.yml" 1
assert_code "pgspawn examples_bad/extra_keys.yml" 0
assert_code "pgspawn examples_bad/extra_keys.yml" 0
assert_code "pgspawn examples/exit_max.yml" 57
assert_code "pgspawn examples/empty.yml" 0
