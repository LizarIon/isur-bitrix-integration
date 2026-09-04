import sqlite3
import json
from datetime import datetime
from src.logger import log_info

DB_PATH = "sync.db"

def get_connection():
    """Возвращает соединение с БД и включает поддержку внешних ключей."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Создаёт таблицы, если их нет."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Таблица связей (task_links)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_links (
                isur_id TEXT NOT NULL,
                bitrix_id TEXT NOT NULL,
                PRIMARY KEY (isur_id, bitrix_id)
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

        # Таблица завершённых задач (completed_tasks)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS completed_tasks (
                isur_id TEXT PRIMARY KEY,
                bitrix_id TEXT,
                title TEXT,
                status TEXT,
                closed_date TEXT,
                detected_at TEXT
            )
        """)

        # Таблица потерянных вебхуков (missed_webhooks)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS missed_webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                isur_id TEXT NOT NULL,
                bitrix_id TEXT NOT NULL,
                field TEXT NOT NULL,
                bitrix_value TEXT,
                isur_value TEXT,
                action TEXT NOT NULL
            )
        """)

        conn.commit()
        log_info("База данных инициализирована")

# ============================================================
# РАБОТА С task_links
# ============================================================

def save_link(isur_id, bitrix_id):
    """Сохраняет или обновляет связь."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO task_links (isur_id, bitrix_id) VALUES (?, ?)",
            (isur_id, str(bitrix_id))
        )
        conn.commit()

def load_links():
    """Загружает все связи."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT isur_id, bitrix_id FROM task_links")
        return {row[0]: row[1] for row in cursor.fetchall()}

def remove_link(isur_id):
    """Удаляет связку по isur_id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_links WHERE isur_id = ?", (isur_id,))
        conn.commit()

# ============================================================
# РАБОТА С task_data
# ============================================================

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

# ============================================================
# РАБОТА С closed_tasks
# ============================================================

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
# РАБОТА С completed_tasks
# ============================================================

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
                (task["isur_id"], str(task["bitrix_id"]), task["title"],
                 task["status"], task["closed_date"], task["detected_at"])
            )
        conn.commit()

# ============================================================
# РАБОТА С missed_webhooks
# ============================================================

def log_missed_webhook(isur_id, bitrix_id, field, bitrix_value, isur_value, action):
    """Записывает расхождение вебхука в БД."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO missed_webhooks (timestamp, isur_id, bitrix_id, field, bitrix_value, isur_value, action)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            isur_id,
            str(bitrix_id),
            field,
            bitrix_value,
            isur_value,
            action
        ))
        conn.commit()

def get_missed_webhooks(limit=20):
    """Возвращает последние записи о потерянных вебхуках."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM missed_webhooks ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        return cursor.fetchall()