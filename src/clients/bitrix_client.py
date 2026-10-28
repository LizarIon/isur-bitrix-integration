import requests
from src.config import BITRIX_WEBHOOK, GROUP_ID, RESPONSIBLE_ID
from src.logger import log_info, log_error, log_debug
import time
from collections import deque

# ============================================================
# КОНТРОЛЬ ЧАСТОТЫ ЗАПРОСОВ К БИТРИКС24
# ============================================================

class RateLimiter:
    """Ограничивает количество запросов в секунду."""
    def __init__(self, max_requests_per_second=2):
        self.max_requests = max_requests_per_second
        self.requests = deque()

    def wait_if_needed(self):
        now = time.time()
        # Удаляем запросы старше 1 секунды
        while self.requests and self.requests[0] < now - 1:
            self.requests.popleft()

        if len(self.requests) >= self.max_requests:
            sleep_time = 1 - (now - self.requests[0])
            if sleep_time > 0:
                log_debug(f"Ограничение частоты: ожидание {sleep_time:.2f}с")
                time.sleep(sleep_time + 0.01)

        self.requests.append(time.time())

# Глобальный экземпляр ограничителя (2 запроса в секунду)
rate_limiter = RateLimiter(max_requests_per_second=2)

def bitrix_request_with_limiter(method, url, **kwargs):
    """Выполняет запрос к Битрикс24 с контролем частоты."""
    rate_limiter.wait_if_needed()
    return requests.request(method, url, **kwargs)

# ============================================================
# РАБОТА С API БИТРИКС24
# ============================================================

def check_bitrix_task_exists(bitrix_id):
    response = requests.get(
        f"{BITRIX_WEBHOOK}tasks.task.get",
        params={"id": bitrix_id}
    )
    
    if response.status_code == 200:
        result = response.json()
        if "error" in result:
            return False
        if "result" in result and result["result"]:
            return True
    return False

