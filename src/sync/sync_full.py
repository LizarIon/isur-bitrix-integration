from src.clients.isur_client import get_isur_token, get_isur_works, close_isur_task, update_isur_task
from src.clients.bitrix_client import get_bitrix_tasks
from src.utils.db_utils import load_links, log_missed_webhook
from src.logger import log_info, log_error

def sync_full():
    """Полная сверка (резервная синхронизация)."""
    log_info("🔄 ЗАПУСК РЕЗЕРВНОЙ СВЕРКИ")
    
    links = load_links()
    token = get_isur_token()
    isur_tasks = get_isur_works(token)
    bitrix_tasks = get_bitrix_tasks()
    
    isur_dict = {task["Id"]: task for task in isur_tasks}
    bitrix_dict = {task["id"]: task for task in bitrix_tasks}
    
    for isur_id, bitrix_id in links.items():
        isur_task = isur_dict.get(isur_id)
        bitrix_task = bitrix_dict.get(bitrix_id)
        
        if not isur_task or not bitrix_task:
            continue
        
        # Проверка статуса завершения
        if bitrix_task.get("CLOSED_DATE") or bitrix_task.get("REAL_STATUS") == "5":
            if isur_task.get("Status") != "Completed":
                if close_isur_task(isur_id):
                    log_info(f"   ✅ Закрыта задача {isur_id} (сверка)")
                    log_missed_webhook(isur_id, bitrix_id, "status", "completed", isur_task.get("Status"), "closed")
                else:
                    log_error(f"   ❌ Ошибка закрытия {isur_id} (сверка)")
        
        # Проверка дат
        if bitrix_task.get("END_DATE_PLAN") != isur_task.get("Finish"):
            if update_isur_task(isur_id, bitrix_task):
                log_info(f"   ✅ Обновлена дата окончания {isur_id} (сверка)")
                log_missed_webhook(isur_id, bitrix_id, "finish", bitrix_task.get("END_DATE_PLAN"), isur_task.get("Finish"), "updated")
        
        if bitrix_task.get("START_DATE_PLAN") != isur_task.get("Start"):
            if update_isur_task(isur_id, bitrix_task):
                log_info(f"   ✅ Обновлена дата начала {isur_id} (сверка)")
                log_missed_webhook(isur_id, bitrix_id, "start", bitrix_task.get("START_DATE_PLAN"), isur_task.get("Start"), "updated")
    
    log_info("✅ РЕЗЕРВНАЯ СВЕРКА ЗАВЕРШЕНА")