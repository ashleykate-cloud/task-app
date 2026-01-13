import sqlite3

conn = sqlite3.connect("task_app.db")
c = conn.cursor()

# Insert admin user (change passcode if you want)
c.execute("INSERT INTO users (username, passcode, is_admin) VALUES (?, ?, ?)", ("admin", "1234", 1))

conn.commit()
conn.close()
print("Admin user created")

