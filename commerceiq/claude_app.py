from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import anthropic
from dotenv import load_dotenv

from commerceiq.query_database import query_database


DEFAULT_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1_000
MAX_TOOL_ITERATIONS = 5
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "docs" / "DATABASE_SCHEMA.md"

QUERY_DATABASE_TOOL = {
    "name": "query_database",
    "description": (
        "Execute one validated, read-only MySQL SELECT query against the CommerceIQ "
        "e-commerce sample database. Use this for factual questions that require "
        "database rows or aggregations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql_query": {
                "type": "string",
                "description": "A single read-only MySQL SELECT query over the allowlisted CommerceIQ tables.",
            }
        },
        "required": ["sql_query"],
        "additionalProperties": False,
    },
}

CLAUDE_TOOLS = [QUERY_DATABASE_TOOL]


@dataclass
class ToolCallLog:
    tool_use_id: str
    name: str
    sql_query: str
    result_summary: str
    error: dict[str, Any] | None = None


@dataclass
class AssistantReply:
    answer: str
    tool_calls: list[ToolCallLog] = field(default_factory=list)
    error: str | None = None


def load_schema_context() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def build_system_prompt(schema_context: str | None = None) -> str:
    schema = schema_context if schema_context is not None else load_schema_context()
    return f"""You are CommerceIQ, a concise data assistant for a fixed MySQL e-commerce database.

Use the query_database tool when a user asks for facts, counts, lists, joins, filters, rankings, date ranges, or aggregations from the database.
Use only the documented schema and business rules below. Do not invent columns or tables.

Important SQL rules:
- Generate MySQL SELECT queries only.
- Query only the commerceiq schema and these tables: customers, products, orders, order_items.
- Revenue is SUM(order_items.quantity * order_items.unit_price) for orders where status = 'Completed'.
- Current products.price is not historical revenue.
- Quantity sold should use Completed orders by default unless the user explicitly asks for another status.
- If the user asks for profit, margin, cost, or unavailable data, say the schema does not store it.
- Prefer clear column aliases for aggregates.
- Keep result sets small. Use LIMIT for lists.
- Base final answers on tool results, and say when results are empty or incomplete.

Database schema and conventions:
{schema}
"""


class CommerceIQAssistant:
    def __init__(
        self,
        client: Any | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        query_tool: Callable[[str], dict[str, Any]] = query_database,
    ) -> None:
        load_dotenv()
        self.client = client if client is not None else anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self.system_prompt = system_prompt or build_system_prompt()
        self.query_tool = query_tool
        self.messages: list[dict[str, Any]] = []

    def clear(self) -> None:
        self.messages.clear()

    def ask(
        self,
        user_question: str,
        on_tool_call: Callable[[str], None] | None = None,
    ) -> AssistantReply:
        if not user_question.strip():
            return AssistantReply(answer="", error="Question cannot be empty.")

        self.messages.append({"role": "user", "content": user_question})
        tool_logs: list[ToolCallLog] = []

        try:
            for _ in range(MAX_TOOL_ITERATIONS):
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    system=self.system_prompt,
                    messages=list(self.messages),
                    tools=CLAUDE_TOOLS,
                )
                assistant_content = normalize_content(response.content)
                self.messages.append({"role": "assistant", "content": assistant_content})

                tool_uses = [block for block in assistant_content if block.get("type") == "tool_use"]
                if not tool_uses:
                    return AssistantReply(answer=extract_text(assistant_content), tool_calls=tool_logs)

                tool_results = []
                for tool_use in tool_uses:
                    tool_result, log = self.dispatch_tool_use(tool_use)
                    tool_logs.append(log)
                    if on_tool_call is not None and log.sql_query:
                        on_tool_call(log.sql_query)
                    tool_results.append(tool_result)

                self.messages.append({"role": "user", "content": tool_results})

            return AssistantReply(
                answer="Claude used too many tool iterations before producing a final answer.",
                tool_calls=tool_logs,
                error="tool_iteration_limit",
            )
        except Exception as exc:
            return AssistantReply(
                answer="I could not reach Claude or complete the request. Please check your API key and network connection.",
                tool_calls=tool_logs,
                error=safe_api_error(exc),
            )

    def dispatch_tool_use(self, tool_use: dict[str, Any]) -> tuple[dict[str, Any], ToolCallLog]:
        tool_use_id = str(tool_use.get("id", "unknown_tool_use"))
        tool_name = str(tool_use.get("name", ""))
        tool_input = tool_use.get("input", {})

        if tool_name != "query_database":
            result = tool_error("unknown_tool", f"Tool '{tool_name}' is not available.")
            return build_tool_result(tool_use_id, result), ToolCallLog(
                tool_use_id=tool_use_id,
                name=tool_name,
                sql_query="",
                result_summary="Rejected unknown tool.",
                error=result["error"],
            )

        if not isinstance(tool_input, dict) or not isinstance(tool_input.get("sql_query"), str):
            result = tool_error("invalid_tool_input", "query_database requires a string sql_query.")
            return build_tool_result(tool_use_id, result), ToolCallLog(
                tool_use_id=tool_use_id,
                name=tool_name,
                sql_query="",
                result_summary="Rejected invalid tool input.",
                error=result["error"],
            )

        sql_query = tool_input["sql_query"]
        result = self.query_tool(sql_query)
        error = result.get("error") if isinstance(result, dict) else None
        summary = summarize_tool_result(result)
        return build_tool_result(tool_use_id, result), ToolCallLog(
            tool_use_id=tool_use_id,
            name=tool_name,
            sql_query=sql_query,
            result_summary=summary,
            error=error,
        )


def normalize_content(content: Any) -> list[dict[str, Any]]:
    normalized = []
    for block in content:
        block_type = get_block_value(block, "type")
        if block_type == "text":
            normalized.append({"type": "text", "text": get_block_value(block, "text", "")})
        elif block_type == "tool_use":
            normalized.append(
                {
                    "type": "tool_use",
                    "id": get_block_value(block, "id"),
                    "name": get_block_value(block, "name"),
                    "input": get_block_value(block, "input", {}),
                }
            )
    return normalized


def get_block_value(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def extract_text(content: list[dict[str, Any]]) -> str:
    return "\n".join(
        block.get("text", "")
        for block in content
        if block.get("type") == "text" and block.get("text")
    ).strip()


def build_tool_result(tool_use_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(result, ensure_ascii=True),
        "is_error": bool(result.get("error")),
    }


def tool_error(code: str, message: str) -> dict[str, Any]:
    return {
        "columns": [],
        "rows": [],
        "row_count": 0,
        "truncated": False,
        "error": {"code": code, "message": message},
    }


def summarize_tool_result(result: dict[str, Any]) -> str:
    error = result.get("error")
    if error:
        return f"error={error.get('code')}: {error.get('message')}"
    return f"rows={result.get('row_count', 0)}, truncated={result.get('truncated', False)}"


def safe_api_error(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc)[:200]}"
