from src.clients.isur_client import close_isur_task, update_isur_task
from src.clients.bitrix_client import get_task_info
from src.utils.db_utils import load_links
from src.logger import log_info, log_error

def handle_event(event, bitrix_task_id):
    """Обрабатывает события от Битрикс24."""
    links = load_links()
    
    # Найти isur_id по bitrix_id
    isur_id = None
    for key, value in links.items():
        if value == bitrix_task_id:
            isur_id = key
            break
    
    # Если задача не найдена в связках — пропускаем
    if not isur_id:
        log_info(f"Задача {bitrix_task_id} не найдена в связках, пропускаем")
        return
    
    # Получаем данные задачи из Битрикс24
    task_info = get_task_info(bitrix_task_id)
    if not task_info:
        log_error(f"Не удалось получить данные задачи {bitrix_task_id}")
        return
    
    if event == "ONTASKCOMPLETE":
        log_info(f"✅ Задача {bitrix_task_id} завершена в Битрикс")
        if close_isur_task(isur_id):
            log_info(f"   ✅ Задача {isur_id} закрыта в ИСУР")
        else:
            log_error(f"   ❌ Ошибка закрытия задачи {isur_id} в ИСУР")
    
    elif event == "ONTASKUPDATE":
        log_info(f"🔄 Задача {bitrix_task_id} обновлена в Битрикс")
        if update_isur_task(isur_id, task_info):
            log_info(f"   ✅ Задача {isur_id} обновлена в ИСУР")
        else:
            log_error(f"   ❌ Ошибка обновления задачи {isur_id} в ИСУР")
    
    else:
        log_info(f"⚠️ Неизвестное событие: {event}")