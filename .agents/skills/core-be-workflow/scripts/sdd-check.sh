#!/bin/sh
# SDD validator. Checks spec, plan, and task files; same checks run in CI.
# usage: sdd-check.sh next <topic> | spec <dir> | analyze <slug> | converge <slug> | status | ci | doctor
# Output: SEVERITY  path:line  message. Exit 1 on any CRITICAL or HIGH.
# POSIX sh + awk only. ponytail: greps the Markdown templates, so a spec that
# departs from templates/spec.md can fool it; keep the templates' line shapes.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)   # before the cd below: $0 may be relative
ROOT=${SDD_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}
cd "$ROOT" || exit 2
IDX=agent-tracking/INDEX.md
TAB=$(printf '\t')

emit() { printf '%s  %s  %s\n' "$1" "$2" "$3"; }
trim() { sed 's/^ *//; s/ *$//'; }

index_rows() { # slug TAB type TAB status, one line per INDEX row
  [ -f "$IDX" ] || return 0
  awk -F'|' 'NF>=6 { for(i=2;i<=5;i++) gsub(/^ +| +$/,"",$i)
    if ($3!="" && $3!="Slug" && $3 !~ /^-+$/) print $3 "\t" $4 "\t" $5 }' "$IDX"
}
tf() { # task file; the legacy name plan.md still works in repos created before the rename
  d=agent-tracking/plans/$1; if [ ! -f "$d/tasks.md" ] && [ -f "$d/plan.md" ]; then echo "$d/plan.md"; else echo "$d/tasks.md"; fi; }
spec_of() { sed -n 's/^\*\*Spec:\*\* *\([^ ]*\).*/\1/p' "$(tf "$1")" 2>/dev/null | head -1; }
ac_active() { sed -n 's/^- \*\*\(AC-[0-9]*\):\*\*.*/\1/p' "$1"; }
covers_of() { sed -n 's/^\*\*Covers:\*\*//p' "$(tf "$1")" 2>/dev/null | head -1 | grep -oE 'AC-[0-9]+'; }
task_acs() { # ACs the task owns: its Covers line, else every active AC of the spec
  c=$(covers_of "$1"); if [ -n "$c" ]; then printf '%s\n' "$c"; else ac_active "$2"; fi; }
cov_all() { # ACs covered by any non-cancelled task that points at spec $1
  index_rows | while IFS="$TAB" read -r slug type st; do
    [ "$st" = cancelled ] && continue
    [ "$(spec_of "$slug")" = "$1" ] || continue
    task_acs "$slug" "$1"
  done | sort -u; }
spec_status() { sed -n 's/^- \*\*Status:\*\* *\([a-z]*\).*/\1/p' "$1" | head -1; }

cmd_spec() {
  d=${1%/}; f=$d/spec.md
  [ -f "$f" ] || { emit CRITICAL "$f" "spec.md missing"; return; }
  st=$(spec_status "$f")
  case $st in draft|approved|implemented|reconstructed) ;;
    *) emit HIGH "$f" "Status is '$st', expected draft|approved|implemented|reconstructed" ;; esac
  [ "$(ac_active "$f" | wc -l)" -ge 1 ] || emit HIGH "$f" "no active acceptance criteria (- **AC-n:** ...)"
  for a in $(grep -oE '^- (~~)?\*\*AC-[0-9]+' "$f" | grep -oE 'AC-[0-9]+' | sort | uniq -d); do
    emit HIGH "$f" "$a is used twice; numbers are never reused"
  done
  if [ "$st" != draft ]; then
    grep -n 'NEEDS CLARIFICATION:' "$f" | while IFS=: read -r ln _; do
      emit HIGH "$f:$ln" "open [NEEDS CLARIFICATION] marker in a $st spec"
    done
  fi
  c=$(awk '/^## Change log/{s=1;next} s&&/^\|/&&!/^\|[- |]+\|$/&&!/YYYY-MM-DD/{c++} END{print c+0}' "$f")
  [ "$c" -ge 2 ] || emit HIGH "$f" "change log has no row (first row is the table header)"
  o=$(awk '/^## Out of scope/{s=1;next} /^## /{s=0} s&&/^- ./{c++} END{print c+0}' "$f")
  [ "$o" -ge 1 ] || emit MEDIUM "$f" "Out of scope is empty"
}

