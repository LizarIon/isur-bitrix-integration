import os

# ============================================================
# 1. СОЗДАЁМ ПАПКИ
# ============================================================

folders = [
    "src",
    "src/clients",
    "src/sync",
    "src/utils",
    "logs"
]

for folder in folders:
    os.makedirs(folder, exist_ok=True)
    print(f"📁 Создана папка: {folder}")

# ============================================================
# 2. СОЗДАЁМ __init__.py
# ============================================================

init_files = [
    "src/__init__.py",
    "src/clients/__init__.py",
    "src/sync/__init__.py",
    "src/utils/__init__.py"
]

for init_file in init_files:
    with open(init_file, 'w', encoding='utf-8') as f:
        f.write("# Модуль для интеграции ИСУР-Проекты ↔ Битрикс24\n")
    print(f"📄 Создан файл: {init_file}")

# ============================================================
# 3. СОЗДАЁМ ПУСТЫЕ ЗАГОТОВКИ ДЛЯ ФАЙЛОВ
# ============================================================

files_to_create = [
    "src/config.py",
    "src/logger.py",
    "src/main.py",
    "src/clients/isur_client.py",
    "src/clients/bitrix_client.py",
    "src/sync/sync.py",
    "src/utils/file_utils.py"
]

for file_path in files_to_create:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("# TODO: добавить код\n")
    print(f"📄 Создан файл: {file_path}")

# ============================================================
# 4. СОЗДАЁМ .env.example
# ============================================================

env_example = """# === НАСТРОЙКИ ИСУР-Проекты ===
ISUR_LOGIN=Admin
ISUR_PASSWORD=
ISUR_AUTH_URL=
ISUR_API_URL=
ISUR_WORK_PARTICIPANTS_URL=
# === НАСТРОЙКИ БИТРИКС24 ===
BITRIX_WEBHOOK=
GROUP_ID=0
RESPONSIBLE_ID=1
"""

with open(".env.example", 'w', encoding='utf-8') as f:
    f.write(env_example)
print("📄 Создан файл: .env.example")

# ============================================================
# 5. КОПИРУЕМ СТАРЫЙ ФАЙЛ КАК БЭКАП
# ============================================================

try:
    with open("sync_new_portal.py", 'r', encoding='utf-8') as src:
        content = src.read()
    with open("sync_old_backup.py", 'w', encoding='utf-8') as dst:
        dst.write(content)
    print("📄 Создана резервная копия: sync_old_backup.py")
except FileNotFoundError:
    print("⚠️ Файл sync_new_portal.py не найден, пропускаем бэкап")

print("\n✅ Структура проекта создана!")
print("Теперь нужно заполнить файлы кодом.")