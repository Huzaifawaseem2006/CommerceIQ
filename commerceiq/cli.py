from __future__ import annotations

import argparse

from commerceiq.claude_app import CommerceIQAssistant


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask Claude questions about the CommerceIQ MySQL database.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Display generated SQL and summarized tool results.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assistant = CommerceIQAssistant()

    print("CommerceIQ CLI")
    print("Ask a question, use /clear to reset conversation history, or type exit/quit to leave.")

    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break
        if question == "/clear":
            assistant.clear()
            print("Conversation history cleared.")
            continue
        if not question:
            continue

        def show_sql(sql_query: str) -> None:
            print("\nGenerated SQL:")
            print(sql_query)

        reply = assistant.ask(question, on_tool_call=show_sql)

        if args.debug and reply.tool_calls:
            print("\nTool results:")
            for index, tool_call in enumerate(reply.tool_calls, start=1):
                print(f"{index}. {tool_call.result_summary}")

        if reply.error:
            print(f"\nError: {reply.answer}")
            if args.debug:
                print(f"Details: {reply.error}")
            continue

        print(f"\n{reply.answer}")


if __name__ == "__main__":
    main()
