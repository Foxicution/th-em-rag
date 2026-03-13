"""LangGraph ReAct agent with query decomposition and tool use.

Implements S13 (Query Decomposition) and S15 (Agentic Retry Loop) from the
architecture document. The graph has three nodes:

    decompose → agent ⇄ tools → END

The decompose node (S13) classifies the query as:
- SINGLE: one retrieval needed, pass through to agent
- MULTI_HOP: sequential dependency between retrievals (agent handles via loop)
- MULTI_QUERY: independent sub-queries that can be retrieved in parallel

For MULTI_QUERY, the decomposition is injected as a system message so the agent
issues parallel tool calls. For SINGLE/MULTI_HOP, the agent reasons sequentially.
"""

import os
from typing import Annotated, Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.message import add_messages  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from rag.tools import calculate, search_documents

DECOMPOSITION_PROMPT = """\
Classify this query and decompose if needed.

Query: {query}

Respond with EXACTLY one of these formats:

SINGLE: <query>
  → One retrieval is enough.

MULTI_HOP: <query>
  → Sequential steps needed (each step depends on the previous result).

MULTI_QUERY: <sub-query 1> ||| <sub-query 2> [||| <sub-query 3> ...]
  → Independent sub-queries that can be searched in parallel.

Examples:
- "What is France known for?" → SINGLE: What is France known for?
- "What is the population of the country mentioned in the renewable energy article?" → MULTI_HOP: What is the population of the country mentioned in the renewable energy article?
- "What is the population of France and what is France known for?" → MULTI_QUERY: population of France ||| what is France known for?\
"""

AGENT_PROMPT = """\
You are a precise research analyst. Answer questions using ONLY information
retrieved from the document corpus. You have two tools:

1. search_documents — search the corpus for relevant information.
2. calculate — evaluate arithmetic expressions for precise computation.

Instructions:
- For multi-hop questions, search for each piece of information separately.
- ALWAYS use the calculate tool for arithmetic. Never compute in your head.
- If search results seem irrelevant or incomplete, rephrase your query and search
  again with different keywords. Try at most 3 searches total.
- Copy numbers exactly as they appear in the documents.

CRITICAL — Citations are MANDATORY:
Your final answer MUST cite every document you used. Use the format [Doc XXX]
where XXX is the doc_id from the search results. Example: "France has 64,875,951
inhabitants [Doc 001, Doc 003]." An answer without citations is INCOMPLETE.\
"""

PARALLEL_INSTRUCTION = """\
The following sub-queries are INDEPENDENT. Call search_documents for ALL of them
in a SINGLE response using parallel tool calls:

{sub_queries}\
"""

TOOLS: list[BaseTool] = [search_documents, calculate]


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    classification: str


def _should_continue(state: AgentState) -> str:
    """Route to tools if the last message contains tool calls, else end."""
    last: AnyMessage = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def build_agent() -> CompiledStateGraph:  # pyright: ignore[reportMissingTypeArgument, reportUnknownParameterType]
    """Construct and compile the LangGraph ReAct agent."""
    model_name: str = os.getenv("MODEL_NAME", "gemini-2.5-flash")
    model = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    model_with_tools = model.bind_tools(TOOLS)  # pyright: ignore[reportUnknownMemberType]

    def decompose(state: AgentState) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """S13: Classify query as single, multi-hop, or multi-query."""
        user_msg: AnyMessage = state["messages"][-1]
        assert isinstance(user_msg, HumanMessage)
        query: str = str(user_msg.content)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]

        response = model.invoke([
            SystemMessage(content=DECOMPOSITION_PROMPT.format(query=query)),
            HumanMessage(content=query),
        ])
        raw: str = str(response.content).strip()  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        # Gemini 2.5+ may wrap in list; extract text
        if isinstance(response.content, list):  # pyright: ignore[reportUnknownMemberType]
            raw = " ".join(
                b["text"] for b in response.content  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
                if isinstance(b, dict) and "text" in b
            ).strip()

        # Append citation reminder to the user query so it stays visible
        # throughout the agent's multi-turn reasoning.
        augmented_msg = HumanMessage(
            content=f"{query}\n\n(Remember: cite every document as [Doc XXX] in your final answer.)"
        )

        if raw.startswith("MULTI_QUERY:"):
            sub_queries: list[str] = [
                q.strip() for q in raw[len("MULTI_QUERY:"):].split("|||")
            ]
            numbered: str = "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_queries))
            return {
                "classification": raw,
                "messages": [
                    SystemMessage(content=AGENT_PROMPT),
                    SystemMessage(content=PARALLEL_INSTRUCTION.format(sub_queries=numbered)),
                    augmented_msg,
                ],
            }

        # SINGLE or MULTI_HOP: agent handles sequentially
        return {
            "classification": raw,
            "messages": [
                SystemMessage(content=AGENT_PROMPT),
                augmented_msg,
            ],
        }

    def call_model(state: AgentState) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        return {"messages": [model_with_tools.invoke(state["messages"])]}

    tool_node: ToolNode = ToolNode(TOOLS)

    graph = StateGraph(AgentState)
    _ = graph.add_node("decompose", decompose)  # pyright: ignore[reportUnknownMemberType]
    _ = graph.add_node("agent", call_model)  # pyright: ignore[reportUnknownMemberType]
    _ = graph.add_node("tools", tool_node)  # pyright: ignore[reportUnknownMemberType]
    _ = graph.set_entry_point("decompose")
    _ = graph.add_edge("decompose", "agent")
    _ = graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    _ = graph.add_edge("tools", "agent")

    return graph.compile()  # pyright: ignore[reportUnknownMemberType]
