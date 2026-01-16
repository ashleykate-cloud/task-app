from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
import datetime
import os

# --------------------------
# 1️ Initialize app
# --------------------------
app = Flask(__name__)
app.secret_key = "this-is-a-secret"

# --------------------------
# 2️ Database paths
# --------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = "/opt/render/project/data"

if os.path.exists(DATA_DIR):
    DB_PATH = os.path.join(DATA_DIR, "task_app.db")
else:
    DB_PATH = os.path.join(BASE_DIR, "task_app.db")

# --------------------------
# 3️ Database helpers
# --------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            is_admin INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            due_date TEXT,
            status TEXT,
            assigned_to TEXT,
            assigned_by TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --------------------------
# 4️ Context Processor
# --------------------------
@app.context_processor
def inject_globals():
    return dict(
        is_admin=session.get("is_admin", 0),
        show_dashboard_button=(request.path != url_for("dashboard"))
    )

# --------------------------
# 5️ Routes
# --------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        passcode = request.form.get("passcode")

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, passcode)
        ).fetchone()
        conn.close()

        if user:
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            return redirect(url_for("dashboard"))
        else:
            return "Invalid username or password"

    return render_template("login.html")

# --------------------------
# DASHBOARD
# --------------------------
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    is_admin = session.get("is_admin", 0)

    conn = get_db_connection()
    tasks = conn.execute(
        """
        SELECT id, title, due_date, status, assigned_by
        FROM tasks
        WHERE assigned_to = ?
        ORDER BY
            CASE WHEN due_date IS NULL OR due_date = '' THEN 1 ELSE 0 END,
            due_date ASC
        """,
        (username,)
    ).fetchall()
    conn.close()

    today = datetime.date.today()

    # Convert sqlite3.Row to mutable dicts and parse due_date
    tasks_list = []
    for task in tasks:
        task_dict = dict(task)
        due_date_str = task_dict.get("due_date")
        if due_date_str:
            try:
                task_dict["due_date"] = datetime.datetime.strptime(due_date_str, "%Y-%m-%d").date()
            except ValueError:
                task_dict["due_date"] = None
        else:
            task_dict["due_date"] = None
        tasks_list.append(task_dict)

    return render_template(
        "dashboard.html",
        tasks=tasks_list,
        username=username,
        is_admin=is_admin,
        today=today  # <--- THIS FIXES YOUR 'today' undefined error
    )

# --------------------------
# TASK ROUTES
# --------------------------
@app.route("/update_status/<int:task_id>", methods=["POST"])
def update_status(task_id):
    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return "Task not found!"
    if session["username"] != task["assigned_to"] and session.get("is_admin") != 1:
        conn.close()
        return "Access denied!"

    conn.execute("UPDATE tasks SET status = 'Done' WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))

@app.route("/task/<int:task_id>", methods=["GET", "POST"])
def view_task(task_id):
    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    users = conn.execute("SELECT username FROM users").fetchall()
    conn.close()

    if not task:
        return "Task not found!"
    if session["username"] != task["assigned_to"] and session.get("is_admin") != 1:
        return "Access denied!"

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        assigned_to = request.form.get("assigned_to")
        due_date = request.form.get("due_date")
        status = request.form.get("status")

        conn = get_db_connection()
        conn.execute(
            "UPDATE tasks SET title = ?, description = ?, assigned_to = ?, due_date = ?, status = ? WHERE id = ?",
            (title, description, assigned_to, due_date, status, task_id)
        )
        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("view_task.html", task=task, users=users)

@app.route("/delete_task/<int:task_id>", methods=["POST"])
def delete_task(task_id):
    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))

@app.route("/completed_tasks")
def completed_tasks():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    conn = get_db_connection()
    tasks = conn.execute(
        "SELECT * FROM tasks WHERE assigned_to = ? AND status = 'Done' ORDER BY due_date ASC",
        (username,)
    ).fetchall()
    conn.close()

    return render_template("completed_tasks.html", username=username, tasks=tasks)

