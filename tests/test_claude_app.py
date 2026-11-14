from __future__ import annotations

from types import SimpleNamespace

from commerceiq.claude_app import CLAUDE_TOOLS, CommerceIQAssistant


class FakeMessages:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if not self.responses:
            raise RuntimeError("No fake responses left.")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.messages = FakeMessages(responses)


def text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[{"type": "text", "text": text}])


def tool_response(*tool_uses: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(content=list(tool_uses))


def tool_use(tool_id: str, sql_query: str) -> dict[str, object]:
    return {
        "type": "tool_use",
        "id": tool_id,
        "name": "query_database",
        "input": {"sql_query": sql_query},
    }


def query_result(row_count: int = 1) -> dict[str, object]:
    return {
        "columns": ["name"],
        "rows": [{"name": "Wireless Mouse"}],
        "row_count": row_count,
        "truncated": False,
        "error": None,
    }


def test_registers_exactly_one_query_database_tool() -> None:
    assert len(CLAUDE_TOOLS) == 1
    tool = CLAUDE_TOOLS[0]
    assert tool["name"] == "query_database"
    assert tool["input_schema"]["required"] == ["sql_query"]


def test_tool_loop_sends_tool_result_then_final_answer() -> None:
    client = FakeClient(
        [
            tool_response(tool_use("toolu_1", "SELECT name FROM products LIMIT 1")),
            text_response("The first product is Wireless Mouse."),
        ]
    )
    assistant = CommerceIQAssistant(
        client=client,
        model="test-model",
        system_prompt="schema",
        query_tool=lambda sql: query_result(),
    )
    seen_sql: list[str] = []

    reply = assistant.ask("Show one product", on_tool_call=seen_sql.append)

    assert reply.answer == "The first product is Wireless Mouse."
    assert reply.error is None
    assert seen_sql == ["SELECT name FROM products LIMIT 1"]
    assert len(client.messages.calls) == 2
    assert client.messages.calls[0]["tools"] == CLAUDE_TOOLS
    tool_result_message = assistant.messages[2]
    assert tool_result_message["role"] == "user"
    assert tool_result_message["content"][0]["type"] == "tool_result"
    assert tool_result_message["content"][0]["tool_use_id"] == "toolu_1"


def test_handles_multiple_same_tool_calls_in_one_response() -> None:
    client = FakeClient(
        [
            tool_response(
                tool_use("toolu_1", "SELECT COUNT(*) AS count FROM customers"),
                tool_use("toolu_2", "SELECT COUNT(*) AS count FROM orders"),
            ),
            text_response("There are customers and orders."),
        ]
    )
    assistant = CommerceIQAssistant(
        client=client,
        model="test-model",
        system_prompt="schema",
        query_tool=lambda sql: query_result(),
    )

    reply = assistant.ask("Compare customers and orders")

    assert reply.error is None
    assert len(reply.tool_calls) == 2
    assert [call.sql_query for call in reply.tool_calls] == [
        "SELECT COUNT(*) AS count FROM customers",
        "SELECT COUNT(*) AS count FROM orders",
    ]
    tool_results = assistant.messages[2]["content"]
    assert [result["tool_use_id"] for result in tool_results] == ["toolu_1", "toolu_2"]


def test_maintains_history_for_follow_up_and_clear_resets() -> None:
    client = FakeClient(
        [
            text_response("Seattle has 5 customers."),
            text_response("Those customers placed 12 orders."),
        ]
    )
    assistant = CommerceIQAssistant(client=client, model="test-model", system_prompt="schema")

    first = assistant.ask("How many customers are in Seattle?")
    second = assistant.ask("How many orders did they place?")

    assert first.answer == "Seattle has 5 customers."
    assert second.answer == "Those customers placed 12 orders."
    second_call_messages = client.messages.calls[1]["messages"]
    assert len(second_call_messages) == 3

    assistant.clear()
    assert assistant.messages == []


def test_tool_error_is_returned_to_claude_for_invalid_tool_input() -> None:
    client = FakeClient(
        [
            tool_response(
                {
                    "type": "tool_use",
                    "id": "toolu_bad",
                    "name": "query_database",
                    "input": {"sql_query": 123},
                }
            ),
            text_response("The query input was invalid."),
        ]
    )
    assistant = CommerceIQAssistant(client=client, model="test-model", system_prompt="schema")

    reply = assistant.ask("Bad input please")

    assert reply.error is None
    assert reply.tool_calls[0].error["code"] == "invalid_tool_input"
    assert assistant.messages[2]["content"][0]["is_error"] is True


def test_api_errors_are_graceful() -> None:
    client = FakeClient([RuntimeError("network unavailable")])
    assistant = CommerceIQAssistant(client=client, model="test-model", system_prompt="schema")

    reply = assistant.ask("Show revenue")

    assert reply.error == "RuntimeError: network unavailable"
    assert "could not reach claude" in reply.answer.lower()
