"""Общее состояние сервиса: последняя синхронизация, время старта."""
import time
from datetime import datetime
import time

_ignore_webhooks_until = {}
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

def ignore_webhook(task_id, task_data, seconds=10):
    """Сохраняет данные, которые мы только что отправили, чтобы узнать наше эхо."""
    # Берем только название и даты, так как именно их мы синхронизируем
    payload_hash = f"{task_data.get('title')}|{task_data.get('start_date_plan')}|{task_data.get('end_date_plan')}"
    _ignore_webhooks_until[str(task_id)] = {
        "hash": payload_hash,
        "until": time.time() + seconds
    }

def is_webhook_ignored(task_id, incoming_data):
    """Проверяет, является ли вебхук нашим же эхом."""
    task_id = str(task_id)
    if task_id in _ignore_webhooks_until:
        record = _ignore_webhooks_until[task_id]
        if time.time() < record["until"]:
            # Сверяем данные: если они совпадают с тем, что мы отправляли — это эхо
            incoming_hash = f"{incoming_data.get('title')}|{incoming_data.get('start_date_plan')}|{incoming_data.get('end_date_plan')}"
            if incoming_hash == record["hash"]:
                return True
        else:
            del _ignore_webhooks_until[task_id]
    return False