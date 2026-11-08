#!/bin/sh
# Self-check for sdd-check.sh and sdd-hook.sh. Builds a temp repo, mutates it,
# prints PASS/FAIL per case, exits 1 on any failure. Run: sh scripts/test-sdd.sh
here=$(cd "$(dirname "$0")" && pwd)
C="sh $here/sdd-check.sh"; H="sh $here/sdd-hook.sh"
R=$(mktemp -d); trap 'rm -rf "$R"' EXIT
cd "$R" && git init -q . && export SDD_ROOT=$R CLAUDE_PROJECT_DIR=$R
fails=0
ok()   { if "$@" >/dev/null 2>&1; then echo "PASS $label"; else echo "FAIL $label"; fails=$((fails+1)); fi; }
bad()  { "$@" >/dev/null 2>&1; got=$?; if [ "$got" = 1 ]; then echo "PASS $label"; else echo "FAIL $label (exit $got, want 1)"; fails=$((fails+1)); fi; }
code() { want=$1; shift; "$@" >/dev/null 2>&1; got=$?; if [ "$got" = "$want" ]; then echo "PASS $label"; else echo "FAIL $label (exit $got, want $want)"; fails=$((fails+1)); fi; }
pre() { printf '{"hook_event_name":"PreToolUse","tool_name":"Edit","cwd":"%s","tool_input":{"file_path":"%s"}}' "$R" "$1" | $H; }
stop() { printf '{"hook_event_name":"Stop","cwd":"%s","stop_hook_active":%s}' "$R" "${1:-false}" | $H; }

S=specs/001-export; T=agent-tracking/plans/2026-01-01-feature-export
mkdir -p $S $T
cat > specs/constitution.md <<'EOF'
# Constitution
EOF
cat > $S/spec.md <<'EOF'
# Spec 001
- **Status:** approved
## Acceptance criteria
- **AC-1:** exports csv
- **AC-2:** rejects over limit
## Out of scope
- xml
## Open questions
## Change log
| Date | Change | Task slug |
|------|--------|-----------|
| 2026-01-01 | Created | 2026-01-01-feature-export |
EOF
cat > $S/plan.md <<'EOF'
# Plan 001
## Constitution check
| # | Principle | Gate question | Answer | Note |
|---|-----------|---------------|--------|------|
| 1 | Simplicity | one layer? | yes | |
## Complexity tracking
| Violation or extra moving part | Why needed | Simpler option rejected |
|--------------------------------|------------|-------------------------|
EOF
cat > $T/tasks.md <<'EOF'
# Plan
**Status:** approved (2026-01-01, by user)
**Spec:** specs/001-export/spec.md
**Covers:** AC-1, AC-2
## Steps
- [ ] 1. AC-1 test then code
- [ ] 2. AC-2 test then code
- [ ] 3. converge
EOF
cat > $T/progress.md <<'EOF'
## Converge
| AC | Evidence | Code | Status |
|----|----------|------|--------|
| AC-1 | tests/t.py::a | app.py:1 | met |
| AC-2 | tests/t.py::b | app.py:9 | met |
Verdict: Converged
EOF
idx() { mkdir -p agent-tracking; printf '| Date | Slug | Type | Status | Summary | Report |\n|---|---|---|---|---|---|\n| 2026-01-01 | 2026-01-01-feature-export | %s | %s | x | |\n' "$1" "$2" > agent-tracking/INDEX.md; }

label="next: first spec number"; [ "$(cd "$R" && rm -rf specs/009-x && $C next foo)" = "002-foo" ] && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
mkdir specs/009-x; label="next: 009 -> 010 (no octal trap)"; [ "$($C next foo)" = "010-foo" ] && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }; rmdir specs/009-x

label="spec: clean spec passes"; ok $C spec $S
cp $S/spec.md /tmp/spec.$$; echo "- [NEEDS CLARIFICATION: x]" >> $S/spec.md
label="spec: open marker in approved spec fails"; bad $C spec $S
cp /tmp/spec.$$ $S/spec.md
sed 's/^- \*\*AC-2:\*\*.*/- **AC-1:** dup/' /tmp/spec.$$ > $S/spec.md
label="spec: duplicate AC fails"; bad $C spec $S
cp /tmp/spec.$$ $S/spec.md; rm /tmp/spec.$$

