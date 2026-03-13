"""Tools available to the agent: document search and arithmetic."""

import re

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.tools import tool  # pyright: ignore[reportUnknownVariableType]

_vectorstore: Chroma | None = None


def init_tools(vectorstore: Chroma) -> None:
    """Set the vectorstore reference used by search_documents."""
    global _vectorstore
    _vectorstore = vectorstore


@tool
def search_documents(query: str) -> str:
    """Search the document corpus for information relevant to the query.

    Returns matching document contents with their document IDs and relevance
    scores. Use this when you need to find factual information from the corpus.
    """
    assert _vectorstore is not None, "Call init_tools() before using search_documents"
    results: list[tuple[Document, float]] = (
        _vectorstore.similarity_search_with_relevance_scores(query, k=2)
    )
    if not results:
        return "No relevant documents found."
    formatted: list[str] = []
    for doc, score in results:
        doc_id: str = str(doc.metadata["doc_id"])  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        formatted.append(f"[Doc {doc_id}] (relevance: {score:.2f}) {doc.page_content}")
    return "\n".join(formatted)


@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression and return the precise result.

    Use this when you need to perform arithmetic (addition, subtraction, etc.).
    Input should be a valid arithmetic expression, e.g. '32524398 + 32351553'.
    """
    if not re.match(r"^[\d\s\+\-\*/\(\)\.]+$", expression):
        return f"Error: Invalid expression '{expression}'. Use only numbers and arithmetic operators."
    try:
        result: int | float = eval(expression)  # noqa: S307  # pyright: ignore[reportAny]
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error evaluating '{expression}': {e}"
