#!/bin/sh
# Edit guard that enforces the SDD workflow, for any coding agent with command
# hooks (Claude Code, Codex, Cursor, GitHub Copilot, Gemini CLI, Windsurf). Reads the event JSON on stdin; a small python
# snippet maps every agent's field names to one shape, the policy below is shared.
#   before a file edit: a source edit needs an approved task in
#     agent-tracking/INDEX.md; feature/change also need the spec first.
#   stop: a feature/change task that is in-progress may not stop before
#     "Verdict: Converged" is in its progress.md.
# Optional first argument pre|stop names the event for agents whose JSON omits it (Copilot CLI).
# Exit 2 blocks and the stderr text goes to the model; Cursor and Copilot also get
# their JSON reply. Fails open if python3 is missing, the JSON is unreadable, or an
# edit event names no path (CI covers it). SDD_GUARD=off in the user's environment
# disables it. ponytail: shell writes (sed -i, >) are not seen; CI covers them.
[ "${SDD_GUARD:-}" = off ] && exit 0
command -v python3 >/dev/null 2>&1 || { echo "sdd-hook: python3 missing, guard off" >&2; exit 0; }
here=$(cd "$(dirname "$0")" && pwd)
pfx=$(basename "$(dirname "$here")"); pfx=${pfx%-workflow}   # e.g. onespace-be

norm=$(python3 -c '
import json, os, re, sys
try: d = json.load(sys.stdin)
except Exception: sys.exit(0)
if not isinstance(d, dict): sys.exit(0)
ev = str(d.get("hook_event_name") or d.get("agent_action_name") or "")
e = re.sub(r"[^a-z]", "", ev.lower())
kind = "pre" if e in ("pretooluse", "beforetool", "prewritecode") else "stop" if e in ("stop", "afteragent", "agentstop") else "other"
hint = sys.argv[1] if len(sys.argv) > 1 else ""
if kind == "other" and hint in ("pre", "stop"): kind = hint   # Copilot CLI sends no event name; the config entry says which event it is
if "workspace_roots" in d or "cursor_version" in d: agent = "cursor"
elif "agent_action_name" in d: agent = "windsurf"
elif "toolName" in d or e == "agentstop" or (hint and not ev): agent = "copilot"
else: agent = "generic"
tn = str(d.get("tool_name") or d.get("toolName") or "")
edit = agent == "windsurf" or not tn or re.match(r"(?i)(write|edit|multiedit|notebookedit|apply_patch|create|replace|write_file|str_replace|patch|delete)", tn)
ti = d.get("tool_input")
if ti is None and d.get("toolArgs") is not None:
    ti = d["toolArgs"]
    if isinstance(ti, str):
        try: ti = json.loads(ti)
        except Exception: pass
paths = []
def patch(t):
    if not isinstance(t, str): return
    if "*** Begin Patch" in t:
        paths.extend(re.findall(r"(?m)^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", t))
        paths.extend(re.findall(r"(?m)^\*\*\* Move to: (.+?)\s*$", t))
    elif re.search(r"(?m)^@@", t):
        paths.extend(re.findall(r"(?m)^\+\+\+ (?:b/)?(\S+)", t))
if isinstance(ti, dict):
    for k in ("file_path", "notebook_path", "path", "filePath", "target_file", "file"):
        if isinstance(ti.get(k), str) and ti[k]: paths.append(ti[k])
    for k in ("command", "patch", "input", "patchText", "patch_text"): patch(ti.get(k))
else: patch(ti)
tf = d.get("tool_info")
if isinstance(tf, dict) and isinstance(tf.get("file_path"), str): paths.append(tf["file_path"])
active = bool(d.get("stop_hook_active")) or (d.get("loop_count") or 0) >= 1 or (agent == "cursor" and kind == "stop" and d.get("status") not in (None, "completed"))
root = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("CURSOR_PROJECT_DIR") or os.environ.get("GEMINI_PROJECT_DIR") or ((d.get("workspace_roots") or [""])[0]) or ""
print("K=" + kind); print("A=" + agent); print("S=" + ("1" if active else "0")); print("R=" + root); print("C=" + str(d.get("cwd") or ""))
print("T=" + ("1" if edit else "0"))
for p in paths: print("P=" + p.replace("\n", " "))
' "${1:-}" 2>/dev/null)

kind=; agent=generic; active=0; root=; cwd=; isedit=1; paths=
while IFS= read -r l; do
  case $l in K=*) kind=${l#K=} ;; A=*) agent=${l#A=} ;; S=*) active=${l#S=} ;; R=*) root=${l#R=} ;; C=*) cwd=${l#C=} ;; T=*) isedit=${l#T=} ;;
    P=*) paths="$paths${paths:+
}${l#P=}" ;; esac
done <<EOF
$norm
EOF
[ -n "$kind" ] || exit 0

proj=$root
if [ -z "$proj" ]; then
  base=${cwd:-$(pwd)}
  proj=$(git -C "$base" rev-parse --show-toplevel 2>/dev/null) || proj=$base
fi
[ -n "$proj" ] && [ -d "$proj" ] || exit 0
SDD_ROOT=$proj; export SDD_ROOT
tasks=$(sh "$here/sdd-check.sh" status 2>/dev/null)

json() { python3 -c 'import json,sys; print(json.dumps(dict(zip(sys.argv[1::2], sys.argv[2::2]))))' "$@"; }
deny() { # exit 2 everywhere; Cursor and Copilot also get their JSON reply on stdout
  echo "$1" >&2
  case $agent in
    cursor) json permission deny user_message "$1" agent_message "$1" ;;
    copilot) json permissionDecision deny permissionDecisionReason "$1" ;;
  esac
  exit 2
}
stopmsg() { # keep the agent working
  case $agent in
    cursor) json followup_message "$1"; exit 0 ;;
    copilot) json decision block reason "$1"; exit 0 ;;
    *) echo "$1" >&2; exit 2 ;;
  esac
}

