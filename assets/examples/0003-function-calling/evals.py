"""Self-tests for 0003-function-calling.

No fake model: both scripts talk to live DeepSeek. Everything here runs offline -
tool contracts, the catalog, tool execution and error handling, the hand-written
loop's control flow and the framework-owned agent loop (both driven by a test
double defined below, not by the scripts), the missing-key instructions, the uv
project - plus live smoke checks when a key is set.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import agent_call
import function_calling_lab as lab
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

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
        [PY, "function_calling_lab.py"],
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


class _StubBound:
    """Answers the loop with pre-built AIMessages; records what it was sent."""

    def __init__(self, replies: list[AIMessage]) -> None:
        self.replies = list(replies)
        self.sent: list[list] = []

    def invoke(self, messages):
        self.sent.append(list(messages))
        return self.replies.pop(0) if self.replies else AIMessage(content="done")


class StubModel:
    """Test double for the loop's control flow. The lab itself has no fake model."""

    def __init__(self, replies: list[AIMessage]) -> None:
        self.bound = _StubBound(replies)
        self.tools: list = []

    def bind_tools(self, tools, **kwargs):
        self.tools = list(tools)
        return self.bound


def call_message(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


# --- tests -----------------------------------------------------------------


def test_fixture() -> None:
    check("two tickets in the fixture", len(lab.TICKETS) == 2, str(sorted(lab.TICKETS)))
    check("T-1001 refundable", lab.TICKETS["T-1001"]["refundable"] is True)
    check("T-1002 not refundable", lab.TICKETS["T-1002"]["refundable"] is False)


def test_tool_contracts() -> None:
    check("tool count", len(lab.TOOLS) == 2, str(len(lab.TOOLS)))
    check("registry keys", sorted(lab.REGISTRY) == ["get_ticket_status", "issue_refund"])

    lookup = lab.get_ticket_status.args_schema.model_json_schema()
    check("lookup name", lab.get_ticket_status.name == "get_ticket_status")
    check("lookup takes ticket_id", lookup.get("required") == ["ticket_id"])
    check("lookup description names the id", "id" in lab.get_ticket_status.description.lower())

    refund = lab.issue_refund.args_schema.model_json_schema()
    check("refund takes two args", sorted(refund.get("required", [])) == ["amount_usd", "ticket_id"])
    check(
        "refund description carries policy",
        "check the status first" in lab.issue_refund.description.lower(),
    )


def test_tool_behaviour() -> None:
    status = lab.get_ticket_status.invoke({"ticket_id": "T-1001"})
    check("lookup returns a dict", isinstance(status, dict), type(status).__name__)
    check("lookup reports open", status["status"] == "open", str(status))
    check(
        "lookup handles unknown ids",
        "error" in lab.get_ticket_status.invoke({"ticket_id": "T-9999"}),
    )

    ok = lab.issue_refund.invoke({"ticket_id": "T-1001", "amount_usd": 20})
    check("refund runs for T-1001", ok == {"refunded_usd": 20, "ticket": "T-1001"}, str(ok))
    refused = lab.issue_refund.invoke({"ticket_id": "T-1002", "amount_usd": 20})
    check("refund refused for T-1002", refused == {"error": "ticket not refundable"}, str(refused))
    unknown = lab.issue_refund.invoke({"ticket_id": "T-9999", "amount_usd": 20})
    check("refund refuses unknown ticket", unknown == {"error": "unknown ticket"}, str(unknown))


def test_catalog() -> None:
    rows = lab.catalog()
    check("catalog lists two tools", len(rows) == 2, str(len(rows)))
    by_name = {row["name"]: row for row in rows}
    check("catalog has both names", set(by_name) == {"get_ticket_status", "issue_refund"})
    check("catalog exposes required args", by_name["issue_refund"]["required"] == ["ticket_id", "amount_usd"])
    check(
        "catalog exposes properties",
        by_name["get_ticket_status"]["properties"] == ["ticket_id"],
        str(by_name["get_ticket_status"]["properties"]),
    )
    check(
        "catalog carries the descriptions",
        all(row["description"] for row in rows),
        str([row["description"] for row in rows]),
    )


def test_execute() -> None:
    good = lab.execute({"name": "get_ticket_status", "args": {"ticket_id": "T-1001"}, "id": "call_1"})
    check("execute returns a ToolMessage", isinstance(good, ToolMessage), type(good).__name__)
    check("tool_call_id is preserved", good.tool_call_id == "call_1", good.tool_call_id)
    check("payload is JSON", json.loads(good.content)["status"] == "open", good.content)

    unknown = lab.execute({"name": "delete_everything", "args": {}, "id": "call_2"})
    check("unknown tool becomes an error payload", "unknown tool" in unknown.content, unknown.content)
    check("unknown tool keeps the id", unknown.tool_call_id == "call_2")

    bad_args = lab.execute({"name": "issue_refund", "args": {"ticket_id": "T-1001"}, "id": "call_3"})
    check("invalid arguments become an error payload", "invalid arguments" in bad_args.content, bad_args.content)


def test_loop_control_flow() -> None:
    stub = StubModel(
        [
            call_message("get_ticket_status", {"ticket_id": "T-1001"}, "call_a"),
            AIMessage(content="T-1001 is open on the pro plan."),
        ]
    )
    result = lab.run_loop(stub, "status of T-1001?")
    check("loop stops on plain text", result.stopped == "answer", result.stopped)
    check("loop counts two iterations", result.iterations == 2, str(result.iterations))
    check("answer comes from the model", "open" in result.answer, result.answer)
    check(
        "message shapes are system/human/ai/tool/ai",
        [m.type for m in result.messages] == ["system", "human", "ai", "tool", "ai"],
        str([m.type for m in result.messages]),
    )
    check("tool result is attached to the call", result.messages[3].tool_call_id == "call_a")
    check("loop binds both tools", len(stub.tools) == 2, str(len(stub.tools)))
    check(
        "second call re-sends the tool result",
        any(m.type == "tool" for m in stub.bound.sent[1]),
        str([m.type for m in stub.bound.sent[1]]),
    )


def test_loop_budget() -> None:
    stub = StubModel([call_message("get_ticket_status", {"ticket_id": "T-1001"}, f"call_{i}") for i in range(5)])
    result = lab.run_loop(stub, "loop forever", max_iterations=3)
    check("budget stops the loop", result.stopped == "budget", result.stopped)
    check("budget honours max_iterations", result.iterations == 3, str(result.iterations))
    check("budget returns no answer", result.answer == "", result.answer)
    check("budget keeps the transcript", len(result.messages) == 8, str(len(result.messages)))


def test_agent_graph() -> None:
    stub = StubModel([])
    agent = agent_call.build_agent(stub)
    graph = agent.get_graph()
    check(
        "agent graph is start/model/tools/end",
        set(graph.nodes) == {"__start__", "model", "tools", "__end__"},
        str(sorted(graph.nodes)),
    )
    edges = {(edge.source, edge.target) for edge in graph.edges}
    check("model routes to tools", ("model", "tools") in edges, str(sorted(edges)))
    check("tools route back to model", ("tools", "model") in edges, str(sorted(edges)))
    check("plain agent has no checkpointer", agent.checkpointer is None)


def test_agent_loop() -> None:
    stub = StubModel(
        [
            call_message("get_ticket_status", {"ticket_id": "T-1001"}, "call_a"),
            AIMessage(content="T-1001 is open on the pro plan."),
        ]
    )
    agent = agent_call.build_agent(stub)
    result = agent.invoke({"messages": [{"role": "user", "content": "status of T-1001?"}]})
    messages = result["messages"]
    check(
        "one invoke produces human/ai/tool/ai",
        [m.type for m in messages] == ["human", "ai", "tool", "ai"],
        str([m.type for m in messages]),
    )
    check("the graph ran the tool", "open" in str(messages[2].content), str(messages[2].content))
    check("the answer survives", "open" in str(messages[-1].content), str(messages[-1].content))
    check("the graph bound both tools", len(stub.tools) == 2, str(len(stub.tools)))
    check(
        "the second model turn saw the tool result",
        any(m.type == "tool" for m in stub.bound.sent[1]),
        str([m.type for m in stub.bound.sent[1]]),
    )
    check("count_turns reads the graph output", agent_call.count_turns(messages) == (2, 1))


def test_pending_actions() -> None:
    interrupt = SimpleNamespace(value={"action_requests": [{"name": "issue_refund", "args": {}}]})
    actions = agent_call.pending_actions({"__interrupt__": (interrupt,)})
    check("pending action is surfaced", [a["name"] for a in actions] == ["issue_refund"], str(actions))
    check("no interrupt means no actions", agent_call.pending_actions({"messages": []}) == [])


def test_agent_no_fake_model() -> None:
    source = (HERE / "agent_call.py").read_text(encoding="utf-8")
    check("agent script has no scripted branch", "--real" not in source and "scripted" not in source.lower())
    check("agent script builds the live model", "build_model()" in source)


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
    with with_env(
        {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_MODEL": "deepseek-v4-pro",
            "DEEPSEEK_BASE_URL": "https://example.test",
        }
    ):
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
    source = (HERE / "function_calling_lab.py").read_text(encoding="utf-8")
    check("lab has no scripted branch", "--real" not in source and "scripted" not in source.lower())


def test_uv_project() -> None:
    """The uv project is the single source of dependencies; keep it honest."""
    pyproject = HERE / "pyproject.toml"
    check("pyproject.toml exists", pyproject.exists())
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    declared = {
        re.split(r"[<>=!~ ]", dep, maxsplit=1)[0] for dep in data["project"]["dependencies"]
    }
    check(
        "declares langchain, langchain-deepseek, pydantic",
        {"langchain", "langchain-deepseek", "pydantic"} <= declared,
        str(sorted(declared)),
    )


def test_live_smoke() -> tuple[bool, str]:
    if not os.getenv("DEEPSEEK_API_KEY"):
        return False, "skipped (no DEEPSEEK_API_KEY)"
    model = lab.build_model()
    reply = model.bind_tools(lab.TOOLS).invoke(
        [
            SystemMessage(content=lab.SYSTEM),
            HumanMessage(content=lab.QUESTION_STATUS),
        ]
    )
    check("live reply is an AIMessage", isinstance(reply, AIMessage), type(reply).__name__)
    check("live reply requested the lookup", bool(reply.tool_calls), str(reply.tool_calls))
    check("live call names a declared tool", reply.tool_calls[0]["name"] in lab.REGISTRY)

    gated = agent_call.build_agent(model, require_approval=True)
    config = {"configurable": {"thread_id": "eval-live-approval"}}
    paused = gated.invoke({"messages": [HumanMessage(lab.QUESTION_REFUND)]}, config)
    actions = agent_call.pending_actions(paused)
    check(
        "live agent paused on issue_refund",
        [action["name"] for action in actions] == ["issue_refund"],
        str(actions),
    )
    rejected = gated.invoke(
        Command(resume={"decisions": [{"type": "reject", "message": "No refund today."}]}),
        config,
    )
    tool_messages = [m for m in rejected["messages"] if m.type == "tool"]
    check(
        "live rejection reaches the model as a tool result",
        any("reject" in str(m.content).lower() for m in tool_messages),
        str([m.content for m in tool_messages]),
    )
    check(
        "live agent still answers after the rejection",
        bool(str(rejected["messages"][-1].content).strip()),
        str(rejected["messages"][-1].content),
    )
    return True, "ran one live tool call and one gated agent with a rejection"


TESTS = [
    ("fixture", test_fixture),
    ("tool contracts", test_tool_contracts),
    ("tool behaviour", test_tool_behaviour),
    ("catalog", test_catalog),
    ("execute", test_execute),
    ("loop control flow", test_loop_control_flow),
    ("loop budget", test_loop_budget),
    ("agent graph", test_agent_graph),
    ("agent loop", test_agent_loop),
    ("pending actions", test_pending_actions),
    ("agent has no fake model", test_agent_no_fake_model),
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
        print(f"FAIL {len(TESTS) + 1:02d} live smoke: {error}")
    else:
        print(f"ok {len(TESTS) + 1:02d} live smoke: {note}")
        if not ran:
            print("     set DEEPSEEK_API_KEY to include the live calls")

    total = len(CHECKS)
    print(f"\n{total} checks passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