label="analyze: clean passes"; ok $C analyze 2026-01-01-feature-export
cp $T/tasks.md /tmp/tp.$$; grep -v 'AC-2' /tmp/tp.$$ > $T/tasks.md
label="analyze: AC with no task is CRITICAL"; bad $C analyze 2026-01-01-feature-export
cp /tmp/tp.$$ $T/tasks.md
sed 's/| yes |/| no |/' $S/plan.md > /tmp/dp.$$; cp $S/plan.md /tmp/dp.orig.$$; cp /tmp/dp.$$ $S/plan.md
label="analyze: gate no without complexity row fails"; bad $C analyze 2026-01-01-feature-export
printf '| extra layer | needed for X | none |\n' >> $S/plan.md
label="analyze: gate no with complexity row passes"; ok $C analyze 2026-01-01-feature-export
cp /tmp/dp.orig.$$ $S/plan.md; rm /tmp/tp.$$ /tmp/dp.$$ /tmp/dp.orig.$$

label="converge: all met passes"; ok $C converge 2026-01-01-feature-export
cp $T/progress.md /tmp/pg.$$; sed 's/| met |$/| partial |/' /tmp/pg.$$ > $T/progress.md
label="converge: partial fails"; bad $C converge 2026-01-01-feature-export
grep -v 'AC-2' /tmp/pg.$$ > $T/progress.md
label="converge: missing evidence row fails"; bad $C converge 2026-01-01-feature-export
cp /tmp/pg.$$ $T/progress.md; rm /tmp/pg.$$

# a later change task owns only the delta (AC-3); the first task keeps owning AC-1, AC-2
T2=agent-tracking/plans/2026-02-01-change-export-limit; mkdir -p $T2
printf '# Plan\n**Status:** approved (2026-02-01, by user)\n**Spec:** specs/001-export/spec.md\n**Covers:** AC-3\n- [ ] 1. AC-3 test then code\n- [ ] 2. converge\n' > $T2/tasks.md
cp $S/spec.md /tmp/sp3.$$; sed -i 's/^## Out of scope/- **AC-3:** limit\n## Out of scope/' $S/spec.md
label="analyze: change task covering only the delta passes"; ok $C analyze 2026-02-01-change-export-limit
label="analyze: first task still passes with a later AC in the spec"; ok $C analyze 2026-01-01-feature-export
printf '# Plan\n**Status:** approved (x)\n**Spec:** specs/001-export/spec.md\n**Covers:** AC-3\n- [ ] 1. docs only\n' > $T2/tasks.md
label="analyze: delta AC with no task is CRITICAL"; bad $C analyze 2026-02-01-change-export-limit
printf '# Plan\n**Status:** approved (2026-02-01, by user)\n**Spec:** specs/001-export/spec.md\n**Covers:** AC-3\n- [ ] 1. AC-3 test then code\n- [ ] 2. converge\n' > $T2/tasks.md
printf '| 2026-02-01 | 2026-02-01-change-export-limit | change | done | y | |\n' > /tmp/row2.$$
idx feature done; cat /tmp/row2.$$ >> agent-tracking/INDEX.md
sed -i 's/^## Out of scope/&/' $S/spec.md
printf '## Converge\n| AC | Evidence | Code | Status |\n|---|---|---|---|\n| AC-3 | tests/t.py::c | app.py:20 | met |\nVerdict: Converged\n' > $T2/progress.md
sed -i 's/^- \*\*Status:\*\* approved/- **Status:** implemented/' $S/spec.md
label="ci: two done tasks covering every AC pass"; ok $C ci
sed -i 's/^\*\*Covers:\*\* AC-1, AC-2/**Covers:** AC-1/' $T/tasks.md
label="ci: AC covered by no task is HIGH"; bad $C ci
sed -i 's/^\*\*Covers:\*\* AC-1$/**Covers:** AC-1, AC-2/' $T/tasks.md
rm -rf $T2; cp /tmp/sp3.$$ $S/spec.md; rm -f /tmp/sp3.$$ /tmp/row2.$$
idx feature done
label="ci: done task with spec still approved fails"; bad $C ci
sed -i 's/^- \*\*Status:\*\* approved/- **Status:** implemented/' $S/spec.md
label="ci: done task with implemented spec passes"; ok $C ci

