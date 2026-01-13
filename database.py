import sqlite3

# Connect to database (creates file if it doesn't exist)
conn = sqlite3.connect("task_app.db")
c = conn.cursor()

# Create users table
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    passcode TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0
)
""")

# Create tasks table (add this)
c.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    assigned_to TEXT NOT NULL,
    assigned_by TEXT NOT NULL,
    due_date TEXT,
    status TEXT DEFAULT 'Pending'
)
""")

# Commit changes and close
conn.commit()
conn.close()
