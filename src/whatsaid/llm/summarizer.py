"""LangGraph-based chat summarizer workflow."""

from __future__ import annotations

from typing import Optional, TypedDict
from langgraph.graph import END, START, StateGraph

from ..core.db import DEFAULT_DB_PATH
from ..api.queries import get_messages
from ..llm.client import LLMClient
from ..logging import get_logger

logger = get_logger(__name__)

class SummarizerState(TypedDict):
    chat_id: int
    date_from: Optional[str]
    date_to: Optional[str]
    db_path: str
    
    messages_raw: list[dict]
    chunks: list[str]
    current_chunk_idx: int
    sub_summaries: list[str]
    
    final_summary: Optional[str]
    status: str
    error: Optional[str]

# 1. Fetch Messages
def _node_fetch_messages(state: SummarizerState) -> SummarizerState:
    logger.info("Fetching messages for summary", extra={"chat_id": state["chat_id"]})
    try:
        # get_messages in queries.py currently uses pagination and only filters by search/chat_id.
        # We need all messages in the date range. Let's write a quick custom query here to avoid altering get_messages heavily.
        from ..core.db import get_connection
        conn = get_connection(state["db_path"])
        cur = conn.cursor()
        
        conditions = ["chat_id = ?"]
        params = [state["chat_id"]]
        if state["date_from"]:
            conditions.append("DATE(timestamp) >= ?")
            params.append(state["date_from"])
        if state["date_to"]:
            conditions.append("DATE(timestamp) <= ?")
            params.append(state["date_to"])
            
        where_clause = f"WHERE {' AND '.join(conditions)}"
        cur.execute(f"SELECT sender, timestamp, text FROM messages {where_clause} ORDER BY timestamp ASC", params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        
        return {**state, "messages_raw": rows}
    except Exception as exc:
        logger.error("Failed to fetch messages for summary", extra={"error": str(exc)})
        return {**state, "status": "failed", "error": f"Failed to fetch messages: {exc}"}

# 2. Chunk Messages
def _node_chunk_messages(state: SummarizerState) -> SummarizerState:
    if state.get("status") == "failed":
        return state
        
    messages = state["messages_raw"]
    if not messages:
        return {**state, "final_summary": "No messages found for this date range.", "status": "done"}
        
    # Chunk by character length to ensure we don't exceed the token limit.
    # 40,000 characters is roughly 10,000 tokens (well within 16k limit).
    CHUNK_MAX_CHARS = 40000
    
    chunks = []
    current_chunk = []
    current_len = 0
    for m in messages:
        sender = m.get("sender") or "Unknown"
        text = m.get("text") or ""
        timestamp = m.get("timestamp") or ""
        
        line = f"[{timestamp}] {sender}: {text}"
        line_len = len(line) + 1 # +1 for newline
        
        if current_len + line_len > CHUNK_MAX_CHARS and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = line_len
        else:
            current_chunk.append(line)
            current_len += line_len
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
        
    logger.info(f"Split messages into {len(chunks)} chunks.")
    
    return {**state, "chunks": chunks, "current_chunk_idx": 0, "sub_summaries": []}

# 3. Summarize Chunk (Cumulative)
def _node_summarize_chunk(state: SummarizerState) -> SummarizerState:
    if state.get("status") == "failed" or state.get("status") == "done":
        return state
        
    idx = state["current_chunk_idx"]
    chunk_text = state["chunks"][idx]
    
    if idx == 0:
        prompt = (
            "You are an expert summarizer. Please summarize the following chat log segment. "
            "Highlight key themes, events, and important decisions.\n\n"
            f"Chat Segment:\n{chunk_text}"
        )
    else:
        previous_summary = state["sub_summaries"][-1]
        prompt = (
            "You are an expert summarizer. You are progressively summarizing a long chat history. "
            "Here is the summary of the chat so far:\n"
            f"{previous_summary}\n\n"
            "Please update and extend this summary by incorporating the new information from the next chat segment below. "
            "Maintain a cohesive, comprehensive final summary that flows well.\n\n"
            f"Next Chat Segment:\n{chunk_text}"
        )
    
    client = LLMClient()
    try:
        response = client.generate(prompt=prompt)
        sub_summaries = state["sub_summaries"] + [response]
        return {**state, "sub_summaries": sub_summaries, "current_chunk_idx": idx + 1}
    except Exception as exc:
        return {**state, "status": "failed", "error": str(exc)}

def _should_continue_summarizing(state: SummarizerState) -> str:
    if state.get("status") == "failed":
        return "combine_summaries"
    if state.get("status") == "done":
        return "END" # no messages
        
    if state["current_chunk_idx"] < len(state.get("chunks", [])):
        return "summarize_chunk"
    return "combine_summaries"

# 4. Finalize Summary
def _node_combine_summaries(state: SummarizerState) -> SummarizerState:
    if state.get("status") == "failed" or state.get("status") == "done":
        return state
        
    sub_summaries = state["sub_summaries"]
    if not sub_summaries:
        return {**state, "final_summary": "No summary generated.", "status": "done"}
        
    # Since we did a cumulative summary, the last summary in the list IS the final summary!
    final_summary = sub_summaries[-1]
    
    return {**state, "final_summary": final_summary, "status": "done"}

def build_summarizer_graph():
    graph = StateGraph(SummarizerState)
    graph.add_node("fetch_messages", _node_fetch_messages)
    graph.add_node("chunk_messages", _node_chunk_messages)
    graph.add_node("summarize_chunk", _node_summarize_chunk)
    graph.add_node("combine_summaries", _node_combine_summaries)
    
    graph.add_edge(START, "fetch_messages")
    graph.add_edge("fetch_messages", "chunk_messages")
    graph.add_edge("chunk_messages", "summarize_chunk")
    
    graph.add_conditional_edges(
        "summarize_chunk",
        _should_continue_summarizing,
        {
            "summarize_chunk": "summarize_chunk",
            "combine_summaries": "combine_summaries",
            "END": END
        }
    )
    
    graph.add_edge("combine_summaries", END)
    return graph.compile()

_GRAPH = None
def get_summarizer_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_summarizer_graph()
    return _GRAPH

def run_summary_workflow(chat_id: int, date_from: Optional[str], date_to: Optional[str], db_path: str = DEFAULT_DB_PATH) -> SummarizerState:
    initial_state: SummarizerState = {
        "chat_id": chat_id,
        "date_from": date_from,
        "date_to": date_to,
        "db_path": db_path,
        "messages_raw": [],
        "chunks": [],
        "current_chunk_idx": 0,
        "sub_summaries": [],
        "final_summary": None,
        "status": "pending",
        "error": None
    }
    graph = get_summarizer_graph()
    return graph.invoke(initial_state)
