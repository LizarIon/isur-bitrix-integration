import sys
import os

# Добавляем корневую папку в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import schedule
import time
from src.sync.sync import sync_bidirectional
from src.logger import log_info
from src.utils.db_utils import init_db

if __name__ == "__main__":
    # Инициализация базы данных (создаёт таблицы, если их нет)
    init_db()
    
    print("🚀 ПОЛНАЯ СИНХРОНИЗАЦИЯ ИСУР-Проекты ↔ Битрикс24")
    print("   📌 Создание, обновление, родители, поиск завершённых, закрытие в ИСУР")
    print("   📌 Данные хранятся в SQLite (sync.db)\n")
    
    # Запуск по расписанию (каждые 30 минут)
    schedule.every(30).minutes.do(sync_bidirectional)
    
    # Первый запуск сразу
    sync_bidirectional()
    
    print("\n⏰ Планировщик запущен. Для остановки Ctrl+C\n")
    
    # Бесконечный цикл планировщика
    while True:
        schedule.run_pending()
        time.sleep(1)