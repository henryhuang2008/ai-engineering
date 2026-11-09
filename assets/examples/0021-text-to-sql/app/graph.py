"""The SQL agent as an explicit graph.

The reference tutorial binds a ``run_query`` tool and lets the model loop over
it. This version keeps the tool contract but makes every step a node, so the
retry limit, the approval point and the failure path are visible in the graph
instead of hidden inside a message loop:

    START -> load_schema -> generate -> (SQL? review : END)
                               ^            |
                               |            v
                            execute <---- review
                               |
                  (error and attempts left) -> generate
                  (ok)                       -> answer -> END
                  (out of attempts)          -> fail   -> END
"""

from __future__ import annotations

import re
from typing import Annotated, Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from app import db
from app.config import Settings
from app.prompts import ANSWER_PROMPT, SYSTEM_PROMPT

SQL_FENCE = re.compile(r"```sql\s*(.*?)```", re.IGNORECASE | re.DOTALL)


class SqlState(TypedDict):
    """Everything a node may read or write. Undeclared keys are dropped."""

    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    schema: str
    sql: str | None
    tool_call_id: str | None
    result: str | None
    error: str | None
    attempts: int
    approved: bool


def extract_sql(message: AIMessage) -> tuple[str | None, str | None]:
    """Return (sql, tool_call_id) from a model reply.

    The tool call is the primary contract. A ```sql fence is the fallback for
    models that describe the query in prose instead of calling the tool; the
    guard treats both the same way.
    """
    for call in getattr(message, "tool_calls", None) or []:
        if call.get("name") != "run_query":
            continue
        arguments = call.get("args") or {}
        sql = arguments.get("query")
        if isinstance(sql, str) and sql.strip():
            return sql.strip(), call.get("id")

    content = message.content if isinstance(message.content, str) else ""
    match = SQL_FENCE.search(content)
    if match:
        return match.group(1).strip(), None
    return None, None


def build_graph(
    model: BaseChatModel,
    settings: Settings,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    review: bool = False,
) -> Any:
    """Compile the agent. ``review=True`` inserts a human approval interrupt."""

    @tool("run_query")
    def run_query(query: str) -> str:
        """Run one read-only SQLite SELECT and return the rows."""
        return db.format_result(db.run_query(query, settings.db_path))

    bound = model.bind_tools([run_query])

    def load_schema(state: SqlState) -> dict:
        schema = db.schema_text(settings.db_path)
        return {
            "schema": schema,
            "messages": [
                SystemMessage(SYSTEM_PROMPT.format(schema=schema)),
                HumanMessage(state["question"]),
            ],
        }

    def generate(state: SqlState) -> dict:
        response = bound.invoke(state["messages"])
        sql, call_id = extract_sql(response)
        update: dict[str, Any] = {
            "messages": [response],
            "sql": sql,
            "tool_call_id": call_id,
        }
        if sql:
            update["attempts"] = state.get("attempts", 0) + 1
        return update

    def route_after_generate(state: SqlState) -> str:
        # No SQL means the model answered in prose, or declared the schema
        # insufficient. Either way the reply is the final message.
        return "review" if state.get("sql") else "end"

    def review_node(state: SqlState) -> dict:
        if not review:
            return {"approved": True}
        decision = interrupt(
            {
                "question": state["question"],
                "sql": state["sql"],
                "attempt": state.get("attempts", 1),
            }
        )
        if isinstance(decision, str):
            decision = {"action": decision}
        action = (decision or {}).get("action", "approve")
        if action == "reject":
            return {"approved": False}
        if action == "edit":
            edited = (decision.get("sql") or "").strip()
            if edited:
                return {"approved": True, "sql": edited}
        return {"approved": True}

    def route_after_review(state: SqlState) -> str:
        return "execute" if state.get("approved", True) else "fail"

    def execute(state: SqlState) -> dict:
        result = db.run_query(state["sql"] or "", settings.db_path)
        text = db.format_result(result)
        call_id = state.get("tool_call_id")

        if result.ok:
            message: AnyMessage = (
                ToolMessage(text, tool_call_id=call_id)
                if call_id
                else HumanMessage(f"Query result:\n{text}")
            )
            return {"messages": [message], "result": text, "error": None}

        message = (
            ToolMessage(text, tool_call_id=call_id)
            if call_id
            else HumanMessage(f"Query result:\n{text}")
        )
        return {
            "messages": [
                message,
                HumanMessage(
                    f"That query failed: {result.error}\n"
                    f"Rewrite it. Attempt {state.get('attempts', 0)} of "
                    f"{settings.max_attempts}."
                ),
            ],
            "result": None,
            "error": result.error,
        }

    def route_after_execute(state: SqlState) -> str:
        if state.get("error") is None:
            return "answer"
        if state.get("attempts", 0) >= settings.max_attempts:
            return "fail"
        return "generate"

    def answer(state: SqlState) -> dict:
        response = model.invoke(
            [
                SystemMessage("You are a precise data analyst."),
                HumanMessage(
                    ANSWER_PROMPT.format(
                        question=state["question"],
                        sql=state["sql"],
                        result=state["result"],
                    )
                ),
            ]
        )
        return {"messages": [response]}

    def fail(state: SqlState) -> dict:
        reason = state.get("error") or "the reviewer rejected the query"
        text = (
            f"I could not produce a working query after "
            f"{state.get('attempts', 0)} attempt(s). Last error: {reason}"
        )
        return {"messages": [AIMessage(content=text)]}

    builder = StateGraph(SqlState)
    builder.add_node("load_schema", load_schema)
    builder.add_node("generate", generate)
    builder.add_node("review", review_node)
    builder.add_node("execute", execute)
    builder.add_node("answer", answer)
    builder.add_node("fail", fail)

    builder.add_edge(START, "load_schema")
    builder.add_edge("load_schema", "generate")
    builder.add_conditional_edges(
        "generate",
        route_after_generate,
        {"review": "review", "end": END},
    )
    builder.add_conditional_edges(
        "review",
        route_after_review,
        {"execute": "execute", "fail": "fail"},
    )
    builder.add_conditional_edges(
        "execute",
        route_after_execute,
        {"answer": "answer", "generate": "generate", "fail": "fail"},
    )
    builder.add_edge("answer", END)
    builder.add_edge("fail", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())
