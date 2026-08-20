import requests
import time
from datetime import datetime
from src.config import (
    ISUR_LOGIN, ISUR_PASSWORD, ISUR_AUTH_URL,
    ISUR_API_URL, ISUR_WORK_PARTICIPANTS_URL
)
from src.logger import log_info, log_error, log_warning

# ============================================================
# РАБОТА С API ИСУР
# ============================================================

def get_isur_token():
    auth_data = {"UserName": ISUR_LOGIN, "Password": ISUR_PASSWORD}
    response = requests.post(ISUR_AUTH_URL, json=auth_data, verify=False)
    if response.status_code == 200:
        return response.text.strip('"')
    else:
        raise Exception(f"Ошибка авторизации: {response.status_code}")

def get_isur_works(token):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    response = requests.get(ISUR_API_URL, headers=headers, verify=False)
    
    if response.status_code != 200:
        raise Exception(f"Ошибка получения работ: {response.status_code}")
    
    data = response.json()
    
    if isinstance(data, dict) and "Items" in data:
        return data["Items"]
    elif isinstance(data, list):
        return data
    else:
        raise Exception(f"Неожиданный формат ответа: {data}")

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
        
        response = requests.put(ISUR_API_URL, json=payload, headers=headers, verify=False)
        return response.status_code == 200
    except Exception as e:
        log_error(f"Ошибка закрытия в ИСУР: {e}")
        return False