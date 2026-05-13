from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    send_from_directory
)

import sqlite3
from datetime import datetime
import os

app = Flask(__name__)

DB_NAME = "taskdeqbot.db"
UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =====================================================
# DATABASE INIT
# =====================================================

def init_db():

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # TASK TABLE
    cursor.execute("""

    CREATE TABLE IF NOT EXISTS tasks (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        no_task TEXT UNIQUE,

        kategori TEXT,

        judul TEXT,
        detail TEXT,
        detail_tambahan TEXT,
        file_update TEXT,
        sumber_master TEXT,
        metode TEXT,

        ai_agent TEXT,

        push_github TEXT,
        date_finish TEXT,
        kendala TEXT,

        status TEXT,
        github_update TEXT,

        ss_design TEXT,

        created_at TEXT

    )

    """)

    # CATEGORY TABLE
    cursor.execute("""

    CREATE TABLE IF NOT EXISTS categories (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        nama_kategori TEXT UNIQUE

    )

    """)

    conn.commit()
    conn.close()


# =====================================================
# HOME
# =====================================================

@app.route("/")
def home():
    return render_template("taskdeqbot.html")


# =====================================================
# LOAD IMAGE
# =====================================================

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# =====================================================
# SAVE CATEGORY
# =====================================================

@app.route("/save_category", methods=["POST"])
def save_category():

    try:

        nama_kategori = request.json.get(
            "nama_kategori"
        )

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""

        INSERT INTO categories (
            nama_kategori
        )

        VALUES (?)

        """, (nama_kategori,))

        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": "Kategori berhasil disimpan"
        })

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        })


# =====================================================
# GET CATEGORY
# =====================================================

@app.route("/get_categories")
def get_categories():

    conn = sqlite3.connect(DB_NAME)

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""

    SELECT * FROM categories
    ORDER BY id DESC

    """)

    rows = cursor.fetchall()

    categories = []

    for row in rows:
        categories.append(dict(row))

    conn.close()

    return jsonify(categories)


# =====================================================
# SAVE TASK
# =====================================================

@app.route("/save_task", methods=["POST"])
def save_task():

    try:

        task_id = request.form.get("task_id")

        no_task = request.form.get("no_task")

        kategori = request.form.get("kategori")

        judul = request.form.get("judul")
        detail = request.form.get("detail")
        detail_tambahan = request.form.get(
            "detail_tambahan"
        )

        file_update = request.form.get(
            "file_update"
        )

        sumber_master = request.form.get(
            "sumber_master"
        )

        metode = request.form.get("metode")

        ai_agent = request.form.get(
            "ai_agent"
        )

        push_github = request.form.get(
            "push_github"
        )

        date_finish = request.form.get(
            "date_finish"
        )

        kendala = request.form.get("kendala")

        status = request.form.get("status")

        github_update = request.form.get(
            "github_update"
        )

        ss_file = request.files.get(
            "ss_design"
        )

        conn = sqlite3.connect(DB_NAME)

        conn.row_factory = sqlite3.Row

        cursor = conn.cursor()

        # CHECK DUPLICATE
        if not task_id:

            cursor.execute("""

            SELECT * FROM tasks
            WHERE no_task=?

            """, (no_task,))

            existing = cursor.fetchone()

            if existing:

                conn.close()

                return jsonify({
                    "status": "error",
                    "message": "NO TASK SUDAH ADA"
                })

        filename = ""

        if task_id:

            cursor.execute("""

            SELECT ss_design
            FROM tasks
            WHERE id=?

            """, (task_id,))

            old_task = cursor.fetchone()

            if old_task:
                filename = old_task["ss_design"]

        if ss_file and ss_file.filename != "":

            filename = ss_file.filename

            save_path = os.path.join(
                UPLOAD_FOLDER,
                filename
            )

            ss_file.save(save_path)

        # UPDATE
        if task_id:

            cursor.execute("""

            UPDATE tasks SET

                no_task=?,
                kategori=?,
                judul=?,
                detail=?,
                detail_tambahan=?,
                file_update=?,
                sumber_master=?,
                metode=?,
                ai_agent=?,
                push_github=?,
                date_finish=?,
                kendala=?,
                status=?,
                github_update=?,
                ss_design=?

            WHERE id=?

            """, (

                no_task,
                kategori,
                judul,
                detail,
                detail_tambahan,
                file_update,
                sumber_master,
                metode,
                ai_agent,
                push_github,
                date_finish,
                kendala,
                status,
                github_update,
                filename,
                task_id

            ))

            message = "TASK UPDATED"

        else:

            # INSERT
            cursor.execute("""

            INSERT INTO tasks (

                no_task,
                kategori,
                judul,
                detail,
                detail_tambahan,
                file_update,
                sumber_master,
                metode,
                ai_agent,
                push_github,
                date_finish,
                kendala,

                status,
                github_update,

                ss_design,

                created_at

            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            """, (

                no_task,
                kategori,
                judul,
                detail,
                detail_tambahan,
                file_update,
                sumber_master,
                metode,
                ai_agent,
                push_github,
                date_finish,
                kendala,

                status,
                github_update,

                filename,

                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            ))

            message = "TASK SAVED"

        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": message
        })

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        })


# =====================================================
# GET TASKS
# =====================================================

@app.route("/get_tasks")
def get_tasks():

    conn = sqlite3.connect(DB_NAME)

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""

    SELECT * FROM tasks

    ORDER BY
    CASE
        WHEN date_finish IS NULL
        OR date_finish=''
        THEN 1
        ELSE 0
    END,

    date_finish ASC

    """)

    rows = cursor.fetchall()

    tasks = []

    for row in rows:
        tasks.append(dict(row))

    conn.close()

    return jsonify(tasks)


# =====================================================
# RUN SERVER
# =====================================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5001
    )