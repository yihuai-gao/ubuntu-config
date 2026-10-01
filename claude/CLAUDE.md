# Global rules (all projects)

## Skill edits must sync to ~/ubuntu-config

Whenever you update a skill under `~/.claude/skills/` (e.g. `static-review` — the review skill),
copy the updated files to the mirror at `~/ubuntu-config/claude/skills/<skill-name>/` in the same
pass and verify with `diff -q`. The ubuntu-config repo is the portable source of truth for these
skills (`~/ubuntu-config/claude/install_skills.sh` installs them on new machines); an unsynced
edit is lost on the next machine setup. Do not commit in `~/ubuntu-config` unless the user
explicitly asks — leave the change in the working tree and mention it is uncommitted.
