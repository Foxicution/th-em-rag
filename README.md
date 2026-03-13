# Mini-Analyst RAG System

A multi-hop RAG agent that answers complex questions by searching a document corpus and performing precise arithmetic. Built with LangGraph and Gemini.

## Setup

```bash
poetry install
cp .env.template .env
# Edit .env and add your Google API key
```

## Run

```bash
poetry run python -m rag.main
```

## How it works

The agent uses a LangGraph state graph with three nodes:

```
decompose → agent ⇄ tools → END
```

### Query Decomposition (S13)

Before tool use begins, a **decompose** node classifies the incoming query:

- **SINGLE** — one retrieval is enough, pass through to agent
- **MULTI_HOP** — sequential dependency between retrievals (agent handles via loop)
- **MULTI_QUERY** — independent sub-queries that can be retrieved in parallel

For MULTI_QUERY, the agent issues parallel tool calls. For SINGLE/MULTI_HOP, it reasons sequentially.

### Tools

- **search_documents** — semantic search over the document corpus via ChromaDB, returns results with relevance scores
- **calculate** — evaluates arithmetic expressions for precise computation

### Example trace

For the multi-hop query *"What is the total number of inhabitants in the country that is mentioned in the article about renewable energy?"*:

1. **Decompose** → classified as MULTI_HOP
2. Searches for "renewable energy" → identifies France (Doc 003)
3. Searches for population data in France → finds male/female counts (Doc 001)
4. Computes 32,524,398 + 32,351,553 = **64,875,951**
5. Returns the answer citing [Doc 001] and [Doc 003]

If initial retrieval is poor, the agent rephrases the query and retries (up to 3 searches).

## Scaling: nested multi-hop sub-queries

The current decomposition is single-level — MULTI_QUERY sub-queries are executed as parallel searches, not as independent multi-hop chains. For production workloads where each sub-query might itself require sequential reasoning, the graph would extend to:

```
decompose → fan_out → [sub_agent₁, sub_agent₂, ...] → fan_in → synthesize → END
```

Each sub-agent runs its own ReAct loop (search → follow-up → calculate). LangGraph's `Send()` API enables this — the fan-out node dynamically spawns one sub-graph per sub-query:

```python
def fan_out(state):
    return [Send("sub_agent", {"messages": [HumanMessage(content=q)]})
            for q in state["sub_queries"]]
```

Results are collected in a fan-in node, then a synthesis agent produces the final cited answer. The decompose node stays unchanged — it feeds sub-queries into `Send` instead of a parallel tool-call instruction.

## Project structure

```
src/rag/
    documents.py   # Document corpus + vectorstore builder
    tools.py       # Search and calculate tools
    agent.py       # LangGraph ReAct agent with query decomposition
    main.py        # Entry point with execution trace
```