@app.route("/assigned_tasks")
def assigned_tasks():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    conn = get_db_connection()
    tasks = conn.execute(
        "SELECT * FROM tasks WHERE assigned_by = ?", (username,)
    ).fetchall()
    conn.close()

    return render_template("assigned_tasks.html", username=username, tasks=tasks)

# --------------------------
# ADMIN ROUTES
# --------------------------
@app.route("/admin_actions")
def admin_actions():
    if "username" not in session:
        return redirect(url_for("login"))
    if session.get("is_admin") != 1:
        return "Access denied! Admins only."
    return render_template("admin_actions.html")

@app.route("/create_user", methods=["GET", "POST"])
def create_user():
    if "username" not in session or session.get("is_admin") != 1:
        return "Access denied! Admins only."

    if request.method == "POST":
        username = request.form["username"].strip().lower()
        passcode = request.form.get("passcode")
        is_admin = 1 if request.form.get("is_admin") == "on" else 0

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO users (username, passcode, is_admin) VALUES (?, ?, ?)",
            (username, passcode, is_admin)
        )
        conn.commit()
        conn.close()

        return redirect(url_for("admin_actions"))

    return render_template("create_user.html")

@app.route("/manage_users", methods=["GET", "POST"])
def manage_users():
    if "username" not in session or session.get("is_admin") != 1:
        return "Access denied! Admins only."

    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users ORDER BY username ASC").fetchall()
    conn.close()

    return render_template("manage_users.html", users=users)

@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if "username" not in session or session.get("is_admin") != 1:
        return "Access denied! Admins only."

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if not user:
        conn.close()
        return "User not found!"

    if request.method == "POST":
        username = request.form["username"].strip().lower()
        passcode = request.form.get("passcode")
        is_admin = 1 if request.form.get("is_admin") == "on" else 0

        conn.execute(
            "UPDATE users SET username = ?, passcode = ?, is_admin = ? WHERE id = ?",
            (username, passcode, is_admin, user_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("manage_users"))

    conn.close()
    return render_template("edit_user.html", user=user)

@app.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    current_user = session.get("username")
    user = conn.execute("SELECT username, is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return redirect(url_for("manage_users"))

    if user["username"] == current_user:
        conn.close()
        return redirect(url_for("manage_users"))

    if user["is_admin"] == 1:
        admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]
        if admin_count <= 1:
            conn.close()
            return redirect(url_for("manage_users"))

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("manage_users"))

@app.route("/all_tasks")
def all_tasks():
    if "username" not in session or session.get("is_admin") != 1:
        return "Access denied! Admins only."

    conn = get_db_connection()
    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()

    return render_template("all_tasks.html", tasks=tasks)

@app.route("/create_task", methods=["GET", "POST"])
def create_task():
    if "username" not in session:
        return redirect(url_for("login"))

    current_user = session["username"]
    conn = get_db_connection()
    users = conn.execute("SELECT username FROM users").fetchall()
    conn.close()

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        assigned_to_list = request.form.getlist("assigned_to")
        due_date = request.form.get("due_date")
        assigned_by = current_user

        conn = get_db_connection()
        for assigned_to in assigned_to_list:
            conn.execute(
                "INSERT INTO tasks (title, description, assigned_to, assigned_by, due_date, status) VALUES (?, ?, ?, ?, ?, ?)",
                (title, description, assigned_to, assigned_by, due_date, "Pending")
            )
        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("create_task.html", users=users, current_user=current_user)

@app.route("/download_db")
def download_db():
    if "username" not in session or not session.get("is_admin"):
        return "Access denied"
    return send_file("task_app.db", as_attachment=True)

# --------------------------
# LOGOUT
# --------------------------
@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("is_admin", None)
    return redirect(url_for("login"))

# Ensure database + tables exist (important for Render)
init_db()

# --------------------------
# START SERVER
# --------------------------
if __name__ == "__main__":
    app.run()
