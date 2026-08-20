import json
import os
import sqlite3
from src.utils.db_utils import DB_PATH, get_connection

# ============================================================
# ПУТИ К JSON-ФАЙЛАМ
# ============================================================

LINKS_FILE = "task_links.json"
DATA_FILE = "task_data.json"
CLOSED_FILE = "closed_in_isur.json"

def migrate_links():
    """Переносит связи из task_links.json в БД."""
    if not os.path.exists(LINKS_FILE):
        print("⚠️ task_links.json не найден, пропускаем")
        return 0

    with open(LINKS_FILE, 'r', encoding='utf-8') as f:
        links = json.load(f)

    with get_connection() as conn:
        cursor = conn.cursor()
        for isur_id, bitrix_id in links.items():
            # Если в старом файле хранился полный объект, извлекаем ID
            if isinstance(bitrix_id, dict):
                if "task" in bitrix_id and "id" in bitrix_id["task"]:
                    bitrix_id = bitrix_id["task"]["id"]
                else:
                    continue
            cursor.execute(
                "INSERT OR REPLACE INTO task_links (isur_id, bitrix_id) VALUES (?, ?)",
                (isur_id, bitrix_id)
            )
        conn.commit()

    print(f"✅ Перенесено связей: {len(links)}")
    return len(links)

def migrate_task_data():
    """Переносит данные задач из task_data.json в БД."""
    if not os.path.exists(DATA_FILE):
        print("⚠️ task_data.json не найден, пропускаем")
        return 0

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        task_data = json.load(f)

    with get_connection() as conn:
        cursor = conn.cursor()
        for isur_id, data in task_data.items():
            cursor.execute(
                "INSERT OR REPLACE INTO task_data (isur_id, data) VALUES (?, ?)",
                (isur_id, json.dumps(data, ensure_ascii=False))
            )
        conn.commit()

    print(f"✅ Перенесено задач: {len(task_data)}")
    return len(task_data)

def migrate_closed_tasks():
    """Переносит закрытые задачи из closed_in_isur.json в БД."""
    if not os.path.exists(CLOSED_FILE):
        print("⚠️ closed_in_isur.json не найден, пропускаем")
        return 0

    with open(CLOSED_FILE, 'r', encoding='utf-8') as f:
        closed_tasks = json.load(f)

    with get_connection() as conn:
        cursor = conn.cursor()
        for isur_id, info in closed_tasks.items():
            closed_at = info.get("closed_at")
            title = info.get("title", "")
            cursor.execute(
                "INSERT OR REPLACE INTO closed_tasks (isur_id, closed_at, title) VALUES (?, ?, ?)",
                (isur_id, closed_at, title)
            )
        conn.commit()

    print(f"✅ Перенесено закрытых задач: {len(closed_tasks)}")
    return len(closed_tasks)

# ============================================================
# ЗАПУСК МИГРАЦИИ
# ============================================================

if __name__ == "__main__":
    print("🚀 МИГРАЦИЯ ДАННЫХ ИЗ JSON В SQLite")
    print("=" * 50)

    # Создаём таблицы (если их нет)
    from src.utils.db_utils import init_db
    init_db()

    # Переносим данные
    total_links = migrate_links()
    total_data = migrate_task_data()
    total_closed = migrate_closed_tasks()

    print("=" * 50)
    print(f"📊 ИТОГО ПЕРЕНЕСЕНО:")
    print(f"   Связей: {total_links}")
    print(f"   Данных задач: {total_data}")
    print(f"   Закрытых задач: {total_closed}")
    print("\n✅ Миграция завершена!")
    print("   JSON-файлы можно удалить или оставить как резерв.")