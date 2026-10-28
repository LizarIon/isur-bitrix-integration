import os
import time
import requests
from datetime import datetime

from src.config import BITRIX_WEBHOOK, GROUP_ID, ISUR_WORK_PARTICIPANTS_URL, ISUR_API_URL
from src.state import set_last_sync
from src.logger import log_info, log_warning, log_error
from src.utils.db_utils import (
    load_links, save_link, load_task_data, save_task_data,
    load_closed_tasks, save_closed_task, remove_link, init_db,
    save_completed_list, load_project_links, save_project_link
)
from src.clients.isur_client import get_isur_token, get_isur_works, close_isur_task, get_isur_employees, isur_request_with_limiter
from src.clients.bitrix_client import (
    check_bitrix_task_exists, create_bitrix_task, update_bitrix_task, get_task_info,
    bitrix_request_with_limiter, create_bitrix_group
)
from src.exceptions import (
    ISURAuthError, ISURAPIError, BitrixAPIError, TaskCreationError
)

# ============================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ПОВТОРНЫХ ПОПЫТОК
# ============================================================

def request_with_retry(url, method="get", json_data=None, params=None, headers=None, retries=3, delay=2):
    """Выполняет запрос с повторными попытками при ошибках сети или 500.
    
    Использует exponential backoff: задержка между попытками растёт (delay * 2^attempt).
    """
    for attempt in range(retries):
        try:
            if method == "get":
                response = requests.get(url, params=params, headers=headers, timeout=30, verify=False)
            elif method == "post":
                response = requests.post(url, json=json_data, headers=headers, timeout=30, verify=False)
            elif method == "put":
                response = requests.put(url, json=json_data, headers=headers, timeout=30, verify=False)
            else:
                raise ValueError(f"Неподдерживаемый метод: {method}")

            if response.status_code == 500:
                log_warning(f"Ошибка 500, попытка {attempt+1} из {retries} для {url}")
                if attempt < retries - 1:
                    wait = delay * (2 ** attempt)
                    log_warning(f"Ожидание {wait}с перед следующей попыткой")
                    time.sleep(wait)
                    continue
                else:
                    raise BitrixAPIError(f"Ошибка 500 при запросе к {url}: {response.text}")
            return response

        except requests.exceptions.Timeout:
            log_warning(f"Таймаут, попытка {attempt+1} из {retries} для {url}")
            if attempt < retries - 1:
                wait = delay * (2 ** attempt)
                log_warning(f"Ожидание {wait}с перед следующей попыткой")
                time.sleep(wait)
            else:
                raise BitrixAPIError(f"Таймаут при запросе к {url}")

        except requests.exceptions.ConnectionError as e:
            log_warning(f"Ошибка соединения, попытка {attempt+1} из {retries} для {url}")
            if attempt < retries - 1:
                wait = delay * (2 ** attempt)
                log_warning(f"Ожидание {wait}с перед следующей попыткой")
                time.sleep(wait)
            else:
                raise BitrixAPIError(f"Ошибка соединения: {e}")
# ============================================================
# ПОДГОТОВКА ДАННЫХ
# ============================================================

def prepare_data():
    """Загружает связи, получает токен и задачи из ИСУР."""
    links = load_links()
    log_info(f"Загружено локальных связок: {len(links)}")

    try:
        token = get_isur_token()
    except ISURAuthError as e:
        log_error(f"Ошибка авторизации в ИСУР: {e}")
        return None, None, None
    except Exception as e:
        log_error(f"Неожиданная ошибка при получении токена ИСУР: {e}")
        return None, None, None

    try:
        works = get_isur_works(token)
        log_info(f"Получено работ из ИСУР: {len(works)}")
    except ISURAPIError as e:
        log_error(f"Ошибка получения задач из ИСУР: {e}")
        return None, None, None
    except Exception as e:
        log_error(f"Неожиданная ошибка при получении задач ИСУР: {e}")
        return None, None, None

    # Сохраняем полные данные (для информации)
    for work in works:
        work_id = work.get("Id") or work.get("id")
        # Пропускаем теневые задачи (без названия)
        if work_id and work.get("Name"):
            save_task_data(work_id, work)

    return links, works, token

# ============================================================
# ПРОХОД 1: СОЗДАНИЕ НОВЫХ ЗАДАЧ
# ============================================================

