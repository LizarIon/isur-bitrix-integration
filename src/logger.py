import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Папка для логов
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "sync.log")

# Основной логгер
logger = logging.getLogger("ISUR-Bitrix")
logger.setLevel(logging.DEBUG)
logger.propagate = False

# Формат сообщений
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Обработчик для файла с ротацией (10 МБ, 5 бэкапов)
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,   # 10 МБ
    backupCount=5,
    encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Обработчик для консоли (только INFO и выше)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Добавляем обработчики
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Удобные функции-обёртки
def log_debug(message):
    logger.debug(message)

def log_info(message):
    logger.info(message)

def log_warning(message):
    logger.warning(message)

def log_error(message):
    logger.error(message)