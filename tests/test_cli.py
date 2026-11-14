from __future__ import annotations

import sys
from collections.abc import Callable

from commerceiq.claude_app import AssistantReply, ToolCallLog
from commerceiq import cli


class FakeAssistant:
    instances: list["FakeAssistant"] = []

    def __init__(self) -> None:
        self.questions: list[str] = []
        self.clear_count = 0
        FakeAssistant.instances.append(self)

    def ask(
        self,
        question: str,
        on_tool_call: Callable[[str], None] | None = None,
    ) -> AssistantReply:
        self.questions.append(question)
        sql_query = "SELECT name FROM products ORDER BY price DESC LIMIT 1"
        if on_tool_call is not None:
            on_tool_call(sql_query)
        return AssistantReply(
            answer=f"Answered: {question}",
            tool_calls=[
                ToolCallLog(
                    tool_use_id="toolu_cli",
                    name="query_database",
                    sql_query=sql_query,
                    result_summary="rows=1, truncated=False",
                )
            ],
        )

    def clear(self) -> None:
        self.clear_count += 1


def test_cli_prints_generated_sql_and_clear_resets_history(
    monkeypatch,
    capsys,
) -> None:
    FakeAssistant.instances = []
    inputs = iter(["Most expensive product?", "/clear", "Follow-up question?", "exit"])

    monkeypatch.setattr(sys, "argv", ["commerceiq"])
    monkeypatch.setattr(cli, "CommerceIQAssistant", FakeAssistant)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    cli.main()

    output = capsys.readouterr().out
    assistant = FakeAssistant.instances[0]
    assert assistant.questions == ["Most expensive product?", "Follow-up question?"]
    assert assistant.clear_count == 1
    assert "Generated SQL:" in output
    assert "SELECT name FROM products ORDER BY price DESC LIMIT 1" in output
    assert "Conversation history cleared." in output
