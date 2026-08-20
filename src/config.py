import os
from dotenv import load_dotenv
from pathlib import Path

# Явно указываем путь к .env (корень проекта)
BASE_DIR = Path(__file__).parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path="env.txt")  # без точки

# === СНАЧАЛА ЧИТАЕМ ПЕРЕМЕННЫЕ ===
ISUR_LOGIN = os.getenv("ISUR_LOGIN", "Admin")
ISUR_PASSWORD = os.getenv("ISUR_PASSWORD", "")
ISUR_AUTH_URL = os.getenv("ISUR_AUTH_URL")
ISUR_API_URL = os.getenv("ISUR_API_URL")
ISUR_WORK_PARTICIPANTS_URL = os.getenv("ISUR_WORK_PARTICIPANTS_URL")

BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK")
GROUP_ID = int(os.getenv("GROUP_ID", 0) or 0)
RESPONSIBLE_ID = int(os.getenv("RESPONSIBLE_ID", 1) or 1)

SCRIPT_DIR = str(BASE_DIR)
LINKS_FILE = os.path.join(SCRIPT_DIR, "task_links.json")
DATA_FILE = os.path.join(SCRIPT_DIR, "task_data.json")
COMPLETED_FILE = os.path.join(SCRIPT_DIR, "completed_tasks.json")
CLOSED_FILE = os.path.join(SCRIPT_DIR, "closed_in_isur.json")

# === ТЕПЕРЬ МОЖНО ВЫВОДИТЬ ===
print(f"ENV_PATH: {ENV_PATH}")
print(f"Файл .env существует: {ENV_PATH.exists()}")
print(f"ISUR_AUTH_URL: {ISUR_AUTH_URL}")
print(f"BITRIX_WEBHOOK: {BITRIX_WEBHOOK}")