cmd_analyze() {
  s=$1; p=$(tf "$s")
  [ -f "$p" ] || { emit CRITICAL "$p" "task plan missing"; return; }
  sp=$(spec_of "$s")
  [ -n "$sp" ] && [ -f "$sp" ] || { emit CRITICAL "$p" "Spec: line missing or file not found ('$sp')"; return; }
  dp=$(dirname "$sp")/plan.md
  [ -f specs/constitution.md ] || emit CRITICAL specs/constitution.md "constitution missing"
  [ -f "$dp" ] || emit CRITICAL "$dp" "design plan missing"
  case $(spec_status "$sp") in approved|reconstructed|implemented) ;;
    *) emit HIGH "$sp" "spec is not approved" ;; esac
  steps=$(grep -nE '^- \[[ xX]\] ' "$p")
  [ -n "$(covers_of "$s")" ] || emit MEDIUM "$p" "no **Covers:** line; assuming this task owns every active criterion"
  for a in $(task_acs "$s" "$sp"); do
    ac_active "$sp" | grep -qx "$a" || continue   # retired criteria need no task
    printf '%s\n' "$steps" | grep -qw "$a" || emit CRITICAL "$p" "$a has no task"
  done
  for a in $(printf '%s\n' "$steps" | grep -oE 'AC-[0-9]+' | sort -u); do
    grep -q "\*\*$a:\*\*" "$sp" || emit HIGH "$p" "a task names $a, which is not in $sp"
  done
  printf '%s\n' "$steps" | while IFS= read -r l; do
    [ -n "$l" ] || continue
    printf '%s' "$l" | grep -qEi 'AC-[0-9]+|(^|[^a-z])(setup|docs|converge)([^a-z]|$)' ||
      emit MEDIUM "$p:${l%%:*}" "step has no AC-n and no setup/docs/converge tag"
  done
  for f in "$sp" "$dp"; do
    [ -f "$f" ] && grep -n 'NEEDS CLARIFICATION:' "$f" | while IFS=: read -r ln _; do
      emit HIGH "$f:$ln" "open [NEEDS CLARIFICATION] marker"
    done
  done
  [ -f "$dp" ] || return 0
  cx=$(awk -F'|' '/^## Complexity tracking/{s=1;next} /^## /{s=0}
    s&&NF>=4{a=$2; gsub(/^ +| +$/,"",a); if(a!=""&&a!~/^-+$/&&a!~/Violation/)c++} END{print c+0}' "$dp")
  awk -F'|' '/^## Constitution check/{s=1;next} /^## /{s=0}
    s&&NF>=6&&$2!~/#/&&$2!~/---/{a=$5; gsub(/^ +| +$/,"",a); print NR "\t" tolower(a)}' "$dp" |
  while IFS="$TAB" read -r ln ans; do
    case $ans in
      yes) ;;
      no) [ "$cx" -ge 1 ] || emit CRITICAL "$dp:$ln" "gate answered no with no Complexity tracking row" ;;
      *) emit HIGH "$dp:$ln" "gate not answered yes or no ('$ans')" ;;
    esac
  done
}

cmd_converge() {
  s=$1; pg=agent-tracking/plans/$s/progress.md; sp=$(spec_of "$s")
  [ -f "$pg" ] || { emit CRITICAL "$pg" "progress.md missing"; return; }
  [ -n "$sp" ] && [ -f "$sp" ] || { emit CRITICAL "$pg" "no readable Spec: line in the task file (tasks.md)"; return; }
  for a in $(task_acs "$s" "$sp"); do
    ac_active "$sp" | grep -qx "$a" || continue
    row=$(grep -E "^\| *$a *\|" "$pg" | tail -1)
    [ -n "$row" ] || { emit CRITICAL "$pg" "$a has no row in the evidence table"; continue; }
    st=$(printf '%s' "$row" | awk -F'|' '{x=$(NF-1); gsub(/^ +| +$/,"",x); print tolower(x)}')
    ev=$(printf '%s' "$row" | awk -F'|' '{x=$3; gsub(/^ +| +$/,"",x); print x}')
    [ "$st" = met ] || emit CRITICAL "$pg" "$a status is '$st', not met"
    [ -n "$ev" ] || emit HIGH "$pg" "$a has no evidence"
  done
}

