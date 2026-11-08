# Safe delivery

Every code change in a plan (feature, refactor, bug fix) is delivered so that
any step can be stopped, verified, and undone without drama. The goal is not
ceremony: it is that a reviewer can approve each step on its own, and that a
bad deploy is a five-minute revert, not an incident.

Use this when writing the **Steps** and **Delivery and rollback** sections of
`tasks.md`.

## 1. Small steps, each green

- Each step changes one thing and ends with the full verification passing
  (tests, types, lint). A red step is fixed before the next begins.
- Order steps so the risky, irreversible parts come last and depend on
  everything before them being proven.
- Prefer steps that are safe to deploy on their own: new code that is not yet
  called, a new column that is not yet read, a new endpoint behind auth that no
  client uses yet.

## 2. Expand → migrate → contract

Any change to something that another deployed component depends on — a table,
a column, an API field, an event schema, an env var — goes in three phases:

1. **Expand**: add the new thing alongside the old (new column nullable, new
   field optional, new endpoint). Old code still works.
2. **Migrate**: write to both / backfill / switch readers to the new thing.
   Backfills run in batches, are idempotent, and can resume.
3. **Contract**: remove the old thing only after nothing uses it — in a later,
   separate change.

Never rename or drop in one step. A rename is add + copy + switch + drop.

## 3. Migrations

- Every migration has a working `down`. Run `up`, `down`, `up` locally before
  calling the step done.
- No long table locks on large tables: add indexes concurrently where the
  database supports it; avoid adding `NOT NULL` with a default on huge tables
  in one statement.
- Data migrations are separate from schema migrations.

## 4. Feature flags — only when rollout risk warrants

A flag is justified when the change alters behaviour for existing users and
must be switched off faster than a deploy, or rolled out gradually. It is not
justified for a new endpoint no one calls yet.

When used: default **off**, read from the settings module, both paths tested,
and a follow-up task to delete the flag and the dead path recorded in
`progress.md`. A flag without a removal task is permanent complexity.

## 5. Blast radius

State in the plan who is affected if this change is wrong: one endpoint, one
tenant, all writes to a table, every request (middleware, auth, config). The
larger the radius, the smaller the steps and the stronger the verification
(extra characterization tests, a flag, a staged rollout).

## 6. Rollback recipe — concrete

"Revert the commit" is only a recipe when the change is pure code. Write the
real steps:

- code only: revert commit(s) `<which>`; no data impact.
- with migration: revert code first, then run `down` for `<migration id>`;
  data written in the meantime is `<kept / lost / needs X>`.
- with flag: set `<FLAG>=false`; no deploy needed.
- external side effects (emails sent, payments made): cannot be rolled back —
  say so, and say how they would be compensated.
