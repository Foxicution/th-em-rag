"""Mini-analyst RAG system — entry point.

NOTE on typing: LangChain and LangGraph have poor type coverage. LangGraph ships
no type stubs at all, and LangChain uses bare `dict` in key places (e.g.
BaseMessage.content is `Union[str, list[Union[str, dict]]]`). This means most
values flowing through the agent graph are partially or fully Unknown to static
analysers. We suppress these per-line with `pyright: ignore` where unavoidable.
"""

from typing import Any, cast

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from rag.agent import build_agent  # pyright: ignore[reportUnknownVariableType]
from rag.documents import build_vectorstore
from rag.tools import init_tools

QUERY = (
    "What is the total number of inhabitants in the country "
    "that is mentioned in the article about renewable energy?"
)


# NOTE: BaseMessage.content is typed as `Union[str, list[Union[str, dict]]]` in
# LangChain — bare `dict`, no parameterization. This is because they support multiple
# LLM providers that each return content blocks in different shapes. The trade-off is
# broad compatibility over type safety. We use `dict[str, Any]` as the best we can do.
def _extract_text(content: str | list[str | dict[str, Any]]) -> str:  # pyright: ignore[reportExplicitAny]
    """Extract plain text from message content (handles Gemini 2.5+ block format)."""
    if isinstance(content, list):
        return "\n".join(
            block["text"]
            for block in content
            if isinstance(block, dict) and "text" in block
        )
    return content


def _print_trace(classification: str, messages: list[BaseMessage]) -> None:
    """Print a step-by-step trace of the agent's reasoning."""
    print(f"  Decompose: {classification}")
    step: int = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            parallel: str = " (parallel)" if len(msg.tool_calls) > 1 else ""
            for call in msg.tool_calls:
                step += 1
                print(f"  Step {step}{parallel}: {call['name']}({call['args']})")
        elif isinstance(msg, ToolMessage):
            print(f"    → {msg.content}")  # pyright: ignore[reportUnknownMemberType]


def main() -> None:
    _ = load_dotenv()

    vectorstore = build_vectorstore()
    init_tools(vectorstore)
    agent = build_agent()  # pyright: ignore[reportUnknownVariableType]

    print(f"Query: {QUERY}\n")
    print("Trace:")

    result = cast(
        dict[str, Any],  # pyright: ignore[reportExplicitAny]
        agent.invoke(  # pyright: ignore[reportUnknownMemberType]
            {"messages": [HumanMessage(content=QUERY)]},
            config={"recursion_limit": 15},
        ),
    )

    classification: str = result.get("classification", "N/A")  # pyright: ignore[reportAny]
    messages: list[BaseMessage] = result["messages"]  # pyright: ignore[reportAny]
    _print_trace(classification, messages)

    content: str = _extract_text(messages[-1].content)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    print(f"\nAnswer:\n{content}")


if __name__ == "__main__":
    main()
