# Lint rules

Ported from `langchain-ai/langchain-skills` `scripts/lint_skills.py`. The
numbers are that repository's; the description rules are this example's
addition. `BLOCK` fails the command; `WARN` prints and exits 0.

| Rule | Severity | Check | Why |
| --- | --- | --- | --- |
| `frontmatter` | BLOCK | `SKILL.md` starts with `---`, and the block closes | Without it there is no name or description to catalog |
| `name` | BLOCK | `name` is present | The catalog is keyed by it |
| `name-mismatch` | BLOCK | `name` equals the directory name | Two sources of truth otherwise; both runtimes assume they agree |
| `name-format` | BLOCK | lowercase letters, digits, single hyphens | The spec's character set; keeps ids stable in tool calls |
| `name-length` | BLOCK | `<= 64` characters | Spec limit; long names cost catalog tokens |
| `description` | BLOCK | `description` is present | It is the only text the model sees before loading |
| `description-length` | BLOCK | `<= 1024` characters | Spec limit |
| `description-budget` | WARN | `<= 400` characters | A description is always-on prompt; two sentences is usually enough |
| `no-trigger` | WARN | says when to use it (`use when`, `when the user`, ...) | A description that only says what it does does not help selection |
| `body-size` | BLOCK | body `<= 600` lines | Hard cap: a skill that large should be split |
| `body-size` | WARN | body `<= 500` lines | Target, from the upstream linter |
| `language-split` | WARN | `> 150` lines of one language inline without `references/` | Move long code out; load it only when needed |
| `on-invoke-budget` | WARN | body `<= ~6000` tokens (chars / 4) | Loading a skill should cost a page, not a file |
| `dead-link` | WARN | local Markdown links resolve inside the skill | A skill that points at a missing file is a broken instruction |
| `pipe-to-shell` | WARN | no `curl ... \| bash` | A skill is executable content; do not teach it to run remote code |
| `model-id` | WARN | model ids are in the allowlist | Stale ids in instructions rot silently |
| `duplicate-description` | WARN | no two skills share a description | The catalog must be distinguishable |
| `catalog-budget` | WARN | library catalog `<= ~1200` tokens | The always-on cost of the whole library |

## What is deliberately not checked

- Whether the instructions are correct, or whether the model selects the skill.
  That needs an eval, not a linter.
- Whether a script is safe. A linter reads text; it cannot sandbox execution.
- Frontmatter fields beyond `name` and `description`. They are accepted and
  inert, exactly as the runtime treats them.

## Run it

```shell
uv run python main.py lint                 # human output, exit 1 on BLOCK
uv run python main.py lint --json          # machine output
```

The broken fixture under `fixtures/broken-library/` exists so the rules have
something to fire on:

```shell
uv run python -c "from pathlib import Path; from app.lint import lint_library; [print(f.format(Path('.'))) for f in lint_library(Path('fixtures/broken-library'))]"
```
