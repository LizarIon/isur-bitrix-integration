import os
import time
from datetime import datetime

from src.config import BITRIX_WEBHOOK, GROUP_ID, COMPLETED_FILE, CLOSED_FILE
from src.logger import log_info, log_warning, log_error
from src.utils.file_utils import (
    load_links, save_links, load_task_data, save_task_data, remove_link
)
from src.clients.isur_client import get_isur_token, get_isur_works, close_isur_task
from src.clients.bitrix_client import (
    check_bitrix_task_exists, create_bitrix_task, update_bitrix_task, get_task_info,
    bitrix_request_with_limiter
)

# ============================================================
# КАСТОМНЫЕ ИСКЛЮЧЕНИЯ
# ============================================================

class ISURAuthError(Exception):
    """Ошибка авторизации в ИСУР."""
    pass

class ISURAPIError(Exception):
    """Ошибка при запросе к ИСУР."""
    pass

class BitrixAPIError(Exception):
    """Ошибка при запросе к Битрикс24."""
    pass

class TaskCreationError(Exception):
    """Ошибка создания задачи."""
    pass

# ============================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ПОВТОРНЫХ ПОПЫТОК
# ============================================================

def request_with_retry(url, method="get", json_data=None, params=None, retries=3, delay=2):
    """Выполняет запрос с повторными попытками при ошибках сети или 500."""
    for attempt in range(retries):
        try:
            if method == "get":
                response = requests.get(url, params=params, timeout=30)
            elif method == "post":
                response = requests.post(url, json=json_data, timeout=30)
            else:
                raise ValueError(f"Неподдерживаемый метод: {method}")

            if response.status_code == 500:
                log_warning(f"Ошибка 500, попытка {attempt+1} из {retries} для {url}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    continue
                else:
                    raise BitrixAPIError(f"Ошибка 500 при запросе к {url}: {response.text}")
            return response
        except requests.exceptions.Timeout:
            log_warning(f"Таймаут, попытка {attempt+1} из {retries} для {url}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise BitrixAPIError(f"Таймаут при запросе к {url}")
        except requests.exceptions.ConnectionError as e:
            log_warning(f"Ошибка соединения, попытка {attempt+1} из {retries} для {url}")
            if attempt < retries - 1:
                time.sleep(delay)
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
    except Exception as e:
        log_error(f"Ошибка авторизации в ИСУР: {e}")
        return None, None

    try:
        works = get_isur_works(token)
        log_info(f"Получено работ из ИСУР: {len(works)}")
    except Exception as e:
        log_error(f"Ошибка получения задач из ИСУР: {e}")
        return None, None

    # Сохраняем полные данные (для информации)
    task_data = {}
    for work in works:
        work_id = work.get("Id") or work.get("id")
        if work_id:
            task_data[work_id] = work
    save_task_data(task_data)

    return links, works, token

# ============================================================
# ПРОХОД 1: СОЗДАНИЕ НОВЫХ ЗАДАЧ
# ============================================================

def run_pass1_creation(links, works):
    """Создаёт новые задачи в Битрикс24."""
    print(f"\n📤 ПРОХОД 1: Создание новых задач")
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
                links[str(work_id)] = new_id
                save_links(links)
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
    print(f"\n🔄 ПРОХОД 2: Обновление данных")
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
                    log_info(f"ОБНОВЛЕНА: {task_name[:40]}")
                    updated += 1
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
    print(f"\n👥 Синхронизация участников (исполнителей)")
    print("-" * 50)

    isur_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    try:
        emp_resp = request_with_retry(
            "https://studldn7.api.isur.tech/api/Employees",
            method="get",
            retries=2
        )
        employees = emp_resp.json().get("Items", [])
        email_to_isur_id = {emp.get("Email"): emp.get("Id") for emp in employees if emp.get("Email")}
    except Exception as e:
        log_error(f"Ошибка получения сотрудников ИСУР: {e}")
        return

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

            part_resp = request_with_retry(
                ISUR_WORK_PARTICIPANTS_URL,
                method="get",
                retries=2
            )
            participants = part_resp.json().get("Items", [])
            already_exists = any(p.get("Work_Id") == isur_id and p.get("Employee_Id") == isur_emp_id for p in participants)

            if already_exists:
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
                    retries=2
                )
                if part_post_resp.status_code in [200, 201]:
                    log_info(f"Добавлен участник {user_email} для задачи {isur_id[:8]}...")
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
    print(f"\n👪 ПРОХОД 3: Установка родительских связей")
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
                    json_data={
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
# ПРОХОД 4: ПОИСК ЗАВЕРШЁННЫХ
# ============================================================

def run_pass4_completed(links):
    """Находит завершённые задачи в Битрикс24."""
    print(f"\n📥 ПРОХОД 4: Поиск завершённых задач в Битрикс24")
    print("-" * 50)

    completed_list = []

    for isur_id, bitrix_id in links.items():
        try:
            info = get_task_info(bitrix_id)
            if info and (info["status"] == "5" or info["closed_date"]):
                title = info["title"] if info["title"] else "Без названия"
                log_info(f"ЗАВЕРШЕНА: {title[:45]}")
                completed_list.append({
                    "isur_id": isur_id,
                    "bitrix_id": bitrix_id,
                    "title": title,
                    "status": info["status"],
                    "closed_date": info["closed_date"],
                    "detected_at": datetime.now().isoformat()
                })
            else:
                title = info["title"] if info and info["title"] else "Без названия"
                log_info(f"АКТИВНА: {title[:45]}")
        except Exception as e:
            log_error(f"Ошибка проверки задачи {isur_id[:8]}...: {e}")
            continue

    if completed_list:
        with open(COMPLETED_FILE, 'w', encoding='utf-8') as f:
            json.dump(completed_list, f, indent=2, ensure_ascii=False)
        log_info(f"НАЙДЕНО ЗАВЕРШЁННЫХ ЗАДАЧ: {len(completed_list)}")
        log_info(f"Результат сохранён в: {COMPLETED_FILE}")
    else:
        log_info("Завершённых задач не найдено")

# ============================================================
# ПРОХОД 5: ЗАКРЫТИЕ В ИСУР
# ============================================================

def run_pass5_close(links):
    """Закрывает завершённые задачи в ИСУР."""
    print(f"\n📥 ПРОХОД 5: Закрытие завершённых задач в ИСУР")
    print("-" * 50)

    if os.path.exists(CLOSED_FILE):
        with open(CLOSED_FILE, 'r', encoding='utf-8') as f:
            closed_in_isur = json.load(f)
    else:
        closed_in_isur = {}

    closed_count = 0

    for isur_id, bitrix_id in links.items():
        if closed_in_isur.get(isur_id):
            continue

        try:
            info = get_task_info(bitrix_id)
            if not info:
                continue

            if info["status"] == "5" or info["closed_date"]:
                title = info["title"] if info["title"] else "Без названия"
                log_info(f"Закрываем: {title[:45]}")

                if close_isur_task(isur_id):
                    log_info(f"ЗАКРЫТА В ИСУР")
                    closed_in_isur[isur_id] = {
                        "closed_at": datetime.now().isoformat(),
                        "title": title
                    }
                    closed_count += 1
                else:
                    log_error("Ошибка закрытия задачи в ИСУР")
            else:
                title = info["title"] if info["title"] else "Без названия"
                log_info(f"АКТИВНА: {title[:45]}")
        except Exception as e:
            log_error(f"Ошибка обработки задачи {isur_id[:8]}...: {e}")
            continue

    if closed_count > 0:
        with open(CLOSED_FILE, 'w', encoding='utf-8') as f:
            json.dump(closed_in_isur, f, indent=2, ensure_ascii=False)
        log_info(f"ЗАКРЫТО В ИСУР: {closed_count}")
    else:
        log_info("Нет новых завершённых задач")

# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ СИНХРОНИЗАЦИИ
# ============================================================

def sync_bidirectional():
    """Запускает все проходы синхронизации в правильном порядке."""
    print(f"\n{'='*70}")
    log_info(f"🔄 СИНХРОНИЗАЦИЯ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    # 1. Подготовка данных
    result = prepare_data()
    if result[0] is None:
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

    # 6. Проход 4: поиск завершённых
    run_pass4_completed(links)

    # 7. Проход 5: закрытие в ИСУР
    run_pass5_close(links)

    print(f"\n{'='*70}")
    log_info("✅ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
    print(f"{'='*70}")