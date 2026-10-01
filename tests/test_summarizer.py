import pytest
from whatsaid.llm.summarizer import run_summary_workflow
from whatsaid.core.db import init_db, get_connection

@pytest.fixture
def test_db_path(tmp_path):
    db_path = str(tmp_path / "test_summarizer.db")
    init_db(db_path)
    
    conn = get_connection(db_path)
    cur = conn.cursor()
    
    cur.execute("INSERT INTO chats (id, name) VALUES (1, 'Test Chat')")
    
    # Insert multiple messages
    for i in range(1, 3000):
        cur.execute(f"INSERT INTO messages (chat_id, sender, timestamp, text) VALUES (1, 'Alice', '2023-01-01 10:00:00', 'Hello this is test message {i}')")
        
    conn.commit()
    conn.close()
    
    return db_path

# We need to mock LLMClient so it doesn't make real API calls in tests
def mock_generate(self, prompt, model="gpt-3.5-turbo"):
    return "This is a mock summary."

def test_run_summary_workflow(test_db_path, monkeypatch):
    from whatsaid.llm.client import LLMClient
    monkeypatch.setattr(LLMClient, "generate", mock_generate)
    
    result = run_summary_workflow(chat_id=1, date_from=None, date_to=None, db_path=test_db_path)
    
    assert result["status"] == "done"
    assert result["final_summary"] == "This is a mock summary."
    # Since we have 2999 messages and chunk size is 1500, we should have 2 chunks
    assert len(result["chunks"]) == 2
    assert len(result["sub_summaries"]) == 2
