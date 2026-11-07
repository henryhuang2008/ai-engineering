# Release note style

## The four groups

Use these headings, in this order, and omit any group with no entries:

1. `### Added` - something that did not exist before.
2. `### Changed` - an existing behaviour works differently.
3. `### Fixed` - a bug the user could hit is gone.
4. `### Removed` - something that used to work no longer does.

`Removed` matters more than it looks: users forgive a new feature they do not
need, and do not forgive a feature that vanished without a line in the notes.

## Voice

- Second person or impersonal; never "we" alone. "You can now export a view",
  not "we added export".
- Present tense for what the release does, past tense only for the bug.
- One sentence per bullet. If it needs two, it is two changes.
- Name the surface (button, endpoint, flag) the user touches.

## Banned filler

These phrases make a note longer without making it clearer. The linter rejects
them:

- `various improvements` - names nothing; list them or drop the bullet.
- `performance improvements` - say what got faster, or drop it.
- `bug fixes and stability` - which bug, which instability.
- `minor changes` - minor to whom.
- `under the hood` - a user-facing note does not need the hood.

## Worked example

Input:

```text
fix: tokenizer split on hyphens
feat: export menu gets CSV
chore: bump ruff to 0.15
```

Output:

```markdown
### Added

- You can export the current view as CSV from the export menu.

### Fixed

- Search now matches hyphenated words such as `release-notes`.
```

The dependency bump is internal and is dropped. Nothing is said about the
tokenizer; the note names the effect the user sees.
