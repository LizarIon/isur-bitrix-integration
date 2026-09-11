"""Общее состояние сервиса: последняя синхронизация, время старта."""
import time
from datetime import datetime

_start_time = time.time()
_last_sync = {
    "time": None,
    "status": "never",     # never / success / error
    "message": None
}

def set_last_sync(status, message=None):
    """Обновляет информацию о последней синхронизации."""
    _last_sync["time"] = datetime.now().isoformat()
    _last_sync["status"] = status
    _last_sync["message"] = message

def get_last_sync():
    """Возвращает информацию о последней синхронизации."""
    return dict(_last_sync)

def get_uptime():
    """Возвращает время работы сервиса в секундах."""
    return int(time.time() - _start_time)