case $kind in
pre)
  [ "$isedit" = 1 ] || exit 0
  [ -n "$paths" ] || exit 0
  src=
  while IFS= read -r fp; do
    [ -n "$fp" ] || continue
    case $fp in /*) ;; *) fp=$proj/$fp ;; esac
    case $fp in "$proj"/*) rel=${fp#"$proj"/} ;; *) continue ;; esac   # outside the project: allow
    case $rel in agent-tracking/*|specs/*|*.md) continue ;; esac
    case /$rel in */.agents/*|*/.claude/*) continue ;; esac
    src=$rel; break
  done <<EOF
$paths
EOF
  [ -n "$src" ] || exit 0
  printf '%s\n' "$tasks" | grep -qE '^TASK [^ ]+ [^ ]+ (approved|in-progress) plan=yes spec=yes' && exit 0
  line=$(printf '%s\n' "$tasks" | grep -E '^TASK [^ ]+ [^ ]+ (approved|in-progress) ' | head -1)
  if [ -z "$line" ]; then
    deny "SDD guard: no approved task. Load ${pfx}-workflow, agree scope, get the plan approved, then edit source. For a trivial edit, add one row to agent-tracking/INDEX.md (type trivial, status in-progress). Edited: $src"
  fi
  set -- $line
  case $line in
    *plan=no*) deny "SDD guard: task $2 is $4 but agent-tracking/plans/$2/tasks.md is not marked '**Status:** approved (date, by name)'. Get approval first. Edited: $src" ;;
    *) deny "SDD guard: task $2 is a $3 task, so the spec comes first. No specs/*/spec.md names $2 in its change log. Run ${pfx}-specify (new) or ${pfx}-change (existing), then edit source. Edited: $src" ;;
  esac ;;
stop)
  [ "$active" = 1 ] && exit 0
  line=$(printf '%s\n' "$tasks" | grep -E '^TASK [^ ]+ (feature|change) in-progress .* verdict=no' | head -1)
  [ -n "$line" ] || exit 0
  set -- $line
  stopmsg "SDD guard: task $2 is in-progress and has no 'Verdict: Converged' in agent-tracking/plans/$2/progress.md. Run ${pfx}-converge, write the evidence table and the verdict, then the report. If you are blocked, set the INDEX status to blocked and tell the user." ;;
esac
exit 0