# ---- guard
rm -f agent-tracking/INDEX.md
label="guard: source edit with no task blocked"; code 2 pre app/main.py
label="guard: markdown allowed"; code 0 pre README.md
label="guard: specs/ allowed"; code 0 pre specs/001-export/spec.md
label="guard: agent-tracking/ allowed"; code 0 pre agent-tracking/INDEX.md
label="guard: .agents path allowed"; code 0 pre core/.agents/skills/x/SKILL.md
label="guard: outside project allowed"; code 0 pre /elsewhere/file.py
idx feature scoping
label="guard: unapproved (scoping) task blocked"; code 2 pre app/main.py
idx feature approved
label="guard: approved feature with spec row allowed"; code 0 pre app/main.py
sed -i 's/2026-01-01-feature-export/other/' $S/spec.md
label="guard: feature whose spec lacks the slug blocked"; code 2 pre app/main.py
sed -i 's/other/2026-01-01-feature-export/' $S/spec.md
mv $T/tasks.md $T/tasks.bak; printf '# Plan\n**Status:** awaiting-approval\n**Spec:** specs/001-export/spec.md\n' > $T/tasks.md
label="guard: plan not approved blocked"; code 2 pre app/main.py
mv $T/tasks.bak $T/tasks.md
mv $T/tasks.md $T/plan.md
label="guard: legacy plan.md name still accepted"; code 0 pre app/main.py
mv $T/plan.md $T/tasks.md
idx trivial in-progress
label="guard: trivial in-progress row allows edit"; code 0 pre app/main.py
label="guard: SDD_GUARD=off allows"; ( SDD_GUARD=off; export SDD_GUARD; rm -f agent-tracking/INDEX.md; code 0 pre app/main.py )

# ---- stop
idx feature in-progress; mv $T/progress.md $T/progress.bak; echo "no verdict" > $T/progress.md
label="stop: in-progress feature without verdict blocked"; code 2 stop false
label="stop: stop_hook_active allows"; code 0 stop true
mv $T/progress.bak $T/progress.md
label="stop: verdict present allows"; code 0 stop false
idx feature awaiting-approval
label="stop: awaiting-approval may stop"; code 0 stop false

