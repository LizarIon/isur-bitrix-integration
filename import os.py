import os
import subprocess

print("=" * 60)
print("🔍 АНАЛИЗ ФАЙЛОВ В GIT")
print("=" * 60)

# Получаем список файлов, которые уже в Git
result = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
files_in_git = result.stdout.strip().split("\n")

print(f"\n📁 ВСЕГО ФАЙЛОВ В GIT: {len(files_in_git)}")
print("-" * 60)

# Категории для сортировки
keep = []
remove_from_git = []
maybe = []

for file in files_in_git:
    if not file:
        continue
    
    # Файлы, которые точно нужно оставить
    if file.startswith("src/") or file in [".gitignore", "README", "README.md", "requirements.txt", "requirements", "env.example"]:
        keep.append(file)
    # Файлы, которые точно нужно убрать из Git
    elif file.endswith(".db") or file.endswith(".json") or file in ["create_structure.py", "find_completed_tasks.py", "migrate_json_to_db.py", "sync_old_backup.py"]:
        remove_from_git.append(file)
    # Остальное (на всякий случай)
    else:
        maybe.append(file)

print("\n✅ НУЖНО ОСТАВИТЬ В GIT:")
for f in keep:
    print(f"   {f}")

print(f"\n   ИТОГО: {len(keep)} файлов")

print("\n🗑️ НУЖНО УБРАТЬ ИЗ GIT (но можно оставить локально):")
for f in remove_from_git:
    print(f"   {f}")

print(f"\n   ИТОГО: {len(remove_from_git)} файлов")

if maybe:
    print("\n⚠️ НЕОПРЕДЕЛЁННЫЕ (проверь вручную):")
    for f in maybe:
        print(f"   {f}")

print("\n" + "=" * 60)
print("💡 Чтобы убрать файлы из Git, выполни:")
print("   git rm --cached <имя_файла>")
print("   git commit -m 'Удалены временные файлы из Git'")
print("   git push")
print("=" * 60)