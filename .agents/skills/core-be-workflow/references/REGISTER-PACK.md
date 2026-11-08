# Register the pack

Paths are relative to the workflow skill folder.

So that the next agent follows these rules even when nobody invokes a skill,
make sure the repo root carries them. Agents such as Codex and Cursor read
`AGENTS.md` on their own; Claude Code reads `CLAUDE.md`, which imports it.
Do this on every non-trivial task; it is a no-op when nothing changed.

1. **No `AGENTS.md`** — copy `templates/AGENTS.md` to the repo root.
2. **`AGENTS.md` without the markers** `<!-- core-be:start -->` /
   `<!-- core-be:end -->` — append the template's marked block (markers
   included) below the existing content. Add the template's
   `## Project structure` section too if the file has none.
3. **Markers present** — replace only the text between them with the
   template's current block. Never edit anything outside the markers: the
   repo's own notes and `## Project structure` belong to the repo.
4. **`CLAUDE.md`** — missing: create it containing the single line
   `@AGENTS.md`. Present without that line: append `@AGENTS.md` once at the
   end. Never rewrite the rest of it.
5. Tell the user in one line what you created or updated, and log it in
   `progress.md`. These files are left for the user to commit.

6. **`.gitignore`** — keep scratch state out of git. Missing: create it from
   `templates/gitignore.txt`. Present without the `# core-be:start` / `# core-be:end` lines: append
   the template's block. Markers present: replace only the text between them. Never touch
   anything outside the markers.

7. **Edit guard.** Run `sdd-check.sh doctor`. It reports the guard as not registered for
   any agent, and the pack was not installed as a plugin? Tell the user once: "The edit
   guard is not registered. For each agent the team uses, run `sh <skills dir>/core-be-workflow/scripts/install-hook.sh --agent <claude|codex|cursor|copilot|gemini|windsurf>`."
   Never run it yourself: it edits the user's settings.

8. **Messy or duplicated files.** `AGENTS.md` and `CLAUDE.md` repeat each other, or
   `CLAUDE.md` holds more than the import? Do not patch them here. `core-be-init`
   consolidates them with the user: one source in `AGENTS.md`, an import in `CLAUDE.md`.
