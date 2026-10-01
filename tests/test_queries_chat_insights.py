import pytest
import sqlite3
import os
from whatsaid.api.queries import get_chat_insights
from whatsaid.core.db import init_db, get_connection

@pytest.fixture
def test_db_path(tmp_path):
    db_path = str(tmp_path / "test_insights.db")
    init_db(db_path)
    
    # seed data
    conn = get_connection(db_path)
    cur = conn.cursor()
    
    cur.execute("INSERT INTO chats (id, name) VALUES (1, 'Test Chat')")
    cur.execute("INSERT INTO chats (id, name) VALUES (2, 'Other Chat')")
    
    # Messages in Test Chat
    cur.execute("INSERT INTO messages (id, chat_id, sender, timestamp) VALUES (1, 1, 'Alice', '2023-01-01 10:00:00')")
    cur.execute("INSERT INTO messages (id, chat_id, sender, timestamp) VALUES (2, 1, 'Bob', '2023-01-01 11:00:00')")
    cur.execute("INSERT INTO messages (id, chat_id, sender, timestamp) VALUES (3, 1, 'Alice', '2023-01-02 10:00:00')")
    
    # Message in Other Chat
    cur.execute("INSERT INTO messages (id, chat_id, sender, timestamp) VALUES (4, 2, 'Charlie', '2023-01-01 10:00:00')")
    
    # Resources
    cur.execute("INSERT INTO resources (id, chat_id, first_message_id, platform) VALUES (1, 1, 1, 'YouTube')")
    cur.execute("INSERT INTO resources (id, chat_id, first_message_id, platform) VALUES (2, 1, 2, 'Twitter')")
    cur.execute("INSERT INTO resources (id, chat_id, first_message_id, platform) VALUES (3, 1, 3, 'YouTube')")
    
    conn.commit()
    conn.close()
    
    return db_path

def test_get_chat_insights(test_db_path):
    insights = get_chat_insights(chat_id=1, db_path=test_db_path)
    assert insights is not None
    assert insights["chat_id"] == 1
    assert insights["chat_name"] == "Test Chat"
    assert insights["total_messages"] == 3
    
    # Check participants
    assert len(insights["participants"]) == 2
    assert insights["participants"][0]["sender"] == "Alice"
    assert insights["participants"][0]["count"] == 2
    assert insights["participants"][1]["sender"] == "Bob"
    
    # Check top platforms
    assert len(insights["top_platforms"]) == 2
    assert insights["top_platforms"][0]["platform"] == "YouTube"
    assert insights["top_platforms"][0]["count"] == 2

def test_get_chat_insights_with_date_range(test_db_path):
    insights = get_chat_insights(chat_id=1, db_path=test_db_path, date_from="2023-01-02", date_to="2023-01-02")
    assert insights["total_messages"] == 1
    assert len(insights["participants"]) == 1
    assert insights["participants"][0]["sender"] == "Alice"
    assert insights["participants"][0]["count"] == 1
    
    assert len(insights["top_platforms"]) == 1
    assert insights["top_platforms"][0]["platform"] == "YouTube"

def test_get_chat_insights_not_found(test_db_path):
    insights = get_chat_insights(chat_id=999, db_path=test_db_path)
    assert insights is None
