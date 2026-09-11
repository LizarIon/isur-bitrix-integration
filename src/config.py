import os
from pathlib import Path
from dotenv import load_dotenv

# === ПУТИ К ФАЙЛАМ ===
BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем .env из корня проекта (явный путь)
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# === НАСТРОЙКИ ИСУР-Проекты ===
ISUR_LOGIN = os.getenv("ISUR_LOGIN", "Admin")
ISUR_PASSWORD = os.getenv("ISUR_PASSWORD", "")
ISUR_AUTH_URL = os.getenv("ISUR_AUTH_URL")
ISUR_API_URL = os.getenv("ISUR_API_URL")
ISUR_WORK_PARTICIPANTS_URL = os.getenv("ISUR_WORK_PARTICIPANTS_URL")
ISUR_EMPLOYEES_URL = os.getenv("ISUR_EMPLOYEES_URL")

# === НАСТРОЙКИ БИТРИКС24 ===
BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK")
GROUP_ID = int(os.getenv("GROUP_ID", 0) or 0)
RESPONSIBLE_ID = int(os.getenv("RESPONSIBLE_ID", 1) or 1)

# === ВРЕМЯ РЕЗЕРВНОЙ СВЕРКИ ===
RESERVE_SYNC_TIME = os.getenv("RESERVE_SYNC_TIME", "03:00")