import requests
from src.config import BITRIX_WEBHOOK, GROUP_ID, RESPONSIBLE_ID
from src.logger import log_info, log_error
import time
import requests
from collections import deque
from src.logger import log_debug

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
    
    print(f"   📤 Отправляем задачу: {task_name[:40]}")
    print(f"      UF_ISUR_TASK_ID: {isur_id}")
    
    response = requests.post(
        f"{BITRIX_WEBHOOK}tasks.task.add",
        json=task_data,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        result = response.json()
        if "result" in result:
            task_id = result["result"]
            print(f"      ✅ Статус: 200, ID: {task_id}")
            return task_id
    
    print(f"      ❌ Ошибка: {response.status_code} - {response.text[:200]}")
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
        print(f"      ✅ Обновлено: {task_name[:40]}")
        return True
    else:
        print(f"      ❌ Ошибка обновления: {response.status_code} - {response.text[:100]}")
        return False

def get_task_info(bitrix_id):
    """Получает информацию о задаче из Битрикс24 (для поиска завершённых)"""
    try:
        response = bitrix_request_with_limiter(
            "GET",
            f"{BITRIX_WEBHOOK}task.get",
            params={"id": bitrix_id},
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            task = result.get("result", {}).get("DATA", {})
            return {
                "title": task.get("TITLE"),
                "status": task.get("REAL_STATUS"),
                "closed_date": task.get("CLOSED_DATE"),
                "bitrix_id": bitrix_id
            }
    except Exception as e:
        print(f"   ⚠️ Ошибка получения задачи {bitrix_id}: {e}")
    return None