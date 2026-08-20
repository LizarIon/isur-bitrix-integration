import requests
import urllib3
import schedule
import time
import json
import os
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# НАСТРОЙКИ
# ============================================================

ISUR_LOGIN = "Admin"
ISUR_PASSWORD = ""
ISUR_AUTH_URL = "https://studldn7.api.isur.tech/api/Authorization"
ISUR_API_URL = "https://studldn7.api.isur.tech/api/Works"
ISUR_WORK_PARTICIPANTS_URL = "https://studldn7.api.isur.tech/api/WorkParticipants"

BITRIX_WEBHOOK = "https://b24-v9tnsq.bitrix24.ru/rest/1/uqmneqrcoil3a90d/"
GROUP_ID = 0
RESPONSIBLE_ID = 1

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LINKS_FILE = os.path.join(SCRIPT_DIR, "task_links.json")
DATA_FILE = os.path.join(SCRIPT_DIR, "task_data.json")
COMPLETED_FILE = os.path.join(SCRIPT_DIR, "completed_tasks.json")
CLOSED_FILE = os.path.join(SCRIPT_DIR, "closed_in_isur.json")

# ============================================================
# РАБОТА С ФАЙЛАМИ
# ============================================================

def init_files():
    if not os.path.exists(LINKS_FILE):
        with open(LINKS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2, ensure_ascii=False)
        print(f"📁 Создан файл связей: {LINKS_FILE}")
    
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2, ensure_ascii=False)
        print(f"📁 Создан файл данных: {DATA_FILE}")

