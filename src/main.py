import threading
from src.webhook.server import start_webhook_server
from src.sync.timer import start_timer
from src.logger import log_info

if __name__ == "__main__":
    log_info("🚀 ЗАПУСК ИНТЕГРАЦИИ")
    
    # Запускаем таймер в отдельном потоке
    timer_thread = threading.Thread(target=start_timer, daemon=True)
    timer_thread.start()
    
    # Запускаем веб-сервер (основной поток)
    start_webhook_server()