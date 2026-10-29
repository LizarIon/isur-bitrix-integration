import requests
import time
import urllib3
import holidays
from collections import deque
from datetime import datetime, timedelta

from src.config import (
    ISUR_LOGIN, ISUR_PASSWORD, ISUR_AUTH_URL,
    ISUR_API_URL, ISUR_WORK_PARTICIPANTS_URL, ISUR_EMPLOYEES_URL
)
from src.logger import log_info, log_error, log_debug, log_warning
from src.exceptions import ISURAuthError, ISURAPIError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def count_working_days(start_date, finish_date):
    """Считает рабочие дни (пн-пт, без праздников РФ) между датами включительно."""
    if not start_date or not finish_date:
        return 0
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date.split("T")[0], "%Y-%m-%d").date()
        if isinstance(finish_date, str):
            finish_date = datetime.strptime(finish_date.split("T")[0], "%Y-%m-%d").date()
        
        years = list(range(start_date.year, finish_date.year + 1))
        ru_holidays = holidays.Russia(years=years)
        
        days = 0
        d = start_date
        while d <= finish_date:
            if d.weekday() < 5 and d not in ru_holidays:
                days += 1
            d += timedelta(days=1)
        return days
    except Exception as e:
        log_error(f"Ошибка count_working_days: {e}")
        return 0
    
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
# АВТОРИЗАЦИЯ
# ============================================================

def get_isur_token():
    auth_data = {"UserName": ISUR_LOGIN, "Password": ISUR_PASSWORD}
    response = isur_request_with_limiter("POST", ISUR_AUTH_URL, json=auth_data, verify=False)
    if response.status_code == 200:
        return response.text.strip('"')
    else:
        raise ISURAuthError(f"Ошибка авторизации: {response.status_code} - {response.text}")

# ============================================================
# ЧТЕНИЕ ДАННЫХ
# ============================================================

def get_isur_works(token):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    response = isur_request_with_limiter("GET", ISUR_API_URL, headers=headers, verify=False)

    if response.status_code != 200:
        raise ISURAPIError(f"Ошибка получения работ: {response.status_code} - {response.text}")

    data = response.json()

    if isinstance(data, dict) and "Items" in data:
        works = data["Items"]
    elif isinstance(data, list):
        works = data
    else:
        raise ISURAPIError(f"Неожиданный формат ответа: {data}")

    # ФИЛЬТР: оставляем только нормальные задачи, привязанные к проекту
    clean_works = []
    for w in works:
        if not w.get("Name") or not w.get("Project_Id"):
            continue
        clean_works.append(w)

    return clean_works

