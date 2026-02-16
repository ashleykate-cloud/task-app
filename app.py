from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
import datetime
from zoneinfo import ZoneInfo
import os

# --------------------------
# 1️ Initialize app
# --------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# --------------------------
# 2️ Database paths
# --------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if os.getenv("RENDER"):  # Render-only
    DATA_DIR = "/opt/render/project/data"
    os.makedirs(DATA_DIR, exist_ok=True)
    DB_PATH = os.path.join(DATA_DIR, "task_app.db")
else:
    DB_PATH = os.path.join(BASE_DIR, "task_app.db")

APP_TZ = ZoneInfo("America/Los_Angeles")

#print("👉 Using database at:", DB_PATH)
#print("UTC:", datetime.datetime.utcnow())
#print("Local:", datetime.datetime.now(APP_TZ))

# --------------------------
# 3️ Database helpers
# --------------------------
def today_local():
    return datetime.datetime.now(APP_TZ).date()

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
            passcode TEXT,
            is_admin INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            due_date TEXT,
            status TEXT,
            assigned_to TEXT,
            assigned_by TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def bootstrap_admin():
    conn = get_db_connection()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    if user_count == 0:
        conn.execute(
            "INSERT INTO users (username, passcode, is_admin) VALUES (?, ?, ?)",
            ("admin", "6160", 1)
        )
        conn.commit()
        print("⚠️ Bootstrapped default admin: admin / admin")

    conn.close()

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
            "SELECT * FROM users WHERE username = ? AND passcode = ?",
            (username, passcode)
        ).fetchone()
        conn.close()

        if user:
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            return redirect(url_for("dashboard"))
        else:
            return "Invalid username or passcode"

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
          AND status != 'Done'
        ORDER BY
            CASE WHEN due_date IS NULL OR due_date = '' THEN 1 ELSE 0 END,
            due_date ASC
        """,
        (username,)
    ).fetchall()
    conn.close()

    today = today_local()

    # Convert sqlite3.Row → dict and parse due_date
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

    # Confetti: only if no tasks due today AND no overdue tasks
    tasks_due_today = [t for t in tasks_list if t['due_date'] == today and t['status'] != 'Done']
    overdue_tasks = [t for t in tasks_list if t['due_date'] and t['due_date'] < today and t['status'] != 'Done']
    confetti_flag = len(tasks_due_today) == 0 and len(overdue_tasks) == 0

    return render_template(
        "dashboard.html",
        tasks=tasks_list,
        username=username,
        is_admin=is_admin,
        today=today,
        confetti=confetti_flag
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

    current_user = session["username"]

    conn = get_db_connection()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    users = conn.execute("SELECT username FROM users").fetchall()
    conn.close()

    if not task:
        return "Task not found!"
    if (
        current_user != task["assigned_to"]
        and current_user != task["assigned_by"]
        and session.get("is_admin") != 1
    ):
        return "Access denied!"

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        assigned_to = request.form.get("assigned_to")
        due_date = request.form.get("due_date")
        done_checked = request.form.get("done")
        status = "Done" if done_checked else "Pending"

        # Determine who should be listed as assigned_by
        if assigned_to != task["assigned_to"]:
            new_assigned_by = current_user
        else:
            new_assigned_by = task["assigned_by"]

        conn = get_db_connection()
        conn.execute(
            """
            UPDATE tasks
            SET title = ?,
                description = ?,
                assigned_to = ?,
                assigned_by = ?,
                due_date = ?,
                status = ?
            WHERE id = ?
            """,
            (title, description, assigned_to, new_assigned_by, due_date, status, task_id)
        )
        conn.commit()
        conn.close()

        # 👇 NEW: Check which button was pressed
        if request.form.get("action") == "close":
            return redirect(url_for("dashboard"))
        else:
            return redirect(url_for("view_task", task_id=task_id))

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
        """
        SELECT * FROM tasks
        WHERE assigned_to = ? AND status = 'Done'
        """,
        (username,)
    ).fetchall()
    conn.close()

    tasks_list = []

    for task in tasks:
        task_dict = dict(task)
        due_date_str = task_dict.get("due_date")

        # Convert due_date string to date object
        if due_date_str:
            try:
                task_dict["due_date"] = datetime.datetime.strptime(
                    due_date_str, "%Y-%m-%d"
                ).date()
            except ValueError:
                task_dict["due_date"] = None
        else:
            task_dict["due_date"] = None

        tasks_list.append(task_dict)

    tasks_list.sort(
        key=lambda t: (t["due_date"] is None, t["due_date"]),
        reverse=True
    )

    return render_template(
        "completed_tasks.html",
        username=username,
        tasks=tasks_list
    )

@app.route("/assigned_tasks")
def assigned_tasks():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]

    conn = get_db_connection()
    tasks = conn.execute(
        """
        SELECT * FROM tasks
        WHERE assigned_by = ?
          AND assigned_to != ?
        """,
        (username, username)
    ).fetchall()
    conn.close()

    today = today_local()
    tasks_list = []

    for task in tasks:
        task_dict = dict(task)
        due_date_str = task_dict.get("due_date")

        if due_date_str:
            try:
                task_dict["due_date"] = datetime.datetime.strptime(
                    due_date_str, "%Y-%m-%d"
                ).date()
            except ValueError:
                task_dict["due_date"] = None
        else:
            task_dict["due_date"] = None

        tasks_list.append(task_dict)

    tasks_list.sort(
        key=lambda t: (t["due_date"] is None, t["due_date"]),
        reverse=True
    )

    return render_template(
        "assigned_tasks.html",
        username=username,
        tasks=tasks_list,
        today=today
    )

@app.route("/filter_tasks")
def filter_tasks():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    selected_user = request.args.get("assigned_by")  # from dropdown

    conn = get_db_connection()

    # Get unique assigners for this user
    assigners = conn.execute(
        """
        SELECT DISTINCT assigned_by
        FROM tasks
        WHERE assigned_to = ?
        """,
        (username,)
    ).fetchall()

    users = [row["assigned_by"] for row in assigners]

    # Base query
    query = """
        SELECT * FROM tasks
        WHERE assigned_to = ?
          AND status != 'Done'
    """
    params = [username]

    # Apply filter if selected
    if selected_user == "me":
        query += " AND assigned_by = ?"
        params.append(username)

    elif selected_user == "others":
        query += " AND assigned_by != ?"
        params.append(username)

    elif selected_user:
        query += " AND assigned_by = ?"
        params.append(selected_user)

    tasks = conn.execute(query, tuple(params)).fetchall()
    conn.close()

    # Convert due_date strings → date objects
    tasks_list = []
    for task in tasks:
        task_dict = dict(task)
        due_date_str = task_dict.get("due_date")

        if due_date_str:
            try:
                task_dict["due_date"] = datetime.datetime.strptime(
                    due_date_str, "%Y-%m-%d"
                ).date()
            except ValueError:
                task_dict["due_date"] = None
        else:
            task_dict["due_date"] = None

        tasks_list.append(task_dict)

    # Sort: soonest due first, None last
    tasks_list.sort(
        key=lambda t: (t["due_date"] is None, t["due_date"] or datetime.date.max)
    )

    return render_template(
        "filter_tasks.html",
        tasks=tasks_list,
        users=users,
        selected_user=selected_user,
        username=username,
        today=today_local()
    )

@app.route("/edit_account", methods=["GET", "POST"])
def edit_account():
    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (session["username"],)
    ).fetchone()

    if request.method == "POST":
        new_passcode = request.form.get("new_passcode", "")
        confirm_passcode = request.form.get("confirm_passcode", "")

        if not new_passcode:
            return "Passcode cannot be empty", 400
        if new_passcode != confirm_passcode:
            return "Passcodes do not match", 400

        # Update passcode
        conn.execute(
            "UPDATE users SET passcode = ? WHERE id = ?",
            (new_passcode, user["id"])
        )
        conn.commit()
        conn.close()
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("edit_account.html")

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

    # Fetch users for the "Assign To" list
    conn = get_db_connection()
    users = conn.execute("SELECT username FROM users").fetchall()
    conn.close()

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        assigned_to_list = request.form.getlist("assigned_to")
        due_date = request.form.get("due_date")
        assigned_by = current_user

        # Default to today if no date selected
        if not due_date:
            due_date = today_local().isoformat()

        conn = get_db_connection()
        for assigned_to in assigned_to_list:
            conn.execute(
                "INSERT INTO tasks (title, description, assigned_to, assigned_by, due_date, status) VALUES (?, ?, ?, ?, ?, ?)",
                (title, description, assigned_to, assigned_by, due_date, "Pending")
            )
        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    # Pass today's date to template for pre-filling
    today = today_local().isoformat()
    return render_template(
        "create_task.html",
        users=users,
        current_user=current_user,
        today=today  # <--- template uses this for value="{{ today }}"
    )

@app.route("/download_db")
def download_db():
    if "username" not in session or not session.get("is_admin"):
        return "Access denied"
    return send_file(DB_PATH, as_attachment=True)

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
bootstrap_admin()

# --------------------------
# START SERVER
# --------------------------
if __name__ == "__main__":
    app.run()