cmd_status() { # TASK slug type status plan=yes|no spec=yes|no verdict=yes|no
  index_rows | while IFS="$TAB" read -r slug type st; do
    case $st in approved|in-progress|scoping|researching|awaiting-approval) ;; *) continue ;; esac
    pa=no; grep -q '^\*\*Status:\*\* approved' "$(tf "$slug")" 2>/dev/null && pa=yes
    [ "$type" = trivial ] && pa=yes
    sp=yes
    case $type in feature|change)
      sp=no; grep -rlF "$slug" specs --include=spec.md >/dev/null 2>&1 && sp=yes ;; esac
    vd=no; grep -q '^Verdict: Converged' "agent-tracking/plans/$slug/progress.md" 2>/dev/null && vd=yes
    echo "TASK $slug $type $st plan=$pa spec=$sp verdict=$vd"
  done
}

cmd_ci() {
  any=0
  for d in specs/[0-9][0-9][0-9]-*/; do
    [ -d "$d" ] || continue
    sp=${d}spec.md          # before cmd_spec: sh has no local, cmd_spec reassigns d
    any=1; cmd_spec "$d"
    [ -f "$sp" ] || continue
    cv=$(cov_all "$sp")
    for a in $(ac_active "$sp"); do
      if [ -z "$cv" ]; then emit MEDIUM "$sp" "no task references this spec"; break; fi
      printf '%s\n' "$cv" | grep -qx "$a" || emit HIGH "$sp" "$a is covered by no task"
    done
  done
  [ "$any" = 0 ] || [ -f specs/constitution.md ] || emit CRITICAL specs/constitution.md "specs exist but the constitution is missing"
  index_rows | while IFS="$TAB" read -r slug type st; do
    pf=$(tf "$slug")
    case $st in
      done) case $type in feature|change)
          sp=$(spec_of "$slug")
          if [ -n "$sp" ] && [ -f "$sp" ]; then
            [ "$(spec_status "$sp")" = implemented ] || emit HIGH "$sp" "task $slug is done but spec Status is not implemented"
            cmd_converge "$slug"
          else emit HIGH "$pf" "done $type task has no readable Spec: line"; fi ;; esac ;;
      approved|in-progress) [ "$type" = trivial ] ||
          grep -q '^\*\*Status:\*\* approved' "$pf" 2>/dev/null ||
          emit HIGH "$pf" "task $slug is $st but its tasks file is not 'Status: approved'" ;;
    esac
  done
}