def load_links():
    init_files()
    try:
        with open(LINKS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Если файл в старом формате (полный объект), конвертируем
            if data and isinstance(list(data.values())[0], dict):
                clean = {}
                for isur_id, value in data.items():
                    if isinstance(value, dict) and "task" in value and "id" in value["task"]:
                        clean[isur_id] = value["task"]["id"]
                    else:
                        clean[isur_id] = value
                return clean
            return data
    except:
        return {}

def save_links(links):
    init_files()
    with open(LINKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(links, f, indent=2, ensure_ascii=False)

def load_task_data():
    init_files()
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_task_data(task_data):
    init_files()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(task_data, f, indent=2, ensure_ascii=False)

def remove_link(isur_id, links):
    if str(isur_id) in links:
        del links[str(isur_id)]
        save_links(links)
        return True
    return False

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
        print(f"   ❌ Ошибка закрытия в ИСУР: {e}")
        return False

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
        response = requests.get(
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

# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ СИНХРОНИЗАЦИИ
# ============================================================

def sync_bidirectional():
    print(f"\n{'='*70}")
    print(f"🔄 СИНХРОНИЗАЦИЯ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    
    try:
        # Загружаем локальные связки
        links = load_links()
        print(f"📁 Загружено локальных связок: {len(links)}")
        
        # Получаем данные из ИСУР
        token = get_isur_token()
        works = get_isur_works(token)
        print(f"📡 Получено работ из ИСУР: {len(works)}")
        
        # Сохраняем полные данные (для информации)
        task_data = {}
        for work in works:
            work_id = work.get("Id") or work.get("id")
            if work_id:
                task_data[work_id] = work
        save_task_data(task_data)
        
        # ========== ПРОХОД 1: СОЗДАНИЕ НОВЫХ ЗАДАЧ ==========
        print(f"\n📤 ПРОХОД 1: Создание новых задач")
        print("-" * 50)
        
        created = 0
        
        for work in works:
            # Пропускаем некорректные элементы
            if not isinstance(work, dict):
                continue
            
            work_id = work.get("Id") or work.get("id")
            if not work_id:
                continue
            
            # Проверяем название (пропускаем задачи без названия)
            task_name = work.get("Name")
            if not task_name or task_name.strip() == "":
                print(f"   ⚠️ ПРОПУЩЕНА (нет названия): ID={work_id[:8]}...")
                continue
            
            bitrix_id = links.get(str(work_id))
            
            if not bitrix_id:
                try:
                    new_id = create_bitrix_task(work, links)
                    links[str(work_id)] = new_id
                    save_links(links)
                    print(f"   ✅ СОЗДАНА: {task_name[:40]} (ID: {new_id})")
                    created += 1
                except Exception as e:
                    print(f"   ❌ ОШИБКА: {task_name[:30]} - {e}")
            
            time.sleep(0.3)
        
        print(f"\n   📊 СОЗДАНО: {created}")
        
        # ========== ПРОХОД 2: ОБНОВЛЕНИЕ ДАННЫХ ==========
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
                        updated += 1
                        print(f"   🔄 ОБНОВЛЕНА: {task_name[:40]}")
                except Exception as e:
                    print(f"   ❌ ОШИБКА обновления: {task_name[:30]} - {e}")
            
            time.sleep(0.3)
        
        print(f"\n   📊 ОБНОВЛЕНО: {updated}")

                # ========== ДОБАВЛЕНО: Синхронизация участников (исполнителей) ==========
        print(f"\n👥 Синхронизация участников (исполнителей)")
        print("-" * 50)
        
        # Получаем свежие заголовки для ИСУР
        isur_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        
        # Получаем справочник сотрудников ИСУР по email
        emp_resp = requests.get("https://studldn7.api.isur.tech/api/Employees", headers=isur_headers, verify=False)
        employees = emp_resp.json().get("Items", [])
        email_to_isur_id = {emp.get("Email"): emp.get("Id") for emp in employees if emp.get("Email")}
        
        # Для каждой задачи
        for isur_id, bitrix_id in links.items():
            # Получаем задачу из Битрикс24
            b_resp = requests.get(f"{BITRIX_WEBHOOK}task.get", params={"id": bitrix_id}, timeout=10)
            if b_resp.status_code != 200:
                continue
            
            b_task = b_resp.json().get("result", {}).get("DATA", {})
            responsible_bitrix_id = b_task.get("RESPONSIBLE_ID")
            if not responsible_bitrix_id:
                continue
            
            # Получаем email из Битрикс24
            u_resp = requests.get(f"{BITRIX_WEBHOOK}user.get", params={"id": responsible_bitrix_id}, timeout=10)
            if u_resp.status_code != 200:
                continue
            
            user_data = u_resp.json().get("result", [])
            if isinstance(user_data, list) and user_data:
                user_data = user_data[0]
            user_email = user_data.get("EMAIL")
            if not user_email:
                continue
            
            # Ищем ID в ИСУР по email
            isur_emp_id = email_to_isur_id.get(user_email)
            if not isur_emp_id:
                print(f"   ⚠️ Сотрудник с email {user_email} не найден в ИСУР")
                continue
            
            # Проверяем, есть ли уже такой участник
            part_resp = requests.get(ISUR_WORK_PARTICIPANTS_URL, headers=isur_headers, verify=False)
            participants = part_resp.json().get("Items", [])
            already_exists = any(p.get("Work_Id") == isur_id and p.get("Employee_Id") == isur_emp_id for p in participants)
            
            if already_exists:
                print(f"   ⏭️ Участник уже добавлен для задачи {isur_id[:8]}...")
                continue
            
            # Добавляем участника
            new_participant = {
                "ParticipationPercent": 100,
                "Employee_Id": isur_emp_id,
                "Work_Id": isur_id
            }
            isur_post_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            part_post_resp = requests.post(ISUR_WORK_PARTICIPANTS_URL, json=[new_participant], headers=isur_post_headers, verify=False)
            if part_post_resp.status_code in [200, 201]:
                print(f"   ✅ Добавлен участник {user_email} для задачи {isur_id[:8]}...")
            else:
                print(f"   ❌ Ошибка: {part_post_resp.text[:100]}")
            
            time.sleep(0.2)
        
        # ========== ПРОХОД 3: УСТАНОВКА РОДИТЕЛЕЙ ==========
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
                
                update_data = {
                    "id": child_bitrix_id,
                    "data": {
                        "PARENT_ID": parent_bitrix_id
                    }
                }
                resp = requests.post(f"{BITRIX_WEBHOOK}task.update", json=update_data)
                if resp.status_code == 200:
                    task_name = work.get("Name") or "Без названия"
                    print(f"   ✅ {task_name[:40]} → родитель: {parent_bitrix_id}")
                    parents_set += 1
                else:
                    print(f"   ❌ Ошибка: {work.get('Name', '')[:30]}")
            else:
                print(f"   ⚠️ Родитель не найден: {parent_isur_id[:8]}...")
            
            time.sleep(0.3)
        
        print(f"\n   📊 РОДИТЕЛЕЙ УСТАНОВЛЕНО: {parents_set}")
        
        # ========== ПРОХОД 4: ПОИСК ЗАВЕРШЁННЫХ ЗАДАЧ ==========
        print(f"\n📥 ПРОХОД 4: Поиск завершённых задач в Битрикс24")
        print("-" * 50)
        
        completed_list = []
        
        for isur_id, bitrix_id in links.items():
            info = get_task_info(bitrix_id)
            if info and (info["status"] == "5" or info["closed_date"]):
                title = info["title"] if info["title"] else "Без названия"
                print(f"   ✅ ЗАВЕРШЕНА: {title[:45]}")
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
                print(f"   ❌ АКТИВНА: {title[:45]}")
        
        if completed_list:
            with open(COMPLETED_FILE, 'w', encoding='utf-8') as f:
                json.dump(completed_list, f, indent=2, ensure_ascii=False)
            print(f"\n   📊 НАЙДЕНО ЗАВЕРШЁННЫХ ЗАДАЧ: {len(completed_list)}")
            print(f"   📁 Результат сохранён в: {COMPLETED_FILE}")
        else:
            print("\n   📭 Завершённых задач не найдено")
        
        # ========== ПРОХОД 5: ЗАКРЫТИЕ ЗАВЕРШЁННЫХ ЗАДАЧ В ИСУР ==========
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
            
            info = get_task_info(bitrix_id)
            if not info:
                continue
            
            if info["status"] == "5" or info["closed_date"]:
                title = info["title"] if info["title"] else "Без названия"
                print(f"   📤 Закрываем: {title[:45]}")
                
                if close_isur_task(isur_id):
                    print(f"      ✅ ЗАКРЫТА В ИСУР")
                    closed_in_isur[isur_id] = {
                        "closed_at": datetime.now().isoformat(),
                        "title": title
                    }
                    closed_count += 1
                else:
                    print(f"      ❌ Ошибка закрытия")
            else:
                title = info["title"] if info["title"] else "Без названия"
                print(f"   ❌ АКТИВНА: {title[:45]}")
        
        if closed_count > 0:
            with open(CLOSED_FILE, 'w', encoding='utf-8') as f:
                json.dump(closed_in_isur, f, indent=2, ensure_ascii=False)
            print(f"\n   📊 ЗАКРЫТО В ИСУР: {closed_count}")
        else:
            print("\n   📭 Нет новых завершённых задач")
        
        print(f"\n{'='*70}")
        print("✅ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
        print(f"{'='*70}")
        
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    print("🚀 ПОЛНАЯ СИНХРОНИЗАЦИЯ ИСУР-Проекты ↔ Битрикс24")
    print("   📌 Создание, обновление, родители, поиск завершённых, закрытие в ИСУР")
    print(f"   📁 Файл связей: {LINKS_FILE}")
    print(f"   📁 Файл данных: {DATA_FILE}")
    print(f"   📁 Файл завершённых задач: {COMPLETED_FILE}")
    print(f"   📁 Файл закрытых в ИСУР: {CLOSED_FILE}\n")
    
    schedule.every(30).minutes.do(sync_bidirectional)
    
    sync_bidirectional()
    
    print("\n⏰ Планировщик запущен. Для остановки Ctrl+C\n")
    
    while True:
        schedule.run_pending()
        time.sleep(1)