#!/bin/bash
set -eu

error () { echo "ERROR in '$file': $@" >&2; exit 1; }

for file in "$@"; do
    if grep '\x0D' "$file"; then
        error 'Use LF to end lines, not CRLF'
    fi
    if grep -Pzo '(?<![-=\n]\n\n)(?<=\n)(#+ \N*\w\N*|\N*\w\N*\n-+)\n' "$file"; then
        error 'Need two blank lines before heading'
    fi
    if grep -Pv '^(\[[^\]]+\]: .*|\[!.*\))$' "$file" | grep -Pvn '^.{0,90}$'; then
        error 'Lines too long'
    fi
done
