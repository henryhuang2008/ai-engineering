# Runtime notes — what was verified, and what broke

Everything here was observed on this machine (Windows 11, Python 3.12, the
versions in `pyproject.toml`) by running the code, not read from a changelog.

## The harness pin

`pydantic-ai-skills` 2.1.1 delegates discovery to `pydantic-ai-harness`. From
harness 0.52 it builds a `LocalWorkspaceBackend` at construction time:

```text
NotImplementedError: `LocalWorkspaceBackend` only supports POSIX platforms at
the moment: its timeout contract kills the whole process group.
```

That is raised by `SkillsCapability('skills')` before any model call, so on
Windows the current release cannot be constructed at all. This project pins
`pydantic-ai-harness<0.52` (resolves to 0.36.0). On Linux or macOS, remove the
pin to run the current harness; the code in `app/` does not change.

`app/runtime.py` still catches `NotImplementedError` and raises
`RuntimeUnavailable` with that explanation, so an upgraded install fails with a
sentence instead of a stack trace.

## The catalog is level 1, and it is instructions

Before any skill loads, the model sees:

```text
<context id="capability:deferred_capabilities">
The following capabilities are deferred and can be loaded using the `load_capability` tool...
- csv-insights: Profile a CSV file...
- release-notes: Turn a list of merged changes...
</context>
```

One line per skill. No body, no file list. `main.py verify` prints exactly this.

## Loading is a context block, not a tool result

`load_capability(id='csv-insights')` adds the skill's body as a
`<context id="capability:csv-insights">` block in the next request, with
`${SKILL_DIR}` replaced by the absolute skill directory. That is why the
`scripts/` path in `SKILL.md` works from any working directory.

## Scripts run in the skill's `scripts/` directory

The default `LocalSkillScriptExecutor` sets `cwd` to the script's parent. A
relative `--csv data/sales.csv` therefore resolves under
`skills/csv-insights/scripts/`, not under the project root.

Two consequences this example handles:

1. The system prompt carries the process working directory and tells the model
   to make paths absolute before calling a script.
2. The CLI uses the same executor, so `run-script` behaves exactly like the
   agent path.

## Shebangs beat the interpreter

The executor prefers the script's shebang. `#!/usr/bin/env python3` resolves to
`python3`, which is not on PATH on a default Windows install; the script exits
with code 9009 and no message. These scripts have no shebang, so the executor
falls back to the interpreter running the agent.

## Script arguments are named flags

`args` is a mapping, not a list: `{"csv": "..."}` becomes `--csv ...`.
`True` emits the flag alone, `False`/`None` omits it, and a list repeats the
flag. There is no positional-argument form, which is why both scripts use
`--name value`.

## `require_loaded` is the boundary

With the default `require_loaded=True`, a file call before loading is refused
with a `ModelRetry`:

```text
Skill 'csv-insights' is not loaded. Call load_capability with id='csv-insights'
first, then read its files.
```

The model sees that text and can correct itself. Set `REQUIRE_LOADED=0` to
allow direct file access; the tests cover both.

## The release-notes workflow bug

The first live run of the second skill failed in an instructive way. The skill
said "write the draft to a file, then run `lint_notes.py --file draft.md`". The
agent has no file-write tool — only `load_capability`, `read_skill_resource`
and `run_skill_script` — so the step was impossible, and the model said so
instead of pretending.

The fix is in the skill, not the agent: `lint_notes.py` accepts `--text` and
the instructions tell the model to pass the draft inline. A skill's workflow
must fit the tool surface the runtime actually provides.

## Not verified

- Sandboxed execution. The default executor runs scripts on the host. The
  package ships sandbox executors; this example does not exercise them.
- Git and S3 registries. `SkillsCapability(registries=[...])` is documented and
  not used here.
- Current harness on Windows. The pin is the workaround, not a fix.
