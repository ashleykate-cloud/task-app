from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

app = Flask(__name__)
app.secret_key = "this-is-a-secret"

DATABASE = "task_app.db"

# Database connection helper
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# LOGIN ROUTE
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
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

# DASHBOARD ROUTE
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    is_admin = session.get("is_admin", 0)

    conn = get_db_connection()
    tasks = conn.execute(
        "SELECT * FROM tasks WHERE assigned_to = ? AND status = 'Pending' ORDER BY due_date ASC",
        (username,)
    ).fetchall()
    conn.close()

    return render_template("dashboard.html", username=username, tasks=tasks, is_admin=is_admin)

@app.route("/update_status/<int:task_id>", methods=["POST"])
def update_status(task_id):
    if "username" not in session:
        return redirect(url_for("login"))

    # Only allow assigned user or admin to update
    conn = get_db_connection()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return "Task not found!"
    if session["username"] != task["assigned_to"] and session.get("is_admin") != 1:
        conn.close()
        return "Access denied!"

    # Update the status to Done
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

    # Only allow assigned user or admin to edit
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

@app.route("/admin_actions")
def admin_actions():
    if "username" not in session:
        return redirect(url_for("login"))

    # Only allow admin
    if session.get("is_admin") != 1:
        return "Access denied! Admins only."

    return render_template("admin_actions.html")

# CREATE USER (admin only)
@app.route("/create_user", methods=["GET", "POST"])
def create_user():
    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied! Admins only."

    if request.method == "POST":
        username = request.form.get("username")
        passcode = request.form.get("passcode")
        is_admin = 1 if request.form.get("is_admin") == "on" else 0

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO users (username, passcode, is_admin) VALUES (?, ?, ?)",
            (username, passcode, is_admin)
        )
        conn.commit()
        conn.close()

        # Redirect to admin actions after creating the user
        return redirect(url_for("admin_actions"))

    return render_template("create_user.html")

@app.route("/manage_users", methods=["GET", "POST"])
def manage_users():
    if "username" not in session:
        return redirect(url_for("login"))

    # Only admin
    if session.get("is_admin") != 1:
        return "Access denied! Admins only."

    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()

    return render_template("manage_users.html", users=users)

@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied! Admins only."

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if not user:
        conn.close()
        return "User not found!"

    if request.method == "POST":
        username = request.form.get("username")
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

@app.route("/all_tasks")
def all_tasks():
    if "username" not in session:
        return redirect(url_for("login"))

    # Only allow admin
    if session.get("is_admin") != 1:
        return "Access denied! Admins only."

    conn = get_db_connection()
    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()

    return render_template("all_tasks.html", tasks=tasks)

# CREATE TASK ROUTE
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
                """
                INSERT INTO tasks
                (title, description, assigned_to, assigned_by, due_date, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, description, assigned_to, assigned_by, due_date, "Pending")
            )

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template(
        "create_task.html",
        users=users,
        current_user=current_user
    )

# LOGOUT ROUTE
@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("is_admin", None)
    return redirect(url_for("login"))

# START SERVER
if __name__ == "__main__":
    app.run(debug=True)
