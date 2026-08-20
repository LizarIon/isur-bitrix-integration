import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ISUR_LOGIN = "Admin"
ISUR_PASSWORD = ""
ISUR_AUTH_URL = "https://studldn7.api.isur.tech/api/Authorization"
ISUR_WORK_PARTICIPANTS_URL = "https://studldn7.api.isur.tech/api/WorkParticipants"

BITRIX_WEBHOOK = "https://b24-v9tnsq.bitrix24.ru/rest/1/uqmneqrcoil3a90d/"

WORK_ID = "4442ac83-566e-4cd6-98e2-85d1651f53c2"  # Тест1
BITRIX_TASK_ID = 1188

# 1. Получаем исполнителя из Битрикс24
resp = requests.get(f"{BITRIX_WEBHOOK}task.get", params={"id": BITRIX_TASK_ID})
task_data = resp.json().get("result", {}).get("DATA", {})
responsible_bitrix_id = task_data.get("RESPONSIBLE_ID")
print(f"RESPONSIBLE_ID в Битрикс: {responsible_bitrix_id}")

# 2. Получаем email исполнителя
resp = requests.get(f"{BITRIX_WEBHOOK}user.get", params={"id": responsible_bitrix_id})
user_data = resp.json().get("result", [])
if isinstance(user_data, list) and user_data:
    user_data = user_data[0]
user_email = user_data.get("EMAIL")
print(f"Email: {user_email}")

# 3. Получаем токен ИСУР
auth_data = {"UserName": ISUR_LOGIN, "Password": ISUR_PASSWORD}
resp = requests.post(ISUR_AUTH_URL, json=auth_data, verify=False)
token = resp.text.strip('"')
headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

# 4. Ищем сотрудника в ИСУР по email
resp = requests.get("https://studldn7.api.isur.tech/api/Employees", headers=headers, verify=False)
employees = resp.json().get("Items", [])
employee_id = None
for emp in employees:
    if emp.get("Email") == user_email:
        employee_id = emp.get("Id")
        break
print(f"ID сотрудника в ИСУР: {employee_id}")

if not employee_id:
    print("❌ Сотрудник не найден")
    exit()

# 5. Добавляем как участника работы
print("\n🔧 Добавляем участника...")
new_participant = {
    "ParticipationPercent": 100,
    "Employee_Id": employee_id,
    "Work_Id": WORK_ID
}
headers_post = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
resp = requests.post(ISUR_WORK_PARTICIPANTS_URL, json=[new_participant], headers=headers_post, verify=False)

print(f"Статус: {resp.status_code}")
if resp.status_code in [200, 201]:
    print("✅ Участник добавлен!")
else:
    print(f"❌ Ошибка: {resp.text}")