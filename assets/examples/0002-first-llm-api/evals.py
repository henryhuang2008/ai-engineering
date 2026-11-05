"""Self-tests for 0002-first-llm-api.

No fake model: the lab talks to live DeepSeek. These checks cover everything that
does not need the network (message shapes, tool schema, pydantic contract, model
wiring, the missing-key instructions), plus one live smoke call when a key is set.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import langchain_lab as lab
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

HERE = Path(__file__).resolve().parent
PY = sys.executable
CHECKS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    CHECKS.append(name)


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEEPSEEK_")}
    env.pop("OPENAI_API_KEY", None)
    return env


def run_lab(env: dict[str, str], timeout: int = 90):
    return subprocess.run(
        [PY, "langchain_lab.py"],
        cwd=HERE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def with_env(values: dict[str, str]):
    """Temporarily set env vars, then restore exactly."""

    class _Ctx:
        def __enter__(self):
            self.old = os.environ.copy()
            os.environ.update(values)

        def __exit__(self, *args):
            os.environ.clear()
            os.environ.update(self.old)

    return _Ctx()


# --- tests -----------------------------------------------------------------


def test_ticket_schema() -> None:
    schema = lab.SupportTicket.model_json_schema()
    props = schema["properties"]
    check("category is an enum", props["category"]["enum"] == ["billing", "bug", "question"])
    check("urgency has 1..5 bounds", props["urgency"]["minimum"] == 1 and props["urgency"]["maximum"] == 5)
    check("order_id is optional", "order_id" not in schema.get("required", []))
    check("summary required", "summary" in schema.get("required", []))


def test_ticket_validation() -> None:
    ticket = lab.SupportTicket(
        category="billing", urgency=5, summary="Duplicate charge.", order_id="A-1042"
    )
    check("valid ticket accepted", ticket.order_id == "A-1042")
    for bad in ({"category": "billing", "urgency": 9, "summary": "x"},
                {"category": "other", "urgency": 1, "summary": "x"}):
        try:
            lab.SupportTicket(**bad)
        except Exception:
            check(f"rejects {bad.get('urgency', bad.get('category'))}", True)
        else:
            check(f"rejects {bad}", False)


def test_tool_contract() -> None:
    schema = lab.get_order_status.args_schema.model_json_schema()
    check("tool name", lab.get_order_status.name == "get_order_status")
    check("tool takes order_id", schema.get("required") == ["order_id"])
    check("tool description mentions status", "status" in lab.get_order_status.description.lower())
    check("fixture returns a status", lab.get_order_status.invoke({"order_id": "A-1042"}).startswith("shipped"))
    check("fixture handles unknown ids", "no order found" in lab.get_order_status.invoke({"order_id": "X-1"}))


def test_message_protocol() -> None:
    messages = [SystemMessage(content=lab.SYSTEM), HumanMessage(content=lab.QUESTION_1)]
    check("turn 1 has 2 messages", len(messages) == 2)
    check("roles are system + human", [m.type for m in messages] == ["system", "human"])
    reply = AIMessage(content="Send us the invoice number.")
    thread = messages + [reply, HumanMessage(content=lab.QUESTION_2)]
    check("turn 2 has 4 messages", len(thread) == 4)
    check("history includes the AI reply", thread[2].type == "ai")


def test_model_config() -> None:
    with with_env({"DEEPSEEK_API_KEY": "test-key"}):
        model = lab.build_model()
    check("live model class", type(model).__name__ == "ChatDeepSeek", type(model).__name__)
    check("default model name", model.model_name == "deepseek-flash", model.model_name)
    check("default base url", str(model.root_client.base_url).rstrip("/") == "https://api.deepseek.com")
    check("temperature zero", model.temperature == 0)
    check(
        "thinking disabled for the lab",
        model.extra_body == {"thinking": {"type": "disabled"}},
        str(model.extra_body),
    )


def test_model_overrides() -> None:
    with with_env({
        "DEEPSEEK_API_KEY": "test-key",
        "DEEPSEEK_MODEL": "deepseek-v4-pro",
        "DEEPSEEK_BASE_URL": "https://example.test",
    }):
        model = lab.build_model()
    check("model override", model.model_name == "deepseek-v4-pro", model.model_name)
    check("base url override", str(model.root_client.base_url).rstrip("/") == "https://example.test")


def test_missing_key() -> None:
    result = run_lab(clean_env())
    check("no key exits 1", result.returncode == 1, str(result.returncode))
    check("shows session command", '$env:DEEPSEEK_API_KEY = "sk-..."' in result.stderr, result.stderr)
    check("shows persist command", "setx DEEPSEEK_API_KEY" in result.stderr, result.stderr)
    check("shows key page", "platform.deepseek.com/api_keys" in result.stderr, result.stderr)
    check("no banner before failing", "live model" not in result.stdout, result.stdout)


def test_no_fake_model() -> None:
    check("no FakeDeepSeek in the lab", not hasattr(lab, "FakeDeepSeek"))
    source = (HERE / "langchain_lab.py").read_text(encoding="utf-8")
    check("lab has no scripted branch", "--real" not in source and "scripted" not in source.lower())


def test_live_smoke() -> tuple[bool, str]:
    if not os.getenv("DEEPSEEK_API_KEY"):
        return False, "skipped (no DEEPSEEK_API_KEY)"
    model = lab.build_model()
    reply = model.invoke(
        [SystemMessage(content="Answer in one sentence."), HumanMessage(content="Say hello.")]
    )
    check("live reply is an AIMessage", isinstance(reply, AIMessage), type(reply).__name__)
    check("live reply has text", bool(str(reply.content).strip()))
    return True, "ran one live call"


def test_uv_project() -> None:
    """The uv project is the single source of dependencies; keep it honest."""
    pyproject = HERE / "pyproject.toml"
    check("pyproject.toml exists", pyproject.exists())
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    declared = {
        re.split(r"[<>=!~ ]", dep, maxsplit=1)[0]
        for dep in data["project"]["dependencies"]
    }
    check(
        "declares langchain, langchain-deepseek, pydantic",
        {"langchain", "langchain-deepseek", "pydantic"} <= declared,
        str(sorted(declared)),
    )


TESTS = [
    ("ticket schema", test_ticket_schema),
    ("ticket validation", test_ticket_validation),
    ("tool contract", test_tool_contract),
    ("message protocol", test_message_protocol),
    ("model config", test_model_config),
    ("model overrides", test_model_overrides),
    ("missing key instructions", test_missing_key),
    ("no fake model", test_no_fake_model),
    ("uv project", test_uv_project),
]


def main() -> int:
    failures = 0
    for index, (name, test) in enumerate(TESTS, start=1):
        try:
            test()
            print(f"ok {index:02d} {name}")
        except Exception as error:  # noqa: BLE001 - a test runner reports everything
            failures += 1
            print(f"FAIL {index:02d} {name}: {error}")

    try:
        ran, note = test_live_smoke()
    except Exception as error:  # noqa: BLE001
        failures += 1
        print(f"FAIL 10 live smoke: {error}")
    else:
        print(f"ok 10 live smoke: {note}")
        if not ran:
            print("     set DEEPSEEK_API_KEY to include the live call")

    total = len(CHECKS)
    print(f"\n{total} checks passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
