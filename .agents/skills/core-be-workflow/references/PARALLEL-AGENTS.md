# Parallel agents: the coordination board

Use this whenever more than one agent works in the same repo at the same
time: several sessions, an orchestrator with workers, or subagents that edit
files. A single agent may use it too; it costs a few commands.

The board is `agent-tracking/board/`. It prevents two failures:

- **Overlap.** Two agents edit the same file or do the same task.
- **Idle agents.** An agent waits by reading code over and over and never
  takes work.

It works for one agent or hundreds because every agent writes only its own
files, and every claim is one atomic filesystem operation. Never edit another
agent's files by hand.

## Layout

```
agent-tracking/board/
  tasks/<NN-slug>.todo            open task: one line, "goal; files it touches"
  tasks/<NN-slug>.<agent>.doing   claimed (renamed from .todo; one winner)
  tasks/<NN-slug>.<agent>.done    finished: "goal => result"
  locks/<path__as__key>/owner     exclusive lock on a file or folder
  agents/<agent>.md               one line: what this agent is doing now
```

Run everything through the script in this skill,
`scripts/board.sh` (POSIX `sh`). Run it from anywhere in the repo.

## Where the board lives

- **Subagents, several terminals, several sessions** in one checkout: all
  share one board automatically.
- **Git worktrees** (including subagents started with worktree isolation):
  the script finds the main checkout with `git rev-parse --git-common-dir`
  and uses its board, so every worktree shares one board. File locks still
  name repo-relative paths, so a lock on `src/a.py` covers that file in
  every worktree.
- **Separate clones on one machine:** set the same absolute path in every
  agent, for example `export BOARD=/home/me/CODE/app/agent-tracking/board`.
- **Different machines:** not supported (see Limits).

## Agent ID

Use a short unique ID: your role plus 4 random characters, for example
`api-7f3k`. Never reuse another agent's ID.

## The loop — every agent

```sh
S=<path to this skill>/scripts/board.sh
sh $S join api-7f3k
sh $S status                 # one screen: agents, task counts, locks
sh $S claim api-7f3k         # prints "NN-slug: goal; files" or NONE
sh $S lock api-7f3k src/items/service.py src/items/router.py
# ... do the task: edit, test ...
sh $S done api-7f3k 03-items "added GET /items, 6 tests pass"
sh $S claim api-7f3k         # next task; repeat until NONE
sh $S leave api-7f3k agent-tracking/plans/<slug>/progress.md
```

Rules:

1. **Claim before you edit.** Edit only files your claimed task names, after
   `lock` succeeds. `lock` is all or nothing. It either takes every path, or
   takes none and names the holder.
2. **Never wait by reading.** If `claim` says NONE or `lock` fails, do not
   re-read code "to be ready" or poll. Do this instead, in order:
   1. Claim another task.
   2. Add a follow-up task you found (`add`). Then claim it.
   3. Review or test a `.done` task that has no review yet. Add it as a task
      first, so two agents do not review the same one.
   4. If nothing is left, run `leave`, report "no work left" and stop.
   Reading code is allowed only as part of a claimed task.
3. **Keep your line true.** `claim` and `done` update `agents/<id>.md`. Use
   `note <id> "<text>"` for "blocked on X" or "running tests".
4. **Finish or give back.** Stopping before the task is done? Run `leave`.
   It returns your `.doing` task to `.todo` and releases your locks, so
   another agent picks the task up.
5. **Status is cheap.** `status` prints names and counts only. Never `cat`
   the whole board.

## Making tasks

The agent that owns the approved `tasks.md` (the orchestrator, or the first
agent) turns each step into one task before any worker claims:

```sh
sh $S add 01-schema "items table + migration; src/db/models.py migrations/"
sh $S add 02-api    "GET /items endpoint; src/items/"
```

- Number tasks in the order they must run. Workers claim the lowest open
  number first.
- A task that depends on an earlier one starts with `after=<NN>`, for example
  `add 03-ui "after=02 items page; src/pages/items/"`. `claim` skips it until
  a `02*` task is `.done`.
- Two tasks that touch the same file are one task, or they run in order.
  Locks are the safety net, not the plan.

## Last agent out removes the board

`leave` removes your agent file, then tries `rmdir agents/`. `rmdir` fails
while any other agent file exists, so only the last agent continues:

- **Tasks still open** (`.todo` or `.doing`): the board stays, and the script
  says so. Tell the user.
- **All tasks done:** the done lines are appended to the log file you pass
  (use the plan's `progress.md`, so history is kept). Then the board is
  deleted.

One agent alone is always the last one out, so it removes the board itself.

## Crashed agents

Each command touches your agent file. Its age is your heartbeat. A crashed
agent stops updating it. `reap` finds agent files older than
`BOARD_STALE_MIN` minutes (default 30). It moves their `.doing` tasks back to
`.todo`, releases their locks and removes their files. Run `reap` when a task
seems stuck. On a long task, run `note` now and then to stay fresh.

## Limits

- All agents need one shared filesystem. Separate machines or clones need a
  shared service, not this board.
- The heartbeat uses file times. Agents on hosts with different clocks can
  be reaped too early. Increase `BOARD_STALE_MIN` if that happens.
- `board/` is scratch state. Do not commit it. Only `progress.md` keeps the
  record.
