import json, sqlite3
from typing import Optional
from schemas.tool_schemas import Message
from config import settings

def initialize_db():
    con = sqlite3.connect(settings.DATABASE_PATH)
    con.execute("PRAGMA Journal_mode=WAL")
    cur = con.cursor()
    
    cur.execute("""CREATE TABLE IF NOT EXISTS Message(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        session_name TEXT,
        role TEXT,
        content TEXT,
        tool_name TEXT,
        tool_calls TEXT
        )""")
    
    con.commit()
    con.close()
    
def save_message_to_db(session_id: str, message: Message, session_name: Optional[str] = None):
    con = sqlite3.connect(settings.DATABASE_PATH)
    cur = con.cursor()
    
    if not session_name:
        cur.execute("""
                    SELECT DISTINCT session_name
                    from Message
                    WHERE session_id = ? AND session_name IS NOT NULL
                    LIMIT 1""", (session_id, ))
        row = cur.fetchone()
        if row:
            session_name = row[0]
    
    tool_calls = json.dumps(message.tool_calls) if message.tool_calls else None
    cur.execute("""
                INSERT INTO Message (session_id, session_name, role, content, tool_name, tool_calls)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id,
                 session_name,
                 message.role, 
                 message.content, 
                 message.tool_name, 
                 tool_calls))
    
    con.commit()
    con.close()
    
def load_history_from_db(session_id: str) -> list[Message]:
    con = sqlite3.connect(settings.DATABASE_PATH)
    cur = con.cursor()
    
    cur.execute("""
                SELECT 
                role, content, tool_name, tool_calls
                FROM Message WHERE session_id = ?""", (session_id,))
    rows = cur.fetchall()
    history = []
    for row in rows:
        tool_calls = json.loads(row[3]) if row[3] else None
        msg = Message(role=row[0], content=row[1], tool_name=row[2], tool_calls=tool_calls)
        history.append(msg)
        
    con.close()
    return history

def get_sessions() -> list[tuple[str, str]]:
    con = sqlite3.connect(settings.DATABASE_PATH)
    cur = con.cursor()
    cur.execute("""
                SELECT session_id, 
                session_name,
                MAX(id) as max_id
                FROM Message 
                GROUP BY session_id 
                ORDER BY max_id 
                DESC
                """)
    rows = cur.fetchall()
    sessions = [(row[0], row[1]) for row in rows]
    con.close()
    return sessions

def update_session_name(session_id: str, session_name: str):
    con = sqlite3.connect(settings.DATABASE_PATH)
    cur = con.cursor()
    cur.execute("""
                UPDATE Message
                SET session_name = ?
                WHERE session_id = ?""", (session_name, session_id))
    con.commit()
    con.close()
    