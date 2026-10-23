import schedule
import time
from src.sync.sync import sync_bidirectional
from src.sync.sync_full import sync_full
from src.config import RESERVE_SYNC_TIME
from src.logger import log_info

def start_timer():
    """Запускает таймеры для синхронизации."""
    # Прямая синхронизация (каждые 30 минут)
    schedule.every(5).minutes.do(sync_bidirectional)
    log_info("⏰ Таймер прямой синхронизации запущен (каждые 30 минут)")
    
    # Резервная сверка (раз в сутки, время из .env)
    schedule.every().day.at(RESERVE_SYNC_TIME).do(sync_full)
    log_info(f"⏰ Резервная сверка запущена (ежедневно в {RESERVE_SYNC_TIME})")
    
    while True:
        schedule.run_pending()
        time.sleep(1)