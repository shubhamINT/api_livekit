# README Standard

The README is part of the deliverable, not an afterthought. **A structure,
endpoint, or configuration change is not complete until the README reflects it
in the same change.**

A section with nothing to say is omitted, never faked: no envelope, Docker, or
Licence section for a repo that has none. Note `N/A` once in `research/<slug>.md`
under README gaps.

Required sections, in order:

1. **Title + what it is** — one paragraph, plus the core model/concepts if the
   service has a non-obvious one
2. **Response envelope** — the shape every endpoint returns
3. **Requirements** — runtime version (Python / Node), package manager, external
   services (DB, queues, upstreams)
4. **Installation** — local (`uv sync` + dev server, or `npm ci` + `npm run dev`)
   *and* Docker
5. **Environment** — table of every variable: name, default, note. Must match the
   settings module and `.env.example` exactly
6. **Endpoints** — quick-reference table: method, path, auth, purpose
7. **Project Structure** — the directory tree with a one-line comment per entry,
   matching the `## Project structure` section in `AGENTS.md`
8. **Data stores** — collections/tables, what keys them, what they hold
9. **Stack** — layer → technology table
10. **Licence** — name the repo's licence and point to `LICENSE`

Rules: if it exists, read it before changing anything. If it is missing, create
it. After any change, re-check the **whole** README for staleness — environment
variables, endpoints, and the structure tree drift first and fastest.
