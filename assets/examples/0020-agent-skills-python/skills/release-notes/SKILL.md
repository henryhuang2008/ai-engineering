---
name: release-notes
description: Turn a list of merged changes into release notes for the changelog. Use when the user provides commit messages, a PR list or a raw change log and asks for a release summary, a changelog entry or notes for users rather than developers.
---

# Release notes

## When to use this skill

Use it when the input is a set of changes and the output is prose for people who
use the software: a changelog section, a "what's new" paragraph, or an email
blurb. Do not use it for commit-message style changelogs aimed at maintainers,
and do not invent changes that are not in the input.

## Workflow

1. Read `references/style.md`. It is short, and it decides the shape of every
   entry.
2. Group the changes by user-visible effect, not by file or commit order:
   added, changed, fixed, removed. Drop internal-only changes unless the user
   asked for a full log.
3. Draft the note with one heading per group and one bullet per change.
4. Validate the draft before returning it, passing the whole note as `--text`:

   ```bash
   python ${SKILL_DIR}/scripts/lint_notes.py --text "<the draft>" --json
   ```

   Pass it inline. This runtime gives the agent no file-write tool, so a
   workflow that says "save the draft, then lint the file" cannot be completed.

5. Fix every reported problem and run the check again. Return the note only
   when the check exits 0.

## Rules

- Lead with the effect on the user, not the implementation. "Search now
  matches partial words" beats "rewrote the tokenizer".
- Keep one change per bullet. Split a bullet that needs "and" to describe two
  different changes.
- Never claim a fix for a bug the input does not name.
- If the input contains no user-visible change, say so instead of padding.

## Files

- `scripts/lint_notes.py` - checks headings, bullets and banned filler.
- `references/style.md` - the four groups, voice and the banned phrases.