def run_pass1_creation(links, works):
    """Создаёт новые задачи в Битрикс24."""
    log_info("📤 ПРОХОД 1: Создание новых задач")
    print("-" * 50)

    created = 0

    for work in works:
        if not isinstance(work, dict):
            continue

        work_id = work.get("Id") or work.get("id")
        if not work_id:
            continue

        task_name = work.get("Name")
        if not task_name or task_name.strip() == "":
            log_warning(f"ПРОПУЩЕНА (нет названия): ID={work_id[:8]}...")
            continue

        bitrix_id = links.get(str(work_id))

        if not bitrix_id:
            try:
                new_id = create_bitrix_task(work, links)
                save_link(work_id, new_id)
                log_info(f"СОЗДАНА: {task_name[:40]} (ID: {new_id})")
                created += 1
            except Exception as e:
                log_error(f"Ошибка создания: {task_name[:30]} - {e}")
                continue

        time.sleep(0.3)

    log_info(f"СОЗДАНО: {created}")

# ============================================================
# ПРОХОД 2: ОБНОВЛЕНИЕ ДАННЫХ
# ============================================================

def run_pass2_update(links, works):
    """Обновляет данные существующих задач."""
    log_info("🔄 ПРОХОД 2: Обновление данных")
    print("-" * 50)

    updated = 0

    for work in works:
        if not isinstance(work, dict):
            continue

        work_id = work.get("Id") or work.get("id")
        if not work_id:
            continue

        task_name = work.get("Name")
        if not task_name or task_name.strip() == "":
            continue

        bitrix_id = links.get(str(work_id))

        if bitrix_id:
            try:
                if update_bitrix_task(bitrix_id, work, links):
                    updated += 1
                    try:
                        from src.clients.isur_client import set_isur_plan_amount_by_dates
                        set_isur_plan_amount_by_dates(work_id, work.get("Start"), work.get("Finish"))
                    except Exception as e:
                        log_error(f"Ошибка пересчета трудоемкости {work_id}: {e}")
            except Exception as e:
                log_error(f"Ошибка обновления: {task_name[:30]} - {e}")
                continue

        time.sleep(0.3)

    log_info(f"ОБНОВЛЕНО: {updated}")

# ============================================================
# СИНХРОНИЗАЦИЯ УЧАСТНИКОВ
# ============================================================

def sync_participants(links, token):
    """Добавляет исполнителей (участников) в задачи ИСУР."""
    log_info("👥 Синхронизация участников (исполнителей)")
    print("-" * 50)

    try:
        employees = get_isur_employees(token)
        email_to_isur_id = {emp.get("Email"): emp.get("Id") for emp in employees if emp.get("Email")}
    except ISURAPIError as e:
        log_error(f"Ошибка получения сотрудников ИСУР: {e}")
        return
    except Exception as e:
        log_error(f"Неожиданная ошибка при получении сотрудников ИСУР: {e}")
        return

    # Получаем ВСЕХ участников ОДИН РАЗ до цикла
    try:
        part_resp = request_with_retry(
            ISUR_WORK_PARTICIPANTS_URL,
            method="get",
            retries=2
        )
        all_participants = part_resp.json().get("Items", [])
    except Exception as e:
        log_error(f"Ошибка получения участников ИСУР: {e}")
        all_participants = []

    # Индекс: (work_id, employee_id) → exists
    existing_participants = {
        (p.get("Work_Id"), p.get("Employee_Id"))
        for p in all_participants
    }

    for isur_id, bitrix_id in links.items():
        try:
            b_resp = bitrix_request_with_limiter(
                "GET",
                f"{BITRIX_WEBHOOK}task.get",
                params={"id": bitrix_id},
                timeout=10
            )
            b_task = b_resp.json().get("result", {}).get("DATA", {})
            responsible_bitrix_id = b_task.get("RESPONSIBLE_ID")
            if not responsible_bitrix_id:
                continue

            u_resp = bitrix_request_with_limiter(
                "GET",
                f"{BITRIX_WEBHOOK}user.get",
                params={"id": responsible_bitrix_id},
                timeout=10
            )
            user_data = u_resp.json().get("result", [])
            if isinstance(user_data, list) and user_data:
                user_data = user_data[0]
            user_email = user_data.get("EMAIL")
            if not user_email:
                continue

            isur_emp_id = email_to_isur_id.get(user_email)
            if not isur_emp_id:
                log_warning(f"Сотрудник с email {user_email} не найден в ИСУР")
                continue

            # Проверяем по локальному индексу — БЕЗ запроса к API
            if (isur_id, isur_emp_id) in existing_participants:
                log_info(f"Участник уже добавлен для задачи {isur_id[:8]}...")
                continue

            new_participant = {
                "ParticipationPercent": 100,
                "Employee_Id": isur_emp_id,
                "Work_Id": isur_id
            }
            try:
                part_post_resp = request_with_retry(
                    ISUR_WORK_PARTICIPANTS_URL,
                    method="post",
                    json_data=[new_participant],
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    retries=2
                )
                if part_post_resp.status_code in [200, 201]:
                    log_info(f"Добавлен участник {user_email} для задачи {isur_id[:8]}...")
                    existing_participants.add((isur_id, isur_emp_id))
            except Exception as e:
                log_error(f"Ошибка добавления участника: {e}")
                continue

        except Exception as e:
            log_error(f"Ошибка синхронизации участников для задачи {isur_id[:8]}...: {e}")
            continue

        time.sleep(0.2)