# ---- install-hook
SK=$(basename "$(dirname "$here")"); IH=$R/.claude/skills/$SK/scripts; mkdir -p "$IH"; cp "$here"/*.sh "$IH"/
I="sh $IH/install-hook.sh"; ST=$R/.claude/settings.json; rm -f "$ST"
label="install-hook: fresh install exits 0"; code 0 $I
label="install-hook: both events registered"; [ "$(grep -c 'sdd-hook.sh' "$ST")" = 2 ] && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
cp "$ST" /tmp/st1.$$
label="install-hook: second run says already installed"; $I 2>&1 | grep -q "already installed" && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
label="install-hook: second run changes nothing"; ok cmp "$ST" /tmp/st1.$$
rm -f /tmp/st1.$$
printf '{"permissions":{"allow":["Bash(ls)"]},"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"echo hi"}]}]}}' > "$ST"
$I >/dev/null 2>&1
label="install-hook: keeps existing settings and hooks"; grep -q 'Bash(ls)' "$ST" && grep -q 'echo hi' "$ST" && grep -q 'sdd-hook.sh' "$ST" && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
label="install-hook: old file backed up"; ls "$R"/.claude/settings.json.bak-* >/dev/null 2>&1 && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
printf '{bad' > "$ST"
label="install-hook: invalid JSON refused"; code 1 sh "$IH/install-hook.sh"
cp "$ST" /tmp/st2.$$; $I >/dev/null 2>&1; label="install-hook: invalid JSON left untouched"; ok cmp "$ST" /tmp/st2.$$; rm -f /tmp/st2.$$
rm -f "$ST"; $I --dry-run >/dev/null 2>&1
label="install-hook: dry run writes nothing"; [ ! -e "$ST" ] && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
label="install-hook: script outside the project is refused"; code 2 sh "$here/install-hook.sh" "$R"

# ---- doctor
D=$R/doctor; mkdir -p $D; cd $D; export SDD_ROOT=$D
TM=$here/../templates/AGENTS.md; PF=$(basename "$(dirname "$here")"); PF=${PF%-workflow}
label="doctor: empty repo is not ready"; bad $C doctor
cp "$TM" AGENTS.md; printf '@AGENTS.md\n' > CLAUDE.md; mkdir -p specs agent-tracking; : > specs/constitution.md
label="doctor: set-up repo has no HIGH finding"; ok $C doctor
printf 'Run the tests with make test before every commit please.\n' >> AGENTS.md; printf 'Run the tests with make test before every commit please.\n' > CLAUDE.md; printf '@AGENTS.md\n' >> CLAUDE.md
label="doctor: line duplicated between CLAUDE.md and AGENTS.md reported"; $C doctor | grep -q 'also appear in AGENTS.md' && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
printf '@AGENTS.md\n' > CLAUDE.md; printf 'Always use the staging database for manual checks here.\n' >> AGENTS.md; printf 'Always use the staging database for manual checks here.\n' >> AGENTS.md
label="doctor: line repeated inside AGENTS.md reported"; $C doctor | grep -q 'more than once outside' && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
i=0; while [ $i -lt 8 ]; do printf 'note number %s\n' $i >> CLAUDE.md; i=$((i+1)); done
label="doctor: CLAUDE.md with extra lines reported"; $C doctor | grep -q 'lines besides the import' && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
printf '# notes\n' > CLAUDE.md
label="doctor: CLAUDE.md without the import is HIGH"; bad $C doctor
label="doctor: missing .gitignore block reported"; $C doctor | grep -q 'pack block missing' && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
cp "$here/../templates/gitignore.txt" .gitignore
label="doctor: current .gitignore block is clean"; $C doctor | grep -q 'gitignore' && { echo "FAIL $label"; fails=$((fails+1)); } || echo "PASS $label"
sed -i 's/^agent-tracking\/board\/$/agent-tracking\/other\//' .gitignore
label="doctor: stale .gitignore block reported"; $C doctor | grep -q 'pack block differs' && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
printf '@AGENTS.md\n' > CLAUDE.md; sed "s/<!-- $PF:start -->//; s/<!-- $PF:end -->//" "$TM" > AGENTS.md
label="doctor: AGENTS.md without markers is HIGH"; bad $C doctor
awk -v e="<!-- $PF:end -->" '$0==e{print "extra rule inside the block"} {print}' "$TM" > AGENTS.md
label="doctor: stale managed block reported"; $C doctor | grep -q 'managed block differs' && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
cd $R; export SDD_ROOT=$R

# ---- other agents: same policy, each agent's own stdin shape
rm -f agent-tracking/INDEX.md
t() { # label, want exit, stdout substring ("" = any), json
  label=$1; out=$(printf '%s' "$4" | $H 2>/dev/null); got=$?
  if [ "$got" = "$2" ] && { [ -z "$3" ] || printf '%s' "$out" | grep -q "$3"; }; then echo "PASS $label"; else echo "FAIL $label (exit $got, want $2; out: $out)"; fails=$((fails+1)); fi; }
PSRC='*** Begin Patch\n*** Update File: app/main.py\n@@\n-a\n+b\n*** End Patch'
PMD='*** Begin Patch\n*** Add File: agent-tracking/plans/x/scope.md\n+hi\n*** End Patch'
PMIX='*** Begin Patch\n*** Add File: specs/001-x/spec.md\n+hi\n*** Update File: app/main.py\n@@\n-a\n+b\n*** End Patch'
t "codex: apply_patch on source blocked" 2 "" "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"apply_patch\",\"cwd\":\"$R\",\"tool_input\":{\"command\":\"$PSRC\"}}"
t "codex: apply_patch on tracking files allowed" 0 "" "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"apply_patch\",\"cwd\":\"$R\",\"tool_input\":{\"command\":\"$PMD\"}}"
t "codex: patch mixing spec and source blocked" 2 "" "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"apply_patch\",\"cwd\":\"$R\",\"tool_input\":{\"command\":\"$PMIX\"}}"
t "codex: unparseable patch fails open" 0 "" "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"apply_patch\",\"cwd\":\"$R\",\"tool_input\":{\"command\":\"ls\"}}"
t "codex: session cwd in a subfolder finds the repo" 2 "" "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"apply_patch\",\"cwd\":\"$R/app\",\"tool_input\":{\"command\":\"$PSRC\"}}"
t "cursor: Write on source blocked with JSON deny" 2 '"permission": "deny"' "{\"hook_event_name\":\"preToolUse\",\"tool_name\":\"Write\",\"workspace_roots\":[\"$R\"],\"tool_input\":{\"path\":\"app/main.py\"}}"
t "cursor: Shell tool ignored" 0 "" "{\"hook_event_name\":\"preToolUse\",\"tool_name\":\"Shell\",\"workspace_roots\":[\"$R\"],\"tool_input\":{\"command\":\"ls\"}}"
t "gemini: write_file on source blocked" 2 "" "{\"hook_event_name\":\"BeforeTool\",\"tool_name\":\"write_file\",\"cwd\":\"$R\",\"tool_input\":{\"file_path\":\"$R/app/main.py\"}}"
t "gemini: write_file on markdown allowed" 0 "" "{\"hook_event_name\":\"BeforeTool\",\"tool_name\":\"write_file\",\"cwd\":\"$R\",\"tool_input\":{\"file_path\":\"$R/docs/a.md\"}}"
t "windsurf: pre_write_code on source blocked" 2 "" "{\"agent_action_name\":\"pre_write_code\",\"tool_info\":{\"file_path\":\"$R/app/main.py\"}}"
t "windsurf: pre_write_code on spec allowed" 0 "" "{\"agent_action_name\":\"pre_write_code\",\"tool_info\":{\"file_path\":\"$R/specs/001-x/spec.md\"}}"
t "copilot: preToolUse edit on source blocked with JSON deny" 2 'permissionDecision' "{\"hook_event_name\":\"preToolUse\",\"toolName\":\"edit\",\"cwd\":\"$R\",\"toolArgs\":\"{\\\"path\\\":\\\"app/main.py\\\"}\"}"
t "copilot: non-edit tool ignored" 0 "" "{\"hook_event_name\":\"preToolUse\",\"toolName\":\"bash\",\"cwd\":\"$R\",\"toolArgs\":\"{\\\"command\\\":\\\"ls\\\"}\"}"
mkdir -p agent-tracking; printf '| 2026-03-01 | 2026-03-01-feature-zz | feature | in-progress | y | |\n' > agent-tracking/INDEX.md
t "cursor: stop without verdict gets followup_message" 0 followup_message "{\"hook_event_name\":\"stop\",\"status\":\"completed\",\"loop_count\":0,\"workspace_roots\":[\"$R\"]}"
t "cursor: second loop lets it stop" 0 "" "{\"hook_event_name\":\"stop\",\"status\":\"completed\",\"loop_count\":1,\"workspace_roots\":[\"$R\"]}"
t "cursor: aborted run is not blocked" 0 "" "{\"hook_event_name\":\"stop\",\"status\":\"aborted\",\"loop_count\":0,\"workspace_roots\":[\"$R\"]}"
t "copilot: agentStop without verdict gets decision block" 0 '"decision": "block"' "{\"hook_event_name\":\"agentStop\",\"cwd\":\"$R\"}"
t "gemini: AfterAgent without verdict blocks" 2 "" "{\"hook_event_name\":\"AfterAgent\",\"cwd\":\"$R\",\"stop_hook_active\":false}"
t "gemini: AfterAgent honors stop_hook_active" 0 "" "{\"hook_event_name\":\"AfterAgent\",\"cwd\":\"$R\",\"stop_hook_active\":true}"
t "codex: Stop without verdict blocks" 2 "" "{\"hook_event_name\":\"Stop\",\"cwd\":\"$R\",\"stop_hook_active\":false}"
rm -f agent-tracking/INDEX.md
label="agent shapes: garbage JSON fails open"; t "$label" 0 "" "not json"

# ---- Copilot CLI as captured live: no event name in the JSON, the config entry passes pre|stop
th() { label=$1; out=$(printf '%s' "$4" | sh "$here/sdd-hook.sh" $5 2>/dev/null); got=$?
  if [ "$got" = "$2" ] && { [ -z "$3" ] || printf '%s' "$out" | grep -q "$3"; }; then echo "PASS $label"; else echo "FAIL $label (exit $got, want $2; out: $out)"; fails=$((fails+1)); fi; }
rm -f agent-tracking/INDEX.md
CPATCH="*** Begin Patch\\n*** Update File: $R/app/orders.py\\n@@\\n-a\\n+b\\n*** End Patch\\n"
th "copilot cli: apply_patch on source blocked, JSON deny" 2 permissionDecision "{\"sessionId\":\"s\",\"cwd\":\"$R\",\"toolName\":\"apply_patch\",\"toolArgs\":\"$CPATCH\"}" pre
th "copilot cli: apply_patch on a spec allowed" 0 "" "{\"sessionId\":\"s\",\"cwd\":\"$R\",\"toolName\":\"apply_patch\",\"toolArgs\":\"*** Begin Patch\\n*** Add File: $R/specs/001-x/spec.md\\n+hi\\n*** End Patch\\n\"}" pre
th "copilot cli: view and bash tools ignored" 0 "" "{\"sessionId\":\"s\",\"cwd\":\"$R\",\"toolName\":\"bash\",\"toolArgs\":{\"command\":\"ls\"}}" pre
printf '| 2026-03-01 | 2026-03-01-feature-zz | feature | in-progress | y | |\n' > agent-tracking/INDEX.md
th "copilot cli: agentStop hint without verdict blocks with decision" 0 '"decision": "block"' "{\"sessionId\":\"s\",\"cwd\":\"$R\"}" stop
rm -f agent-tracking/INDEX.md

# ---- install-hook for every agent
for ag in codex cursor copilot gemini windsurf; do
  label="install-hook: $ag fresh install exits 0"; code 0 $I --agent $ag
  label="install-hook: $ag second run changes nothing"; $I --agent $ag 2>&1 | grep -q 'already installed' && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
done
label="install-hook: codex file registers both events"; [ "$(grep -c 'sdd-hook.sh' "$R/.codex/hooks.json")" = 2 ] && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
label="install-hook: cursor file carries version 1"; grep -q '"version": 1' "$R/.cursor/hooks.json" && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
printf '{bad' > "$R/.gemini/settings.json"
label="install-hook: invalid gemini JSON refused"; code 1 $I --agent gemini
label="install-hook: unknown agent refused"; code 1 $I --agent nope

# ---- doctor: edit guard seen in any agent's file
D2=$R/doctor2; mkdir -p $D2/.codex; cd $D2; export SDD_ROOT=$D2
label="doctor: no agent guarded is reported"; $C doctor | grep -q 'edit guard not registered for any agent' && echo "PASS $label" || { echo "FAIL $label"; fails=$((fails+1)); }
printf '{"hooks":{"Stop":[{"hooks":[{"command":"x/sdd-hook.sh"}]}]}}' > .codex/hooks.json
label="doctor: a codex hook counts as guarded"; $C doctor | grep -q 'edit guard' && { echo "FAIL $label"; fails=$((fails+1)); } || echo "PASS $label"
cd $R; export SDD_ROOT=$R

[ "$fails" = 0 ] && { echo "all passed"; exit 0; } || { echo "$fails failed"; exit 1; }
