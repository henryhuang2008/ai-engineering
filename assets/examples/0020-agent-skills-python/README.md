# Agent Skills in Python — author, lint, run

A working example of [Agent Skills](https://agentskills.io/specification) in
Python: a two-skill library in the portable `SKILL.md` format, a linter ported
from [langchain-ai/langchain-skills](https://github.com/langchain-ai/langchain-skills),
and a runtime built on
[`pydantic-ai-skills`](https://github.com/DougTrajano/pydantic-ai-skills) where
each skill is a deferred capability the model loads on demand.

The claim worth testing is the format's: a skill library can grow without every
skill paying for context. The catalog below is what the model sees before it
decides to load anything.

## Layout

```text
skills/                      # the library: a directory of skill packages
├── csv-insights/
│   ├── SKILL.md             # name + description + instructions
│   ├── references/metrics.md
│   └── scripts/{profile,aggregate}.py
└── release-notes/
    ├── SKILL.md
    ├── references/style.md
    └── scripts/lint_notes.py
app/
├── skills.py                # parse frontmatter, discover, catalog, token estimate
├── lint.py                  # 18 rules, BLOCK/WARN, no runtime import
├── runtime.py               # SkillsCapability + Pydantic AI agent
└── cli.py                   # lint | catalog | verify | ask | run-script
fixtures/broken-library/     # a skill that fails the linter on purpose
tests/                       # 34 tests, no network, no key
docs/{lint-rules,runtime-notes}.md
data/sales.csv               # the CSV the skill scripts operate on
```

## Run it

```shell
cp .env.example .env          # set OPENAI_API_KEY (DeepSeek works)
uv sync

uv run python main.py lint
uv run python main.py catalog
uv run python main.py verify
uv run python main.py run-script csv-insights profile.py --set csv=/abs/path/data/sales.csv
uv run python main.py ask "Using data/sales.csv, how many rows are there and what is the mean amount?"
uv run pytest -q
```

`lint`, `catalog`, `verify`, `run-script` need no model. `verify` builds the
capability with a scripted model and prints the tools and catalog; it is a
structural check, not a quality check.

## What the model sees

Level 1, always on (~128 tokens for two skills):

```text
- csv-insights: Profile a CSV file and answer questions about its columns...
- release-notes: Turn a list of merged changes into release notes...
```

Level 2, after `load_capability('csv-insights')`: the body, with `${SKILL_DIR}`
resolved to the real directory.

Level 3, on demand: `read_skill_resource('csv-insights', 'references/metrics.md')`
and `run_skill_script('csv-insights', 'scripts/profile.py', {...})`.

## The linter

Full table in [`docs/lint-rules.md`](docs/lint-rules.md). The gates that matter
most:

- `name` must equal the directory name, and use lowercase letters, digits and
  single hyphens;
- body `> 600` lines blocks, `> 500` warns;
- `> 150` lines of inline code with no `references/` warns;
- descriptions must say *when* to use the skill, and two skills may not share
  one;
- dead local links, `curl | bash`, and stale model ids warn.

The real library lints clean; the fixture reports one block and four warnings.

## What was verified

- Both skills load, list their bundled files, and answer live questions through
  DeepSeek `deepseek-chat`.
- `csv-insights` on `data/sales.csv`: the model loaded the skill, read
  `references/metrics.md`, ran `profile.py`, and reported `10` rows and the mean
  `236.1377777777778` with the missing count — the skew rule from the reference
  applied without being asked.
- `release-notes`: the model drafted the note, dropped the internal `chore`, and
  ran `lint_notes.py --text ...` to a clean result.
- `require_loaded` refuses file access before a load, with the error text the
  model can act on.
- 34 tests pass with no network, no database and no provider key.

## What is not

- **Current harness on Windows.** `pydantic-ai-harness >= 0.52` builds a
  POSIX-only `LocalWorkspaceBackend`, so `SkillsCapability` cannot be
  constructed on Windows. This project pins `< 0.52` and documents the error in
  [`docs/runtime-notes.md`](docs/runtime-notes.md). Remove the pin on
  Linux/macOS.
- **Sandboxing.** The default executor runs skill scripts on the host. A skill
  is code; only install libraries you trust.
- **Registries.** Git and S3 skill registries are documented by the package and
  not exercised here.
- **Selection quality.** No eval for "did the model load the right skill".
  Distinct descriptions make selection possible, not correct.
- **Skill authoring by the agent.** This example reads skills; it does not let
  an agent write one. That is a separate trust problem.

## The two sources

- [langchain-ai/langchain-skills](https://github.com/langchain-ai/langchain-skills)
  — a 21-skill library for coding agents, plus the lint script this example
  ports. It is the authoring reference: how big a skill may get, how to split
  references, what a description must contain.
- [DougTrajano/pydantic-ai-skills](https://github.com/DougTrajano/pydantic-ai-skills)
  — the runtime: `SkillsCapability`, deferred capabilities, the two bundled-file
  tools, registries and sandbox executors.