def create_bitrix_task(work, links):
    # Безопасное получение названия
    if isinstance(work, str):
        task_name = work
    else:
        task_name = work.get("Name")
        if task_name is None or task_name.strip() == "":
            raise Exception("Пропущена задача без названия")
    
    isur_id = work.get("Id") or work.get("id")
    
    start = None
    finish = None
    if isinstance(work, dict):
        start = work.get("Start")
        finish = work.get("Finish")
    
    desc = f"Задача из ИСУР-Проекты\n"
    if start:
        desc += f"📅 Начало: {start}\n"
    if finish:
        desc += f"📅 Окончание: {finish}"
    
    task_data = {
        "fields": {
            "TITLE": task_name,
            "DESCRIPTION": desc,
            "RESPONSIBLE_ID": RESPONSIBLE_ID,
            "GROUP_ID": GROUP_ID,
            "UF_ISUR_TASK_ID": isur_id,
        }
    }
    
    if start:
        task_data["fields"]["START_DATE_PLAN"] = start.split("T")[0]
    if finish:
        task_data["fields"]["END_DATE_PLAN"] = finish.split("T")[0]
        task_data["fields"]["DEADLINE"] = finish
    
    log_info(f"Отправляем задачу: {task_name[:40]}")
    log_info(f"UF_ISUR_TASK_ID: {isur_id}")
    
    response = requests.post(
        f"{BITRIX_WEBHOOK}tasks.task.add",
        json=task_data,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        result = response.json()
        if "result" in result:
            result_data = result["result"]
            # Битрикс возвращает {"task": {"id": "3075", ...}}
            if isinstance(result_data, dict) and "task" in result_data:
                task_id = result_data["task"].get("id")
            else:
                task_id = result_data
            log_info(f"Задача создана, ID: {task_id}")
            return task_id
    
    log_error(f"Ошибка создания задачи: {response.status_code} - {response.text[:200]}")
    raise Exception(f"Ошибка создания задачи: {response.text}")

def update_bitrix_task(bitrix_id, work, links):
    # Безопасное получение названия
    if isinstance(work, str):
        task_name = work
    else:
        task_name = work.get("Name")
        if task_name is None:
            task_name = "Без названия"
    
    start = None
    finish = None
    if isinstance(work, dict):
        start = work.get("Start")
        finish = work.get("Finish")
    
    desc = f"Задача из ИСУР-Проекты\n"
    if start:
        desc += f"📅 Начало: {start}\n"
    if finish:
        desc += f"📅 Окончание: {finish}"
    
    update_data = {
        "fields": {
            "TITLE": task_name,
            "DESCRIPTION": desc,
        }
    }
    
    if start:
        update_data["fields"]["START_DATE_PLAN"] = start.split("T")[0]
    if finish:
        update_data["fields"]["END_DATE_PLAN"] = finish.split("T")[0]
        update_data["fields"]["DEADLINE"] = finish
    
    response = requests.post(
        f"{BITRIX_WEBHOOK}tasks.task.update",
        json={"id": bitrix_id, **update_data},
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        log_info(f"Обновлено: {task_name[:40]}")
        
        # ДОБАВЛЕНО: Запоминаем, что мы только что отправили (защита от эха)
        from src.state import ignore_webhook
        ignore_webhook(bitrix_id, {"title": task_name, "start_date_plan": start, "end_date_plan": finish}, 10)
        
        return True
    else:
        log_error(f"Ошибка обновления задачи: {response.status_code} - {response.text[:100]}")
        return False

def get_task_info(bitrix_id):
    """Получает информацию о задаче из Битрикс24."""
    try:
        response = bitrix_request_with_limiter(
            "GET",
            f"{BITRIX_WEBHOOK}task.get",
            params={"id": bitrix_id},
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            data = result.get("result", {}).get("DATA", {})
            task = result.get("result", {}).get("task", {})

            # status: сначала из task (где он есть), потом из DATA
            status = task.get("status") or data.get("status") or data.get("REAL_STATUS")

            return {
                "title": data.get("TITLE") or task.get("title"),
                "status": status,
                "real_status": data.get("REAL_STATUS"),
                "closed_date": data.get("CLOSED_DATE"),
                "start_date_plan": data.get("START_DATE_PLAN"),
                "end_date_plan": data.get("DEADLINE"),
                "bitrix_id": bitrix_id
            }
    except Exception as e:
        log_error(f"Ошибка получения задачи {bitrix_id}: {e}")
    return None

def get_bitrix_tasks():
    """Получает все задачи из Битрикс24 (для резервной сверки)."""
    all_tasks = []
    start = 0

    while True:
        response = bitrix_request_with_limiter(
            "POST",
            f"{BITRIX_WEBHOOK}tasks.task.list",
            json={
                "filter": {"GROUP_ID": GROUP_ID} if GROUP_ID else {},
                "select": [
                    "ID", "TITLE", "STATUS", "REAL_STATUS", "CLOSED_DATE",
                    "START_DATE_PLAN", "END_DATE_PLAN", "RESPONSIBLE_ID"
                ],
                "start": start
            },
            timeout=30
        )

        if response.status_code != 200:
            log_error(f"Ошибка получения задач из Битрикс24: {response.status_code} - {response.text[:200]}")
            break

        result = response.json()
        tasks = result.get("result", {}).get("tasks", [])

        # Приводим ключи к нижнему регистру, как ожидает sync_full.py
        for task in tasks:
            all_tasks.append({k.lower(): v for k, v in task.items()})

        next_start = result.get("next")
        if next_start is None:
            break
        start = next_start

    log_info(f"Получено задач из Битрикс24: {len(all_tasks)}")
    return all_tasks

def create_bitrix_group(group_name):
    """Создает рабочую группу (проект) в Битриксе и возвращает её ID."""
    url = f"{BITRIX_WEBHOOK}sonet_group.create"
    payload = {
        "NAME": group_name[:100], # Ограничение длины названия
        "DESCRIPTION": f"Проект ИСУР: {group_name}",
        "VISIBLE": "Y",
        "OPENED": "N"
    }
    
    response = bitrix_request_with_limiter("POST", url, json=payload, timeout=30)
    
    if response.status_code == 200:
        result = response.json()
        if "result" in result:
            group_id = result["result"]
            log_info(f"Создана группа Битрикс '{group_name}' с ID: {group_id}")
            return str(group_id)
            
    log_error(f"Ошибка создания группы '{group_name}': {response.text[:200]}")
    return None