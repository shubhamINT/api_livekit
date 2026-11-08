#!/bin/sh
# Registers sdd-hook.sh for the coding agents you use: each agent's own hook file
# in the project (PreToolUse-style edit guard + stop guard).
# For npx skills and manual installs; a Claude Code plugin install already ships its hook.
# usage: sh install-hook.sh [--agent claude|codex|cursor|copilot|gemini|windsurf]... [--all] [--dry-run] [project-dir]
# No --agent means claude. Merges, never overwrites: other settings and hooks are
# kept, an invalid file is left untouched, the old file is backed up, and a second
# run changes nothing.
set -u
dry=0; proj=; agents=
for a in "$@"; do
  case $a in
    --dry-run) dry=1 ;;
    --all) agents="claude codex cursor copilot gemini windsurf" ;;
    --agent=*) agents="$agents ${a#--agent=}" ;;
    --agent) want=1 ;;
    -*) echo "install-hook: unknown option $a" >&2; exit 2 ;;
    *) if [ "${want:-0}" = 1 ]; then agents="$agents $a"; want=0; else proj=$a; fi ;;
  esac
done
[ -n "$agents" ] || agents=claude
proj=$(cd "${proj:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}" && pwd) || exit 2
here=$(cd "$(dirname "$0")" && pwd)
case $here in
  "$proj"/*) rel=${here#"$proj"/} ;;
  *) echo "install-hook: $here is outside $proj. A plugin install already has the hook; nothing to do." >&2; exit 2 ;;
esac
command -v python3 >/dev/null 2>&1 || { echo "install-hook: python3 missing. Add the hook by hand: see the pack README, Enforcement." >&2; exit 2; }
skill=$(basename "$(dirname "$here")")
SDD_PROJ=$proj SDD_REL=$rel/sdd-hook.sh SDD_SKILL=$skill SDD_DRY=$dry SDD_AGENTS=$agents python3 - <<'PY'
import json, os, shutil, sys, time
proj, rel, skill = os.environ['SDD_PROJ'], os.environ['SDD_REL'], os.environ['SDD_SKILL']
dry = os.environ['SDD_DRY'] == '1'
suffix = skill + '/scripts/sdd-hook.sh'
# Fail open: sh exits 2 (= block) when the script is missing, so test the file first.
# The wrapper finds the repo root itself: agents run hooks from the session cwd, not always the root.
def wrapper(hint=''):
    return ("sh -c 'r=$(git rev-parse --show-toplevel 2>/dev/null || pwd); "
            "[ -f \"$r/%s\" ] && exec sh \"$r/%s\"%s; exit 0'") % (rel, rel, (' ' + hint) if hint else '')
wrap = wrapper()
claude_entry = {'type': 'command', 'command': 'sh',
                'args': ['-c', '[ -f "$1" ] && exec sh "$1"; exit 0', 'sdd-hook', '${CLAUDE_PROJECT_DIR}/' + rel],  # braces: only ${NAME} is expanded
                'timeout': 15}
# nested = {event: [{matcher?, hooks: [entry]}]}; flat = {event: [entry]}
AG = {
  'claude':   dict(file='.claude/settings.json', shape='nested', version=None, entry=claude_entry,
                   events=[('PreToolUse', 'Write|Edit|MultiEdit|NotebookEdit'), ('Stop', None)],
                   note='Run /hooks in Claude Code to confirm; it may ask you to trust the project hooks.'),
  'codex':    dict(file='.codex/hooks.json', shape='nested', version=None,
                   entry={'type': 'command', 'command': wrap, 'timeout': 15},
                   events=[('PreToolUse', 'apply_patch|Edit|Write'), ('Stop', None)],
                   note='Codex: run /hooks and trust the new hook. The project .codex/ layer must be trusted.'),
  'gemini':   dict(file='.gemini/settings.json', shape='nested', version=None,
                   entry={'type': 'command', 'command': wrap, 'timeout': 15000},
                   events=[('BeforeTool', 'write_file|replace'), ('AfterAgent', None)],
                   note='Gemini CLI: trust the project hook when it asks (/hooks panel).'),
  'cursor':   dict(file='.cursor/hooks.json', shape='flat', version=1,
                   entry={'type': 'command', 'command': wrap, 'timeout': 15},
                   events=[('preToolUse', 'Write'), ('stop', None)],
                   note='Cursor: the workspace must be trusted. Hooks run in the editor agent; CLI support is partial.'),
  'copilot':  dict(file='.github/hooks/sdd-guard.json', shape='flat', version=1,
                   entry={'type': 'command', 'bash': wrap, 'timeoutSec': 15}, hints={'preToolUse': 'pre', 'agentStop': 'stop'},
                   events=[('preToolUse', None), ('agentStop', None)],
                   note='Copilot: the CLI in prompt mode needs --trust-folder (or a trusted folder); the cloud agent reads hook files only from the default branch, so merge this file there.'),
  'windsurf': dict(file='.devin/hooks.json', shape='flat', version=None,
                   entry={'command': wrap, 'show_output': True},
                   events=[('pre_write_code', None)],
                   note='Windsurf has no stop hook, so only the edit guard runs. Hooks do not run in Restricted Mode.'),
}
def die(msg): sys.exit(msg)

def install_json(name, spec):
    path = os.path.join(proj, spec['file'])
    data = {}
    if os.path.exists(path):
        try: data = json.load(open(path))
        except Exception as e: die('install-hook: %s is not valid JSON (%s). Fix it first; nothing written.' % (path, e))
    if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
        die('install-hook: %s has an unexpected shape (top level and "hooks" must be objects); nothing written.' % path)
    if spec['version'] is not None: data.setdefault('version', spec['version'])
    hooks = data.setdefault('hooks', {})
    added, kept = [], []
    for event, matcher in spec['events']:
        lst = hooks.setdefault(event, [])
        if not isinstance(lst, list): die('install-hook: hooks.%s in %s is not a list; nothing written.' % (event, path))
        if suffix in json.dumps(lst): kept.append(event); continue
        if spec['shape'] == 'nested':
            block = {'hooks': [dict(spec['entry'])]}
            if matcher: block['matcher'] = matcher
        else:
            block = dict(spec['entry'])
            if spec.get('hints'): block['bash'] = wrapper(spec['hints'][event])
            if matcher: block['matcher'] = matcher
        lst.append(block); added.append(event)
    if not added:
        print('install-hook: %s already installed (%s); nothing changed.' % (name, ', '.join(kept))); return
    out = json.dumps(data, indent=2) + '\n'
    if dry:
        print('install-hook: dry run, would write %s:\n%s' % (path, out)); return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        bak = path + '.bak-' + time.strftime('%Y%m%d%H%M%S'); shutil.copy2(path, bak)
        print('install-hook: backed up the old file to %s' % bak)
    open(path, 'w').write(out)
    print('install-hook: %s: added %s -> %s' % (name, ' and '.join(added), spec['file']))
    print('  ' + spec['note'])

for name in os.environ['SDD_AGENTS'].split():
    if name in AG: install_json(name, AG[name])
    else: die('install-hook: unknown agent %r. Use claude, codex, cursor, copilot, gemini, or windsurf. Other agents are covered by AGENTS.md and CI.' % name)
PY
