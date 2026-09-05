import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading
from src.webhook.server import start_webhook_server
from src.sync.timer import start_timer
from src.logger import log_info
from src.sync.sync import sync_bidirectional
from src.utils.db_utils import init_db

if __name__ == "__main__":
    # Инициализация базы данных
    init_db()
    
    log_info("🚀 ЗАПУСК ИНТЕГРАЦИИ")
    
    # Первый запуск синхронизации (опционально)
    sync_bidirectional()
    
    # Запускаем таймер в отдельном потоке
    timer_thread = threading.Thread(target=start_timer, daemon=True)
    timer_thread.start()
    
    # Запускаем веб-сервер (основной поток)
    start_webhook_server()