cmd_doctor() { # is this repo set up for the pack? read-only
  A=AGENTS.md; C=CLAUDE.md
  pfx=$(basename "$(dirname "$HERE")"); pfx=${pfx%-workflow}; tm=$HERE/../templates/AGENTS.md
  blk() { awk -v s="<!-- $pfx:start -->" -v e="<!-- $pfx:end -->" '$0==s{f=1;next} $0==e{f=0} f' "$1"; }
  own() { awk -v s="<!-- $pfx:start -->" -v e="<!-- $pfx:end -->" '$0==s{f=1;next} $0==e{f=0;next} !f' "$1"; }
  long() { sed 's/^[ >*-]*//; s/ *$//' | awk 'length($0)>=25 && $0 !~ /^(```|\||<!--|-->)/'; }
  t1=${TMPDIR:-/tmp}/sdd-doctor1.$$; t2=${TMPDIR:-/tmp}/sdd-doctor2.$$
  if [ ! -f $A ]; then emit HIGH $A "missing; init creates it from templates/AGENTS.md"
  else
    if grep -qF "<!-- $pfx:start -->" $A && grep -qF "<!-- $pfx:end -->" $A; then
      [ ! -f "$tm" ] || [ "$(blk $A)" = "$(blk "$tm")" ] ||
        emit MEDIUM $A "managed block differs from the pack's current template; refresh it (references/REGISTER-PACK.md)"
    else emit HIGH $A "pack markers <!-- $pfx:start --> / <!-- $pfx:end --> missing"; fi
    grep -q '^## Project structure' $A || emit MEDIUM $A "no '## Project structure' section"
    n=$(own $A | long | sort | uniq -d | wc -l)
    [ "$n" -eq 0 ] || emit MEDIUM $A "$n long lines appear more than once outside the managed block; keep each fact once"
  fi
  if [ ! -f $C ]; then emit HIGH $C "missing; it must contain the line @AGENTS.md"
  else
    grep -qx '@AGENTS.md' $C || emit HIGH $C "no '@AGENTS.md' import line"
    n=$(grep -v '^[[:space:]]*$' $C | grep -vxF '@AGENTS.md' | wc -l)
    [ "$n" -le 5 ] || emit MEDIUM $C "$n lines besides the import; keep only Claude-specific notes, move the rest to AGENTS.md"
    if [ -f $A ]; then
      long < $C | sort -u > $t1; long < $A | sort -u > $t2
      n=$(comm -12 $t1 $t2 | wc -l); rm -f $t1 $t2
      [ "$n" -eq 0 ] || emit MEDIUM $C "$n long lines also appear in AGENTS.md; AGENTS.md is the single source"
    fi
  fi
  gt=$HERE/../templates/gitignore.txt
  gib() { awk -v s="# $pfx:start" -v e="# $pfx:end" '$0==s{f=1} f{print} $0==e{f=0}' "$1"; }
  if [ -f .gitignore ] && grep -qxF "# $pfx:start" .gitignore; then
    [ ! -f "$gt" ] || [ "$(gib .gitignore)" = "$(gib "$gt")" ] ||
      emit MEDIUM .gitignore "pack block differs from templates/gitignore.txt; refresh it (references/REGISTER-PACK.md)"
  else emit MEDIUM .gitignore "pack block missing (board and screenshot scratch would be committed); see references/REGISTER-PACK.md"; fi
  [ -f $IDX ] || emit MEDIUM $IDX "missing; created from templates/INDEX.md"
  [ -f specs/constitution.md ] || emit HIGH specs/constitution.md "missing; run the constitution skill"
  [ -f specs/project.md ] || emit MEDIUM specs/project.md "missing; the project brief from the init skill"
  [ -f README.md ] || emit MEDIUM README.md "missing"
  grep -qs sdd-hook .claude/settings.json .claude/settings.local.json .codex/hooks.json .cursor/hooks.json \
      .github/hooks/*.json .gemini/settings.json .devin/hooks.json ||
    emit MEDIUM .claude/settings.json "edit guard not registered for any agent (ignore if the pack is a Claude plugin); the user runs install-hook.sh --agent <name> for each agent the team uses"
}

cmd=${1:-}; [ $# -gt 0 ] && shift
usage() { echo "usage: sdd-check.sh next <topic> | spec <dir> | analyze <slug> | converge <slug> | status | ci | doctor" >&2; exit 2; }
report() { # run $1, print findings, exit 1 on CRITICAL/HIGH
  out=$("$@")
  [ -n "$out" ] || { echo "OK"; exit 0; }
  echo "$out"
  printf '%s\n' "$out" | grep -qE '^(CRITICAL|HIGH) ' && exit 1
  exit 0
}
case $cmd in
  next) [ $# -ge 1 ] || usage
        max=$(ls -d specs/[0-9][0-9][0-9]-*/ 2>/dev/null | sed 's#^specs/\([0-9]*\)-.*#\1#' | sort -n | tail -1 | sed 's/^0*//')
        printf '%03d-%s\n' $(( ${max:-0} + 1 )) "$1" ;;
  spec)     [ $# -ge 1 ] || usage; report cmd_spec "$1" ;;
  analyze)  [ $# -ge 1 ] || usage; report cmd_analyze "$1" ;;
  converge) [ $# -ge 1 ] || usage; report cmd_converge "$1" ;;
  ci)       report cmd_ci ;;
  doctor)   report cmd_doctor ;;
  status)   cmd_status ;;
  *) usage ;;
esac