def get_isur_employees(token):
    """Получает список сотрудников из ИСУР."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    response = isur_request_with_limiter("GET", ISUR_EMPLOYEES_URL, headers=headers, verify=False)

    if response.status_code != 200:
        raise ISURAPIError(f"Ошибка получения сотрудников: {response.status_code} - {response.text[:200]}")

    data = response.json()

    if isinstance(data, dict) and "Items" in data:
        return data["Items"]
    elif isinstance(data, list):
        return data
    else:
        raise ISURAPIError(f"Неожиданный формат ответа сотрудников: {data}")

# ============================================================
# ЗАКРЫТИЕ ЗАДАЧИ
# ============================================================

def close_isur_task(isur_id):
    """Закрывает задачу в ИСУР (полным объектом, чтобы не затереть поля)."""
    try:
        token = get_isur_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Читаем задачу целиком
        resp_list = isur_request_with_limiter("GET", ISUR_API_URL, headers=headers, verify=False)
        if resp_list.status_code != 200:
            log_error(f"Не удалось прочитать задачу {isur_id} для закрытия")
            return False
        items = resp_list.json().get("Items", [])
        task = next((w for w in items if str(w.get("Id","")).lower() == str(isur_id).lower()), None)
        if not task:
            log_error(f"Задача {isur_id} не найдена для закрытия")
            return False

        payload = dict(task)
        payload.pop("Product_Id", None)
        payload["Status"] = "Completed"
        payload["FactualFinish"] = datetime.now().isoformat()
        payload["AmountMeasurementUnit"] = payload.get("AmountMeasurementUnit") or "ManHour"
        payload["FactualAmountMeasurementUnit"] = payload.get("FactualAmountMeasurementUnit") or "ManHour"

        resp = isur_request_with_limiter("PUT", ISUR_API_URL, json=[payload], headers=headers, verify=False)
        if resp.status_code == 200:
            log_info(f"Задача {isur_id[:8]}... закрыта в ИСУР")
            return True
        log_error(f"Ошибка закрытия {isur_id}: {resp.status_code} - {resp.text[:200]}")
        return False
    except Exception as e:
        log_error(f"Ошибка закрытия в ИСУР: {e}")
        return False
    
# ============================================================
# ЯДРО: ОБНОВЛЕНИЕ ДАТ (НЕ ТРОГАТЬ БЕЗ НЕОБХОДИМОСТИ)
# ============================================================

def update_isur_task(isur_id, task_info):
    """Обновляет задачу в ИСУР, сохраняя её связи (проект, родителя)."""
    try:
        token = get_isur_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # 1. Получаем текущую задачу из ИСУР (чтобы взять Project_Id и Parent_Id)
        response_list = isur_request_with_limiter("GET", ISUR_API_URL, headers=headers, verify=False)
        target_task_old = None
        if response_list.status_code == 200:
            works = response_list.json().get("Items", [])
            target_task_old = next((w for w in works if w.get("Id") == isur_id), None)

        if not target_task_old:
            log_error(f"Задача {isur_id} не найдена в ИСУР для обновления")
            return False

        # 2. Собираем новый объект (как в Swagger)
        old_plan = target_task_old.get("PlanAmount")
        old_factual = target_task_old.get("FactualAmount")
        old_unit = target_task_old.get("AmountMeasurementUnit")

        unit = old_unit if old_unit else "ManHour"

        # Расчёт трудоёмкости по новым датам (дни × 8)
        plan_amount = old_plan if old_plan is not None else 1.0
        start_s = task_info.get("start_date_plan")
        end_s = task_info.get("end_date_plan")
        if start_s and end_s:
            try:
                d1 = datetime.strptime(start_s[:10], "%d.%m.%Y")
                d2 = datetime.strptime(end_s[:10], "%d.%m.%Y")
                working_days = count_working_days(d1.date(), d2.date())
                if working_days > 0:
                    plan_amount = working_days * 8
            except Exception as e:
                log_error(f"Не удалось пересчитать трудоемкость: {e}")

        new_task = {
            "Id": isur_id,
            "Name": task_info.get("title", target_task_old.get("Name")),
            "AmountMeasurementUnit": unit,
            "FactualAmountMeasurementUnit": unit,
            "PlanAmount": plan_amount,
            "FactualAmount": old_factual if old_factual is not None else 0.0,
            "Status": target_task_old.get("Status") or "InProgress",
            "Project_Id": target_task_old.get("Project_Id"),
            "Parent_Id": target_task_old.get("Parent_Id"),
        }

        # Если родителя нет, удаляем ключ, чтобы не отправлять null
        if new_task["Parent_Id"] is None:
            del new_task["Parent_Id"]

        # НЕ передаем Product_Id (он ломает PUT)

        # 3. Формируем даты (ДД.ММ.ГГГГ -> ГГГГ-ММ-ДДT00:00:00.000Z)
        if task_info.get("start_date_plan"):
            date_str = task_info["start_date_plan"][:10].replace(".", "-")
            parts = date_str.split("-")
            if len(parts) == 3:
                new_task["Start"] = f"{parts[2]}-{parts[1]}-{parts[0]}T00:00:00.000Z"
        elif target_task_old.get("Start"):
            new_task["Start"] = target_task_old.get("Start")

        if task_info.get("end_date_plan"):
            date_str = task_info["end_date_plan"][:10].replace(".", "-")
            parts = date_str.split("-")
            if len(parts) == 3:
                new_task["Finish"] = f"{parts[2]}-{parts[1]}-{parts[0]}T00:00:00.000Z"
        elif target_task_old.get("Finish"):
            new_task["Finish"] = target_task_old.get("Finish")

        # 4. Отправляем
        response = isur_request_with_limiter("PUT", ISUR_API_URL, json=[new_task], headers=headers, verify=False)

        if response.status_code == 200:
            # Если изменились даты (start или finish), запускаем пересчет графика
            if task_info.get("start_date_plan") or task_info.get("end_date_plan"):
                project_id = target_task_old.get("Project_Id")
                if project_id:
                    trigger_isur_recalculation(project_id, isur_id, new_task.get("Start"), new_task.get("Finish"))
            return True
        else:
            log_error(f"Ошибка обновления в ИСУР: {response.status_code} - {response.text[:200]}")
            return False
    except Exception as e:
        log_error(f"Ошибка обновления задачи в ИСУР: {e}")
        return False

def set_isur_plan_amount_by_dates(isur_id, start_iso, finish_iso):
    """Считает трудоемкость по рабочим дням ИСУР (рабочие дни × 8) и пишет полным объектом."""
    try:
        if not start_iso or not finish_iso:
            return False
        d1 = datetime.strptime(start_iso.split("T")[0], "%Y-%m-%d")
        d2 = datetime.strptime(finish_iso.split("T")[0], "%Y-%m-%d")
        
        working_days = count_working_days(d1.date(), d2.date())
        if working_days <= 0:
            return False

        token = get_isur_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp_list = isur_request_with_limiter("GET", ISUR_API_URL, headers=headers, verify=False)
        if resp_list.status_code != 200:
            return False
        items = resp_list.json().get("Items", [])
        task = next((w for w in items if str(w.get("Id","")).lower() == str(isur_id).lower()), None)
        if not task:
            return False

        payload = dict(task)
        payload.pop("Product_Id", None)
        payload["PlanAmount"] = working_days * 8
        payload["AmountMeasurementUnit"] = "ManHour"
        payload["FactualAmountMeasurementUnit"] = "ManHour"

        resp = isur_request_with_limiter("PUT", ISUR_API_URL, json=[payload], headers=headers, verify=False)
        if resp.status_code == 200:
            log_info(f"Трудоемкость ИСУР {isur_id} по датам: {working_days} раб.дн. * 8 = {working_days*8}")
            return True
        log_error(f"Ошибка трудоемкости ИСУР {isur_id}: {resp.status_code} - {resp.text[:200]}")
        return False
    except Exception as e:
        log_error(f"Ошибка set_isur_plan_amount_by_dates: {e}")
        return False

# ============================================================
# КАСКАДНЫЙ ПЕРЕСЧЕТ ЗАВИСИМОСТЕЙ
# ============================================================

def trigger_isur_recalculation(project_id, changed_task_id, new_start, new_finish):
    """Локально пересчитывает зависимости и обновляет их в ИСУР."""
    from src.sync.sync import request_with_retry

    token = get_isur_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp_works = isur_request_with_limiter("GET", ISUR_API_URL, headers=headers, verify=False)
    works = resp_works.json().get("Items", [])

    links_url = ISUR_API_URL.replace('/Works', '/Links')
    resp_links = isur_request_with_limiter("GET", links_url, headers=headers, verify=False)
    links = resp_links.json().get("Items", [])

    tasks_map = {w["Id"]: w for w in works if w.get("Id")}

    tasks_map[changed_task_id]["Start"] = new_start
    tasks_map[changed_task_id]["Finish"] = new_finish

    updated_tasks = {changed_task_id}
    tasks_to_process = [changed_task_id]

    while tasks_to_process:
        current_id = tasks_to_process.pop(0)
        current_task = tasks_map[current_id]

        for link in links:
            from_id = link.get("From_Id")
            to_id = link.get("To_Id")

            if from_id == current_id and to_id in tasks_map:
                if to_id not in updated_tasks:
                    updated_tasks.add(to_id) 
                    pred_finish_str = current_task.get("Finish")
                    if not pred_finish_str:
                        continue

                    pred_finish = datetime.strptime(pred_finish_str.split("T")[0], "%Y-%m-%d")
                    succ_start = pred_finish + timedelta(days=1)

                    succ_task = tasks_map[to_id]
                    if succ_task.get("Start") and succ_task.get("Finish"):
                        succ_start_old = datetime.strptime(succ_task["Start"].split("T")[0], "%Y-%m-%d")
                        succ_finish_old = datetime.strptime(succ_task["Finish"].split("T")[0], "%Y-%m-%d")
                        duration = (succ_finish_old - succ_start_old).days

                        succ_task["Start"] = succ_start.strftime("%Y-%m-%dT00:00:00")
                        succ_task["Finish"] = (succ_start + timedelta(days=duration)).strftime("%Y-%m-%dT00:00:00")

                        payload = [{
                            "Id": to_id,
                            "Name": succ_task["Name"],
                            "Start": succ_task["Start"],
                            "Finish": succ_task["Finish"],
                            "AmountMeasurementUnit": "ManHour",
                            "FactualAmountMeasurementUnit": "ManHour",
                            "PlanAmount": succ_task.get("PlanAmount") or 1.0,
                            "FactualAmount": 0.0,
                            "Status": succ_task.get("Status") or "InProgress",
                            "Project_Id": succ_task.get("Project_Id"),
                            "Parent_Id": succ_task.get("Parent_Id")
                        }]
                        isur_request_with_limiter("PUT", ISUR_API_URL, json=payload, headers=headers, verify=False)
                        log_info(f"   ✅ Сдвинута задача {succ_task['Name']} (из-за {current_task['Name']})")

                        updated_tasks.add(to_id)
                        tasks_to_process.append(to_id)

                        # Пересчитываем трудоемкость сдвинутой задачи
                        try:
                            set_isur_plan_amount_by_dates(to_id, succ_task["Start"], succ_task["Finish"])
                        except Exception as e:
                            log_error(f"Ошибка пересчета трудоемкости {to_id}: {e}")

    return True


def sync_task_participants(isur_id, bitrix_id):
    """Синхронизирует участников задачи ИСУР с ответственным из Битрикса.
    Удаляет всех лишних, добавляет нужного (по email).
    """
    from src.config import BITRIX_WEBHOOK
    from src.clients.bitrix_client import bitrix_request_with_limiter

    try:
        token = get_isur_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}

        # 1. Ответственный из Битрикса
        b_resp = bitrix_request_with_limiter("GET", f"{BITRIX_WEBHOOK}task.get", params={"id": bitrix_id}, timeout=10)
        b_task = b_resp.json().get("result", {}).get("DATA", {})
        resp_id = b_task.get("RESPONSIBLE_ID")
        if not resp_id:
            return False

        u_resp = bitrix_request_with_limiter("GET", f"{BITRIX_WEBHOOK}user.get", params={"id": resp_id}, timeout=10)
        user_data = u_resp.json().get("result", [])
        if isinstance(user_data, list) and user_data:
            user_data = user_data[0]
        email = user_data.get("EMAIL")
        if not email:
            return False

        # 2. Email -> Employee_Id в ИСУР
        emp_resp = isur_request_with_limiter("GET", ISUR_EMPLOYEES_URL, headers=headers, verify=False)
        employees = emp_resp.json().get("Items", [])
        isur_emp_id = next((e["Id"] for e in employees if e.get("Email") == email), None)
        if not isur_emp_id:
            log_warning(f"Сотрудник {email} не найден в ИСУР, участников не трогаем")
            return False

        # 3. Текущие участники задачи
        part_resp = isur_request_with_limiter("GET", ISUR_WORK_PARTICIPANTS_URL, headers=headers, verify=False)
        parts = part_resp.json().get("Items", [])
        task_parts = [p for p in parts if p.get("Work_Id") == isur_id]

        # 4. Удаляем всех, кроме нужного
        for p in task_parts:
            if p.get("Employee_Id") != isur_emp_id:
                isur_request_with_limiter("DELETE", f"{ISUR_WORK_PARTICIPANTS_URL}/{p['Id']}", headers=headers, verify=False)
                log_info(f"Удалён участник {p['Employee_Id']} из задачи {isur_id[:8]}...")

        # 5. Добавляем нужного, если его нет
        if not any(p.get("Employee_Id") == isur_emp_id for p in task_parts):
            payload = [{"ParticipationPercent": 100, "Employee_Id": isur_emp_id, "Work_Id": isur_id}]
            resp = isur_request_with_limiter("POST", ISUR_WORK_PARTICIPANTS_URL, json=payload, headers=headers, verify=False)
            if resp.status_code in (200, 201):
                log_info(f"Добавлен участник {email} в задачу {isur_id[:8]}...")
                return True
            log_error(f"Ошибка добавления участника: {resp.status_code} - {resp.text[:200]}")
            return False
        else:
            log_info(f"Участник {email} уже есть в задаче {isur_id[:8]}...")
            return True
    except Exception as e:
        log_error(f"Ошибка sync_task_participants: {e}")
        return False
def get_isur_task(isur_id):
    """Возвращает задачу ИСУР по ID (или None)."""
    try:
        token = get_isur_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        resp = isur_request_with_limiter("GET", ISUR_API_URL, headers=headers, verify=False)
        if resp.status_code != 200:
            return None
        items = resp.json().get("Items", [])
        return next((w for w in items if str(w.get("Id","")).lower() == str(isur_id).lower()), None)
    except Exception as e:
        log_error(f"Ошибка get_isur_task: {e}")
        return None
    
def reopen_isur_task(isur_id):
    """Возвращает задачу в работу в ИСУР (сбрасывает FactualFinish)."""
    try:
        token = get_isur_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp_list = isur_request_with_limiter("GET", ISUR_API_URL, headers=headers, verify=False)
        if resp_list.status_code != 200:
            return False

        items = resp_list.json().get("Items", [])
        task = next((w for w in items if str(w.get("Id","")).lower() == str(isur_id).lower()), None)
        if not task:
            return False

        payload = dict(task)
        payload.pop("Product_Id", None)
        payload["FactualStart"] = None
        payload["FactualFinish"] = None
        payload["AmountMeasurementUnit"] = payload.get("AmountMeasurementUnit") or "ManHour"
        payload["FactualAmountMeasurementUnit"] = payload.get("FactualAmountMeasurementUnit") or "ManHour"

        resp = isur_request_with_limiter("PUT", ISUR_API_URL, json=[payload], headers=headers, verify=False)
        if resp.status_code == 200:
            log_info(f"Задача {isur_id[:8]}... возвращена в работу (FactualFinish = null)")
            return True
        log_error(f"Ошибка возврата в работу {isur_id}: {resp.status_code} - {resp.text[:200]}")
        return False
    except Exception as e:
        log_error(f"Ошибка reopen_isur_task: {e}")
        return False

def set_isur_factual_start(isur_id):
    """Ставит FactualStart и FactualAmount, если задача ещё не начата."""
    try:
        token = get_isur_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp_list = isur_request_with_limiter("GET", ISUR_API_URL, headers=headers, verify=False)
        if resp_list.status_code != 200:
            return False
        items = resp_list.json().get("Items", [])
        task = next((w for w in items if str(w.get("Id","")).lower() == str(isur_id).lower()), None)
        if not task:
            return False

        if task.get("FactualStart"):
            return True

        payload = dict(task)
        payload.pop("Product_Id", None)
        payload["FactualStart"] = datetime.now().isoformat()
        payload["FactualAmount"] = 1.0
        payload["AmountMeasurementUnit"] = payload.get("AmountMeasurementUnit") or "ManHour"
        payload["FactualAmountMeasurementUnit"] = payload.get("FactualAmountMeasurementUnit") or "ManHour"

        resp = isur_request_with_limiter("PUT", ISUR_API_URL, json=[payload], headers=headers, verify=False)
        if resp.status_code == 200:
            log_info(f"Задача {isur_id[:8]}... взята в работу (FactualStart)")
            return True
        log_error(f"Ошибка FactualStart {isur_id}: {resp.status_code} - {resp.text[:200]}")
        return False
    except Exception as e:
        log_error(f"Ошибка set_isur_factual_start: {e}")
        return False