# Release Notes Workflow for Master Pushes

This repository enforces detailed English release notes before pushing to `master`.

## One-time setup

Run:

```bash
bash tools/install_hooks.sh
```

This configures `core.hooksPath` to `.githooks` so the local `pre-push` hook is active.

## What happens on `git push origin master`

1. The hook checks whether a release notes file for the exact `HEAD` commit is already committed.
2. If missing, it generates:

```text
release-notes/master-<head-sha-12>.md
```

3. Push is blocked until you review and commit that file.

## Manual generation (optional)

You can generate release notes yourself:

```bash
python3 tools/release_notes/generate_release_notes.py \
  --base <base-commit-or-ref> \
  --head <head-commit-or-ref> \
  --output release-notes/manual-note.md
```

The generated notes include:
- summary metrics
- change areas
- change type breakdown
- commit-by-commit details with file-level diff stats
