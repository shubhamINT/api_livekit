#!/bin/sh
# Coordination board for parallel agents. See references/PARALLEL-AGENTS.md.
# Only atomic filesystem operations: mkdir (fails if it exists), mv (one
# claimer wins), rmdir (fails if not empty). Safe for 1 to 100s of agents on
# one filesystem. ponytail: mtime heartbeat assumes one machine / shared clock.
set -u
# Default: the main checkout's board, so git worktrees and subdirectories share
# one board. Override with BOARD=<absolute path> (e.g. separate clones).
main=$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)
B=${BOARD:-${main:-.}/agent-tracking/board}
STALE=${BOARD_STALE_MIN:-30}
cmd=${1:-}; [ $# -gt 0 ] && shift

usage() { echo "usage: board.sh join|add|claim|lock|unlock|done|note|status|reap|leave ..." >&2; exit 2; }
need() { [ "$1" -ge "$2" ] || usage; }
beat() { mkdir -p "$B/agents"; touch "$B/agents/$1.md"; }  # any command re-registers the agent
has() { for _h in "$@"; do [ -e "$_h" ] && return 0; done; return 1; }
key() { printf '%s' "$1" | sed 's#^\./##; s#/#__#g'; }
free_locks() { # release every lock owned by agent $1
  for l in "$B"/locks/*/; do
    [ -f "${l}owner" ] && [ "$(cat "${l}owner")" = "$1" ] && rm -f "${l}owner" && rmdir "$l"
  done 2>/dev/null
}

case $cmd in
join)   need $# 1; mkdir -p "$B/agents" "$B/tasks" "$B/locks"
        echo "idle" > "$B/agents/$1.md"; echo "joined $1" ;;
add)    need $# 2; mkdir -p "$B/tasks"
        has "$B/tasks/$1."* && { echo "exists $1"; exit 1; }
        echo "$2" > "$B/tasks/$1.todo"; echo "added $1" ;;
claim)  need $# 1; beat "$1"
        for f in "$B"/tasks/*.todo; do
          [ -e "$f" ] || continue  # gone: another agent took it
          t=$(basename "$f" .todo)
          dep=$(sed -n 's/^after=\([^ ;]*\).*/\1/p' "$f" 2>/dev/null)  # "after=01 ..." waits for 01
          [ -n "$dep" ] && ! has "$B/tasks/$dep"*.done && continue
          if mv "$f" "$B/tasks/$t.$1.doing" 2>/dev/null; then
            echo "$t: $(cat "$B/tasks/$t.$1.doing")" > "$B/agents/$1.md"
            echo "$t: $(cat "$B/tasks/$t.$1.doing")"; exit 0
          fi
        done
        echo NONE; has "$B"/tasks/*.todo && echo "open tasks wait on unfinished ones"; has "$B"/tasks/*.doing && echo "others still working"; exit 1 ;;
lock)   need $# 2; id=$1; shift; beat "$id"; got=""
        for p in "$@"; do
          d="$B/locks/$(key "$p")"
          if mkdir "$d" 2>/dev/null; then echo "$id" > "$d/owner"; got="$got $d"
          else # all or nothing: roll back what we took
            for g in $got; do rm -f "$g/owner"; rmdir "$g"; done
            echo "locked by $(cat "$d/owner" 2>/dev/null): $p"; exit 1
          fi
        done; echo "locked $*" ;;
unlock) need $# 1; beat "$1"; free_locks "$1"; echo "unlocked" ;;
done)   need $# 3; beat "$1"; f="$B/tasks/$2.$1.doing"
        [ -f "$f" ] || { echo "not yours: $2"; exit 1; }
        echo "$(cat "$f") => $3" > "$B/tasks/$2.$1.done" && rm "$f"
        free_locks "$1"; echo "idle" > "$B/agents/$1.md"; echo "done $2" ;;
note)   need $# 2; echo "$2" > "$B/agents/$1.md"; echo ok ;;
status) [ -d "$B" ] || { echo "no board"; exit 0; }
        for a in "$B"/agents/*.md; do [ -e "$a" ] && echo "agent $(basename "$a" .md): $(cat "$a")"; done
        for s in todo doing done; do printf '%s %s  ' "$s" "$(ls "$B"/tasks/*."$s" 2>/dev/null | wc -l)"; done; echo
        for l in "$B"/locks/*/; do [ -f "${l}owner" ] && echo "lock $(basename "$l") by $(cat "${l}owner")"; done ;;
reap)   [ -d "$B/agents" ] || exit 0
        find "$B/agents" -name '*.md' -mmin +"$STALE" | while read -r a; do
          id=$(basename "$a" .md)
          for f in "$B"/tasks/*."$id".doing; do [ -e "$f" ] && mv "$f" "${f%."$id".doing}.todo"; done
          free_locks "$id"; rm -f "$a"; echo "reaped $id"
        done ;;
leave)  need $# 1; id=$1; log=${2:-}
        for f in "$B"/tasks/*."$id".doing; do [ -e "$f" ] && mv "$f" "${f%."$id".doing}.todo"; done
        free_locks "$id"; rm -f "$B/agents/$id.md"
        rmdir "$B/agents" 2>/dev/null || { echo "left; others still on board"; exit 0; }
        # Last agent out. Keep the board if work is unfinished.
        if has "$B"/tasks/*.todo "$B"/tasks/*.doing; then
          mkdir -p "$B/agents"; echo "last out, but tasks remain; board kept"; exit 0
        fi
        [ -n "$log" ] && cat "$B"/tasks/*.done >> "$log" 2>/dev/null
        rm -f "$B"/tasks/*.done; rmdir "$B/tasks" "$B/locks" "$B" 2>/dev/null
        [ -d "$B" ] && echo "last out; board not empty, kept" || echo "last out; board removed" ;;
*)      usage ;;
esac
