import sqlite3
import json

def get_session_messages():
    conn = sqlite3.connect("agent_memory.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role, content, tool_calls, tool_name FROM Message WHERE session_id='db51ab75-0259-4623-8075-065f7e560d8a' ORDER BY id ASC;")
    rows = cursor.fetchall()
    for r in rows:
        print(f"Role: {r[0]}")
        print(f"Content: {r[1]}")
        print(f"Tool Calls: {r[2]}")
        print(f"Tool Name: {r[3]}")
        print("-" * 50)
    conn.close()

if __name__ == "__main__":
    get_session_messages()
