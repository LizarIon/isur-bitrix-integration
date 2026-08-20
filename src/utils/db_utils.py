import sqlite3
import json
from src.logger import log_info, log_error

DB_PATH = "sync.db"

def get_connection():
    """Возвращает соединение с БД."""
    return sqlite3.connect(DB_PATH)

def init_db():
    """Создаёт таблицы, если их нет."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Таблица связей (task_links)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_links (
                isur_id TEXT PRIMARY KEY,
                bitrix_id INTEGER NOT NULL
            )
        """)

        # Таблица данных задач (task_data)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_data (
                isur_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)

        # Таблица закрытых задач (closed_tasks)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS closed_tasks (
                isur_id TEXT PRIMARY KEY,
                closed_at TEXT NOT NULL,
                title TEXT
            )
        """)

        # === НОВАЯ ТАБЛИЦА: завершённые задачи ===
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS completed_tasks (
                isur_id TEXT PRIMARY KEY,
                bitrix_id INTEGER,
                title TEXT,
                status TEXT,
                closed_date TEXT,
                detected_at TEXT
            )
        """)

        conn.commit()
        log_info("База данных инициализирована")

def save_link(isur_id, bitrix_id):
    """Сохраняет или обновляет связь."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO task_links (isur_id, bitrix_id) VALUES (?, ?)",
            (isur_id, bitrix_id)
        )
        conn.commit()

def load_links():
    """Загружает все связи."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT isur_id, bitrix_id FROM task_links")
        return {row[0]: row[1] for row in cursor.fetchall()}

def save_task_data(isur_id, data):
    """Сохраняет полные данные задачи."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO task_data (isur_id, data) VALUES (?, ?)",
            (isur_id, json.dumps(data, ensure_ascii=False))
        )
        conn.commit()

def load_task_data():
    """Загружает все данные задач."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT isur_id, data FROM task_data")
        return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}

def save_closed_task(isur_id, closed_at, title):
    """Сохраняет закрытую задачу."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO closed_tasks (isur_id, closed_at, title) VALUES (?, ?, ?)",
            (isur_id, closed_at, title)
        )
        conn.commit()

def load_closed_tasks():
    """Загружает все закрытые задачи."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT isur_id, closed_at, title FROM closed_tasks")
        return {row[0]: {"closed_at": row[1], "title": row[2]} for row in cursor.fetchall()}

# ============================================================
# СОВМЕСТИМОСТЬ СО СТАРЫМИ ИМЕНАМИ (для постепенного перехода)
# ============================================================

# Чтобы не менять сразу все вызовы в sync.py, оставляем старые имена как алиасы
save_links = save_link
load_task_data = load_task_data  # уже есть
save_task_data = save_task_data  # уже есть

def remove_link(isur_id, links):
    """Удаляет связку (для совместимости)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_links WHERE isur_id = ?", (isur_id,))
        conn.commit()
    return True

def load_task_data():
    """Загружает task_data (для совместимости)."""
    return load_task_data()

def save_task_data(task_data):
    """Сохраняет task_data (для совместимости)."""
    for isur_id, data in task_data.items():
        save_task_data(isur_id, data)

def save_completed_list(completed_list):
    """Сохраняет список завершённых задач в БД."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM completed_tasks")
        for task in completed_list:
            cursor.execute(
                """INSERT INTO completed_tasks 
                   (isur_id, bitrix_id, title, status, closed_date, detected_at) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task["isur_id"], task["bitrix_id"], task["title"],
                 task["status"], task["closed_date"], task["detected_at"])
            )
        conn.commit()