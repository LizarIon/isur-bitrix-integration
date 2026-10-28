from src.clients.isur_client import (
    close_isur_task, update_isur_task,
    sync_task_participants, get_isur_task, reopen_isur_task, set_isur_factual_start
)
from src.clients.bitrix_client import get_task_info
from src.utils.db_utils import load_links
from src.logger import log_info, log_error
from src.state import is_webhook_ignored

def handle_event(event, bitrix_task_id):
    """Обрабатывает события от Битрикс24."""
    links = load_links()
    
    isur_id = None
    for key, value in links.items():
        if value == bitrix_task_id:
            isur_id = key
            break
    
    if not isur_id:
        log_info(f"Задача {bitrix_task_id} не найдена в связках, пропускаем")
        return
    
    task_info = get_task_info(bitrix_task_id)
    if not task_info:
        log_error(f"Не удалось получить данные задачи {bitrix_task_id}")
        return

    if is_webhook_ignored(bitrix_task_id, task_info):
        log_info(f"Игнорируем эхо-вебхук для {bitrix_task_id} (наше же изменение)")
        return
    
    if event == "ONTASKCOMPLETE":
        log_info(f"✅ Задача {bitrix_task_id} завершена в Битрикс")
        if close_isur_task(isur_id):
            log_info(f"   ✅ Задача {isur_id} закрыта в ИСУР")
        else:
            log_error(f"   ❌ Ошибка закрытия задачи {isur_id} в ИСУР")
    
    elif event == "ONTASKUPDATE":
        log_info(f"🔄 Задача {bitrix_task_id} обновлена в Битрикс")
        
        if task_info and str(task_info.get("status")) == "5":
            log_info(f"   Задача {bitrix_task_id} завершена, закрываем в ИСУР...")
            if close_isur_task(isur_id):
                log_info(f"   ✅ Задача {isur_id} закрыта в ИСУР")
            else:
                log_error(f"   ❌ Ошибка закрытия задачи {isur_id} в ИСУР")
        else:
            isur_task = get_isur_task(isur_id)
            if isur_task and isur_task.get("FactualFinish"):
                log_info(f"   🔄 Задача {isur_id[:8]}... была закрыта в ИСУР, возвращаем в работу")
                reopen_isur_task(isur_id)

            # 1. Сначала обновляем даты (update_isur_task)
            if update_isur_task(isur_id, task_info):
                log_info(f"   ✅ Задача {isur_id} обновлена в ИСУР")
                sync_task_participants(isur_id, bitrix_task_id)
            else:
                log_error(f"   ❌ Ошибка обновления задачи {isur_id} в ИСУР")

            # 2. ПОТОМ ставим FactualStart (если статус "в работе")
            bitrix_status = str(task_info.get("status"))
            if bitrix_status == "3":
                set_isur_factual_start(isur_id)
    
    else:
        log_info(f"⚠️ Неизвестное событие: {event}")