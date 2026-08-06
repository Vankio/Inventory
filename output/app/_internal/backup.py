import os
import shutil
import requests
import schedule
import time
from datetime import datetime

# --- Настройки ---
YANDEX_DISK_TOKEN = "y0__xC5nvajqveAAhjS0jcg57KDixNDzwiyBStmdoTyKufu3LHmy8W19w"  # Вставьте сюда ваш OAuth-токен
DB_FILE = "equipment.db"
BACKUP_DIR = "backups"
YANDEX_DISK_DIR = "app_backups"  # Папка на Яндекс.Диске для хранения бэкапов

def job():
    """Задача резервного копирования."""
    print(f"Запуск резервного копирования: {datetime.now()}")
    local_backup_path = create_backup()
    if local_backup_path:
        upload_to_yandex_disk(local_backup_path)

def create_backup():
    """Создает локальную копию базы данных."""
    if not os.path.exists(DB_FILE):
        print(f"Ошибка: Файл базы данных {DB_FILE} не найден.")
        return None

    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    backup_filename = f"backup.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    try:
        shutil.copy2(DB_FILE, backup_path)
        print(f"Резервная копия создана: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"Ошибка при создании локальной резервной копии: {e}")
        return None

def upload_to_yandex_disk(file_path):
    """Загружает файл на Яндекс.Диск."""
    if YANDEX_DISK_TOKEN == "ВАШ_ТОКЕН_СЮДА":
        print("Ошибка: Введите ваш OAuth-токен в переменную YANDEX_DISK_TOKEN.")
        return

    headers = {
        "Authorization": f"OAuth {YANDEX_DISK_TOKEN}"
    }

    # 1. Проверяем, существует ли папка на Диске, и создаем ее, если нет
    try:
        response = requests.put(f"https://cloud-api.yandex.net/v1/disk/resources?path={YANDEX_DISK_DIR}", headers=headers)
        if response.status_code != 201 and response.json().get("error") != "DiskPathPointsToExistentDirectoryError":
             print(f"Ошибка создания папки на Яндекс.Диске: {response.text}")
             return
    except Exception as e:
        print(f"Ошибка при создании папки на Яндекс.Диске: {e}")
        return

    # 2. Получаем URL для загрузки
    file_name = os.path.basename(file_path)
    try:
        upload_url_response = requests.get(
            f"https://cloud-api.yandex.net/v1/disk/resources/upload?path={YANDEX_DISK_DIR}/{file_name}&overwrite=true",
            headers=headers
        )
        upload_url_response.raise_for_status()
        upload_url = upload_url_response.json()["href"]
    except requests.exceptions.RequestException as e:
        print(f"Ошибка получения URL для загрузки: {e}")
        return

    # 3. Загружаем файл
    try:
        with open(file_path, 'rb') as f:
            upload_response = requests.put(upload_url, files={'file': f})
            upload_response.raise_for_status()
        print(f"Файл {file_name} успешно загружен на Яндекс.Диск.")
    except requests.exceptions.RequestException as e:
        print(f"Ошибка загрузки файла: {e}")

if __name__ == "__main__":
    print("Скрипт резервного копирования запущен.")
    schedule.every().day.at("02:00").do(job)
    
    # Для тестирования можно запустить каждые 5 минут:
    #schedule.every(5).seconds.do(job)

    while True:
        schedule.run_pending()
        time.sleep(60) # Проверка каждую минуту