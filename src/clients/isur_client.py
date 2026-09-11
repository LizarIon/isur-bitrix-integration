import requests
import time
from collections import deque
from datetime import datetime
import urllib3
from src.config import (
    ISUR_LOGIN, ISUR_PASSWORD, ISUR_AUTH_URL,
    ISUR_API_URL, ISUR_WORK_PARTICIPANTS_URL
)
from src.logger import log_info, log_error, log_debug, log_warning
from src.exceptions import ISURAuthError, ISURAPIError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# КОНТРОЛЬ ЧАСТОТЫ ЗАПРОСОВ К ИСУР
# ============================================================

class RateLimiter:
    """Ограничивает количество запросов в секунду."""
    def __init__(self, max_requests_per_second=5):
        self.max_requests = max_requests_per_second
        self.requests = deque()

    def wait_if_needed(self):
        now = time.time()
        while self.requests and self.requests[0] < now - 1:
            self.requests.popleft()

        if len(self.requests) >= self.max_requests:
            sleep_time = 1 - (now - self.requests[0])
            if sleep_time > 0:
                log_debug(f"Ограничение частоты ИСУР: ожидание {sleep_time:.2f}с")
                time.sleep(sleep_time + 0.01)

        self.requests.append(time.time())

isur_rate_limiter = RateLimiter(max_requests_per_second=5)

def isur_request_with_limiter(method, url, **kwargs):
    """Выполняет запрос к ИСУР с контролем частоты."""
    isur_rate_limiter.wait_if_needed()
    return requests.request(method, url, **kwargs)

# ============================================================
# РАБОТА С API ИСУР
# ============================================================

def get_isur_token():
    auth_data = {"UserName": ISUR_LOGIN, "Password": ISUR_PASSWORD}
    response = isur_request_with_limiter("POST", ISUR_AUTH_URL, json=auth_data, verify=False)
    if response.status_code == 200:
        return response.text.strip('"')
    else:
        raise ISURAuthError(f"Ошибка авторизации: {response.status_code} - {response.text}")

def get_isur_works(token):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    response = isur_request_with_limiter("GET", ISUR_API_URL, headers=headers, verify=False)
    
    if response.status_code != 200:
        raise ISURAPIError(f"Ошибка получения работ: {response.status_code} - {response.text}")
    
    data = response.json()
    
    if isinstance(data, dict) and "Items" in data:
        return data["Items"]
    elif isinstance(data, list):
        return data
    else:
        raise ISURAPIError(f"Неожиданный формат ответа: {data}")

def close_isur_task(isur_id):
    """Закрывает задачу в ИСУР (минимальный рабочий объект)"""
    try:
        token = get_isur_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        payload = [{
            "Id": isur_id,
            "Status": "Completed",
            "FactualFinish": datetime.now().isoformat(),
            "AmountMeasurementUnit": "ManHour",
            "FactualAmountMeasurementUnit": "ManHour"
        }]
        
        response = isur_request_with_limiter("PUT", ISUR_API_URL, json=payload, headers=headers, verify=False)
        return response.status_code == 200
    except Exception as e:
        log_error(f"Ошибка закрытия в ИСУР: {e}")
        return False

def update_isur_task(isur_id, task_info):
    """Обновляет задачу в ИСУР."""
    try:
        token = get_isur_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Получаем текущую задачу из ИСУР
        response = isur_request_with_limiter("GET", f"{ISUR_API_URL}/{isur_id}", headers=headers, verify=False)
        if response.status_code != 200:
            return False
        
        task = response.json()
        
        # Обновляем поля
        task["Name"] = task_info.get("title", task.get("Name"))
        task["Start"] = task_info.get("start_date_plan", task.get("Start"))
        task["Finish"] = task_info.get("end_date_plan", task.get("Finish"))
        
        # Отправляем обновление
        response = isur_request_with_limiter("PUT", ISUR_API_URL, json=[task], headers=headers, verify=False)
        return response.status_code == 200
    except Exception as e:
        log_error(f"Ошибка обновления задачи в ИСУР: {e}")
        return False