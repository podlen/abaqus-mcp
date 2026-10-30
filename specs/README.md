# Specs

One file per goal. A spec says what "done" means before anyone starts, so two people (and their
Claude sessions) work toward the same checks.

| file | state |
|---|---|
| `NNN-<slug>.md` | draft, agreed or in progress |
| `done/NNN-<slug>.md` | finished; its Log says what passed |
| `backlog.md` | gaps and ideas not yet in a spec |

## Flow
1. Write `NNN-<slug>.md` from `TEMPLATE.md` (next free number). Status `draft`.
2. Both of us read it. Open points get answered in the file. Status `agreed`.
3. Work on a branch named after the spec (`NNN-<slug>`). The PR names the spec and the criteria it meets.
   Two release branches: `linux` (VM setup: `setup.sh`, `bin/`, `vm/`) and `windows` (native setup:
   `setup-windows.*`). A platform file lives on its branch only. A shared change (src, tests, skills,
   specs, docs) is merged into one branch and cherry-picked onto the other.
4. Each check that passes gets a dated line in the spec's Log. A criterion changes only with a
   `(source: <name>, <date>)` mark.
5. When every criterion passes, move the file to `done/` in the last PR of the goal.

Facts about one person's machine (paths, network, other VMs) stay out of specs: keep them in the
git-ignored `.team/local.md`. Design reasons go to `docs/decisions.md`.

With Claude Code: point `.critic/spec.md` at the active spec (`ln -sf ../specs/NNN-<slug>.md .critic/spec.md`);
reviews in `.critic/` stay local, their verdicts go into the Log.