# ============================================================
# ПРОХОД 3: УСТАНОВКА РОДИТЕЛЕЙ
# ============================================================

def run_pass3_parents(links, works):
    """Устанавливает родительские связи."""
    log_info("👪 ПРОХОД 3: Установка родительских связей")
    print("-" * 50)

    parents_set = 0

    for work in works:
        if not isinstance(work, dict):
            continue

        work_id = work.get("Id") or work.get("id")
        if not work_id:
            continue

        if work_id not in links:
            continue

        parent_isur_id = work.get("Parent_Id")
        if not parent_isur_id:
            continue

        if parent_isur_id in links:
            child_bitrix_id = links[work_id]
            parent_bitrix_id = links[parent_isur_id]

            try:
                resp = bitrix_request_with_limiter(
                    "POST",
                    f"{BITRIX_WEBHOOK}task.update",
                    json={
                        "id": child_bitrix_id,
                        "data": {"PARENT_ID": parent_bitrix_id}
                    },
                    timeout=30
                )
                if resp.status_code == 200:
                    task_name = work.get("Name") or "Без названия"
                    log_info(f"{task_name[:40]} → родитель: {parent_bitrix_id}")
                    parents_set += 1
                else:
                    log_error(f"Ошибка установки родителя: {work.get('Name', '')[:30]}")
            except Exception as e:
                log_error(f"Ошибка установки родителя: {e}")
        else:
            log_warning(f"Родитель не найден: {parent_isur_id[:8]}...")

        time.sleep(0.3)

    log_info(f"РОДИТЕЛЕЙ УСТАНОВЛЕНО: {parents_set}")

# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ СИНХРОНИЗАЦИИ
# ============================================================

def sync_projects():
    """Проверяет проекты в ИСУР и создает для них группы в Битриксе, если их нет."""
    log_info("📁 Проверка проектов ИСУР...")
    
    try:
        token = get_isur_token()
        projects_url = ISUR_API_URL.replace('/Works', '/Projects')
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        
        resp = isur_request_with_limiter("GET", projects_url, headers=headers, verify=False)
        if resp.status_code != 200:
            log_error("Не удалось получить список проектов ИСУР")
            return
            
        projects = resp.json().get("Items", [])
        project_links = load_project_links()
        
        for p in projects:
            p_id = p.get("Id")
            p_name = p.get("Name")
            
            if not p_id or not p_name:
                continue
                
            # Если для этого проекта еще нет группы в Битриксе
            if p_id not in project_links:
                log_info(f"Новый проект ИСУР: '{p_name}'. Создаем группу...")
                group_id = create_bitrix_group(p_name)
                if group_id:
                    save_project_link(p_id, group_id)
            else:
                log_info(f"Проект '{p_name}' уже привязан к группе {project_links[p_id]}")
                
    except Exception as e:
        log_error(f"Ошибка синхронизации проектов: {e}")

def sync_bidirectional():
    """Запускает все проходы синхронизации в правильном порядке."""
    print(f"\n{'='*70}")
    log_info(f"🔄 СИНХРОНИЗАЦИЯ (ИСУР → Битрикс): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    # 0. Проверяем и создаем проекты
    sync_projects()

    # 1. Подготовка данных
    result = prepare_data()
    if result[0] is None:
        log_error("Ошибка подготовки данных, синхронизация прервана")
        set_last_sync("error", "Ошибка подготовки данных")
        return
    links, works, token = result

    # 2. Проход 1: создание задач
    run_pass1_creation(links, works)

    # 3. Проход 2: обновление данных
    run_pass2_update(links, works)

    # 4. Синхронизация участников
    sync_participants(links, token)

    # 5. Проход 3: родители
    run_pass3_parents(links, works)

    print(f"\n{'='*70}")
    log_info("✅ ПРЯМАЯ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
    set_last_sync("success", "Прямая синхронизация завершена")
    print(f"{'='*70}")