"""Document corpus and vector store initialization."""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

PERSIST_DIR: Path = Path(__file__).resolve().parents[2] / ".chroma"

DOCUMENTS = [
    Document(
        page_content=(
            "In France, there are approximately "
            "32,524,398 females and 32,351,553 males."
        ),
        metadata={"doc_id": "001"},
    ),
    Document(
        page_content="France is known for its wine and cheese.",
        metadata={"doc_id": "002"},
    ),
    Document(
        page_content="Renewable energy is growing rapidly in France.",
        metadata={"doc_id": "003"},
    ),
]


def build_vectorstore() -> Chroma:
    """Load vectorstore from disk, or embed and persist on first run."""
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    if PERSIST_DIR.exists():
        return Chroma(
            persist_directory=str(PERSIST_DIR),
            embedding_function=embeddings,
            collection_name="mini-analyst",
        )
    return Chroma.from_documents(  # pyright: ignore[reportUnknownMemberType]
        documents=DOCUMENTS,
        embedding=embeddings,
        collection_name="mini-analyst",
        persist_directory=str(PERSIST_DIR),
    )
