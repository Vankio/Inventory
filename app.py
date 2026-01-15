from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, g, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_wtf.csrf import CSRFProtect
import sqlite3
import os
import json
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader
from config import SECRET_KEY


app = Flask(__name__)
app.secret_key = SECRET_KEY
csrf = CSRFProtect(app)

# Пользователи
USERS = {
    "admin": {"password": 'scrypt:32768:8:1$zEvz3W4JyOkrE4Ww$e935288ad068863adefcabb00d893ea190b34a85c08a8834b1fd2197775c50a060c629dee9b094d3ec9643b06b709f764577aa700cfa35c8c6f88ff8f3df0683', "role": "Администратор"},
    "buh": {"password": 'scrypt:32768:8:1$ZZPFCz68LW9Vz3zV$950acbeb5fad7a70248a4d235ee369f5fb4cb8a20ef8806158c81ee1de7e68e01ffa8946232c12352a659affe8f1328d3a72bcdc27b9e8dd15f08a6dddb0827c', "role": "Бухгалтер"},
    "prakt": {"password": 'scrypt:32768:8:1$OceYDEqcmjcx5hCJ$32dde19ac8eef6eaeff5121850e9baacfda32b68660eccf25d8bea9b9e91d7b31f6e07ccdebc467a049ae478512cb34fb698045f10a1e7d46dcaadef2d4ea594', "role": "Практикант"},
    "ADS": {"password": 'scrypt:32768:8:1$2wMs9XrNVo9VJKTy$731ab15f83868e3d8316ba93f01ea67271561bf8053b9970fe03810fdd4f219bac0829f9a565f724caf032cda5652bd89d751e70c4d41ba02e1544129e522e18', "role": "АДС"}
}
DB_FILE = "equipment.db"

# Создаем окружение Jinja2 для добавления пользовательских фильтров
env = Environment(loader=FileSystemLoader(app.template_folder))
app.jinja_env.add_extension('jinja2.ext.do')

def format_datetime_filter(value):
    if value is None:
        return ""
    # Преобразуем строку в объект datetime
    dt_object = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    # Форматируем в нужный вид: ДД.ММ.ГГ ЧЧ:ММ
    return dt_object.strftime("%d.%m.%y %H:%M")

app.jinja_env.filters['format_datetime'] = format_datetime_filter

def format_component_details(component_type, details):
    """Форматирует детали компонента в читаемую строку. details может быть словарем или списком словарей."""
    if not details:
        return ""

    field_order = {
        "Процессор": ["name", "model", "frequency", "cores"],
        "Материнская плата": ["name", "model", "socket"],
        "Оперативная память": ["name", "model", "capacity", "type"],
        "Хранение данных": ["name", "model", "capacity", "type"],
        "Видеокарта": ["name", "model", "memory"],
        "Блок питания": ["name", "model", "power"],
        "Корпус": ["name", "model", "form_factor"]
    }

    def format_single_item(item_dict):
        parts = []
        fields_to_format = field_order.get(component_type, item_dict.keys())
        for key in fields_to_format:
            if key in item_dict and item_dict[key]:
                value = item_dict[key]
                if component_type == 'Процессор':
                    if key == 'frequency': value = f"{value} ГГц"
                    if key == 'cores': value = f"{value} ядра"
                elif component_type in ['Оперативная память', 'Хранение данных'] and key == 'capacity':
                    value = f"{value} ГБ"
                elif component_type == 'Видеокарта' and key == 'memory':
                    value = f"{value} ГБ"
                elif component_type == 'Блок питания' and key == 'power':
                    value = f"{value} Вт"
                parts.append(str(value))
        return " ".join(parts) if component_type == 'Процессор' else ", ".join(parts)

    # Преобразуем в список, если это не список, для единообразной обработки
    if not isinstance(details, list):
        details = [details]

    return ' | '.join(format_single_item(item) for item in details)

def format_details_filter(value):
    """Форматирует JSON-строку в читаемый вид."""
    try:
        details = json.loads(value)
        if not details:
            return '-'
        
        formatted_parts = []
        
        # Форматирование 'manual_components'
        if 'manual_components' in details:
            manual_components = details['manual_components']
            if manual_components:
                formatted_parts.append("Компоненты (вручную):")
                for comp_type, comp_details in manual_components.items():
                    # comp_details может быть словарем или списком словарей
                    details_str = format_component_details(comp_type, comp_details)
                    formatted_parts.append(f"  - {comp_type}: {details_str}")
        
        # Форматирование 'components'
        if 'components' in details:
            components = details['components']
            if components:
                formatted_parts.append("Компоненты (из базы):")
                db = get_db()
                cursor = db.cursor()
                for comp_type, comp_id in components.items():
                    cursor.execute("SELECT name, details FROM equipment WHERE id=?", (comp_id,))
                    comp_data = cursor.fetchone()
                    if comp_data:
                        comp_name = comp_data[0] or f'ID: {comp_id}'
                        comp_details_json = comp_data[1] or '{}'
                        try:
                            comp_details_dict = json.loads(comp_details_json)
                            details_str = format_component_details(comp_type, comp_details_dict)
                            formatted_parts.append(f"  - {comp_type}: {comp_name} ({details_str})")
                        except json.JSONDecodeError:
                            formatted_parts.append(f"  - {comp_type}: {comp_name} (некорректные детали)")
                    else:
                        formatted_parts.append(f"  - {comp_type}: ID {comp_id} (не найден)")

        # Форматирование остальных полей
        other_details = {k: v for k, v in details.items() if k not in ['manual_components', 'components']}
        if other_details:
            formatted_parts.append("Прочие детали:")
            for key, val in other_details.items():
                label = FIELD_LABELS.get(key, key)
                formatted_parts.append(f"  - {label}: {val}")

        return '\n'.join(formatted_parts)
        
    except (json.JSONDecodeError, TypeError):
        return value if value else '-'

app.jinja_env.filters['format_details'] = format_details_filter

PDF_UPLOAD_FOLDER = os.path.join('static', 'uploads', 'pdfs')

# Создаем папку для загрузки PDF, если ее нет
if not os.path.exists(PDF_UPLOAD_FOLDER):
    os.makedirs(PDF_UPLOAD_FOLDER)

# Все типы оборудования из примеров
EQUIPMENT_TYPES = {
    "Компьютеры": {
        "icon": "fas fa-desktop",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Списаны", "Нераспределённые", "Архив"]
    },
    "Процессор": {
        "icon": "fas fa-microchip",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Оперативная память": {
        "icon": "fas fa-memory",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Хранение данных": {
        "icon": "fas fa-hdd",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Материнская плата": {
        "icon": "fas fa-server",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Видеокарта": {
        "icon": "fas fa-gamepad",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Блок питания": {
        "icon": "fas fa-bolt",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Корпус": {
        "icon": "fas fa-box",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Мониторы": {
        "icon": "fas fa-tv",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Мыши": {
        "icon": "fas fa-mouse",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Клавиатуры": {
        "icon": "fas fa-keyboard",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Наушники": {
        "icon": "fas fa-headphones",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Оборудование": {
        "icon": "fas fa-tools",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Принтеры": {
        "icon": "fas fa-print",
        "statuses": ["Резерв", "Установленные", "Сломанные", "Ремонтируются", "Списание", "Архив"]
    },
    "Картриджи": {
        "icon": "fas fa-tint",
        "statuses": ["Заправленные", "Установленные", "Пустые", "Заправляются", "Списание", "Архив"]
    }
}

# Характеристики для каждого типа оборудования
EQUIPMENT_FIELDS = {
    "Компьютеры": {
        "fields": ["name"],
        "needs_components": True,
        "components": ["Процессор", "Оперативная память", "Хранение данных", "Материнская плата", "Видеокарта", "Блок питания", "Корпус"],
        "multiple_components": ["Хранение данных"]
    },
    "Мониторы": {
        "fields": ["name", "diagonal", "resolution"],
        "needs_components": False
    },
    "Мыши": {
        "fields": ["name", "model"],
        "needs_components": False
    },
    "Клавиатуры": {
        "fields": ["name", "model"],
        "needs_components": False
    },
    "Наушники": {
        "fields": ["name", "model"],
        "needs_components": False
    },
    "Принтеры": {
        "fields": ["name", "model"],
        "needs_components": False
    },
    "Картриджи": {
        "fields": ["name", "model"],
        "needs_components": False
    },
    "Процессор": {
        "fields": ["name", "model", "frequency", "cores"],
        "needs_components": False
    },
    "Оперативная память": {
        "fields": ["name", "capacity", "type"],
        "needs_components": False
    },
    "Хранение данных": {
        "fields": ["name", "capacity", "type"],
        "needs_components": False
    },
    "Материнская плата": {
        "fields": ["name", "model", "socket"],
        "needs_components": False
    },
    "Видеокарта": {
        "fields": ["name", "model", "memory"],
        "needs_components": False
    },
    "Корпус": {
        "fields": ["name", "model", "form_factor"],
        "needs_components": False
    },
    "Блок питания": {
        "fields": ["name", "power"],
        "needs_components": False
    },
    "Оборудование": {
        "fields": ["name", "model"],
        "needs_components": False
    }
}

DEPARTMENTS = ["АДС", "АУП", "ТиС", "ГИС", "HR-отдел"]

FIELD_LABELS = {
    'name': 'Название',
    'model': 'Модель',
    'diagonal': 'Диагональ',
    'resolution': 'Разрешение',
    'frequency': 'Частота',
    'cores': 'Ядра',
    'capacity': 'Объем',
    'type': 'Тип',
    'socket': 'Сокет',
    'memory': 'Память',
    'form_factor': 'Форм-фактор',
    'power': 'Мощность',
    'inventory_number': 'Инвентарный номер',
    'department': 'Отдел',
    'price': 'Стоимость',
    'status': 'Статус',
    'comment': 'Комментарий',
    'created': 'Создание',
    'details': 'Детали',
    'pdf_path': 'PDF-файл',
    'archived': 'Архивация',
    'unarchived': 'Восстановление',
    'deleted': 'Удаление'
}

# --- Управление базой данных ---

def get_db():
    """Открывает новое соединение с базой данных, если его еще нет для текущего контекста."""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Закрывает соединение с базой данных."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

# --- Вспомогательные функции ---
 
def get_utc_plus6():
    return (datetime.utcnow() + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
 
def log_change(equipment_id, field_name, old_value, new_value, comment=None):
    """Записывает изменение в историю."""
    db = get_db()
    cursor = db.cursor()
    change_date = get_utc_plus6()

    # Приводим None к пустой строке для корректного сравнения
    old_value_str = str(old_value) if old_value is not None else ''
    new_value_str = str(new_value) if new_value is not None else ''

    # Если значения идентичны после приведения, не логируем
    if old_value_str == new_value_str:
        return

    # Если поле - 'details', сравниваем JSON-объекты, а не строки
    if field_name == 'details':
        try:
            old_json = json.loads(old_value) if old_value else {}
            new_json = json.loads(new_value) if new_value else {}
            if old_json == new_json:
                return # Не логируем, если объекты идентичны
        except (json.JSONDecodeError, TypeError):
            # Если парсинг не удался, сравниваем как строки
            if old_value_str == new_value_str:
                return
    
    cursor.execute("""
        INSERT INTO history (equipment_id, field_name, old_value, new_value, change_date, comment)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (equipment_id, field_name, old_value_str, new_value_str, change_date, comment))
    db.commit()
 

def parse_details_for_excel(component_type, details_json):
    """Парсит JSON деталей компонента и возвращает словарь с отдельными полями."""
    if not details_json:
        return {}
    try:
        details_dict = json.loads(details_json)
    except json.JSONDecodeError:
        return {'details_raw': details_json} # Если не JSON, сохраняем как есть

    formatted_data = {}
    field_order = {
        "Процессор": ["model", "frequency", "cores"],
        "Материнская плата": ["model", "socket"],
        "Оперативная память": ["capacity", "type"],
        "Хранение данных": ["capacity", "type"],
        "Видеокарта": ["model", "memory"],
        "Блок питания": ["power"],
        "Корпус": ["model", "form_factor"]
    }

    fields_to_format = field_order.get(component_type, details_dict.keys())

    for key in fields_to_format:
        if key in details_dict:
            value = details_dict[key]
            label = FIELD_LABELS.get(key, key)

            # Добавляем единицы измерения
            if component_type == 'Процессор':
                if key == 'frequency': value = f"{value} ГГц"
                if key == 'cores': value = f"{value} ядра"
            elif component_type == 'Оперативная память' and key == 'capacity':
                value = f"{value} ГБ"
            elif component_type == 'Хранение данных' and key == 'capacity':
                value = f"{value} ГБ"
            elif component_type == 'Видеокарта' and key == 'memory':
                value = f"{value} ГБ"
            elif component_type == 'Блок питания' and key == 'power':
                value = f"{value} Вт"
            
            formatted_data[f"{component_type} {label}"] = value
            
    return formatted_data

# Создаем таблицу, если нет
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Проверяем существование таблицы
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='equipment'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            # Проверяем структуру таблицы
            cursor.execute("PRAGMA table_info(equipment)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Миграция колонок
            if 'status' not in columns:
                cursor.execute("ALTER TABLE equipment ADD COLUMN status TEXT NOT NULL DEFAULT 'Установленные'")

            if 'name' not in columns:
                cursor.execute("ALTER TABLE equipment ADD COLUMN name TEXT")

            if 'created_at' not in columns:
                cursor.execute("ALTER TABLE equipment ADD COLUMN created_at INTEGER")

            if 'inventory_number' not in columns:
                cursor.execute("ALTER TABLE equipment ADD COLUMN inventory_number TEXT")

            if 'local_id' not in columns:
                cursor.execute("ALTER TABLE equipment ADD COLUMN local_id INTEGER")
            
            if 'pdf_path' not in columns:
                cursor.execute("ALTER TABLE equipment ADD COLUMN pdf_path TEXT")
            
            # Добавляем новую колонку 'department', если ее нет
            if 'department' not in columns:
                cursor.execute("ALTER TABLE equipment ADD COLUMN department TEXT")

            # Добавляем новую колонку 'price', если ее нет
            if 'price' not in columns:
                cursor.execute("ALTER TABLE equipment ADD COLUMN price REAL") # Используем REAL для дробных чисел

            if 'comment' not in columns:
                cursor.execute("ALTER TABLE equipment ADD COLUMN comment TEXT")
                
        else:
            # Создаем новую таблицу без недопустимого DEFAULT
            cursor.execute("""
            CREATE TABLE equipment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                name TEXT,
                status TEXT NOT NULL DEFAULT 'Установленные',
                details TEXT,
                inventory_number TEXT,
                local_id INTEGER,
                created_at INTEGER,
                pdf_path TEXT,
                department TEXT,
                price REAL,
                comment TEXT
            )
            """)
        
        # Создаем таблицу для архива
        cursor.execute("""
    CREATE TABLE IF NOT EXISTS archived_equipment (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT,
            status TEXT,
            details TEXT,
            inventory_number TEXT,
            local_id INTEGER,
            created_at INTEGER,
            pdf_path TEXT,
            department TEXT,
            price REAL,
            comment TEXT
        )
        """)

        # Проверяем и обновляем структуру таблицы archived_equipment
        cursor.execute("PRAGMA table_info(archived_equipment)")
        archived_columns = [column[1] for column in cursor.fetchall()]
        
        if 'department' not in archived_columns:
            cursor.execute("ALTER TABLE archived_equipment ADD COLUMN department TEXT")
        if 'price' not in archived_columns:
            cursor.execute("ALTER TABLE archived_equipment ADD COLUMN price REAL")
        if 'comment' not in archived_columns:
            cursor.execute("ALTER TABLE archived_equipment ADD COLUMN comment TEXT")
    
        # Создаем таблицу для истории изменений
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT NOT NULL,
            change_date TEXT NOT NULL,
            comment TEXT,
            FOREIGN KEY (equipment_id) REFERENCES equipment(id)
        )
        """)

        # Проверяем существование таблицы history
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='history'")
        history_table_exists = cursor.fetchone()

        if history_table_exists:
            # Проверяем структуру таблицы history
            cursor.execute("PRAGMA table_info(history)")
            history_columns = [column[1] for column in cursor.fetchall()]
            
            # Миграция: Добавляем колонку 'comment', если ее нет
            if 'comment' not in history_columns:
                cursor.execute("ALTER TABLE history ADD COLUMN comment TEXT")

        db.commit()

init_db()

# --- Аутентификация ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    """Декоратор для проверки ролей пользователей."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get('user', {}).get('role')
            if user_role not in allowed_roles:
                flash('У вас нет прав для выполнения этого действия.', 'danger')
                return redirect(request.referrer or url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.context_processor
def inject_user():
    return dict(user_session=session.get('user'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = USERS.get(username)
        if user and check_password_hash(user['password'], password):
            session['user'] = {'username': username, 'role': user['role']}
            flash('Вы успешно вошли в систему.', 'success')
            next_url = request.args.get('next')
            return redirect(next_url or url_for('index'))
        else:
            flash('Неверный логин или пароль.', 'danger')
    return render_template('login.html', equipment_types=EQUIPMENT_TYPES, equipment_fields=EQUIPMENT_FIELDS, is_component_category=False)

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))

@app.route('/')
@login_required
def index():
    db = get_db()
    cursor = db.cursor()
    
    # Подсчитываем статистику для каждого типа оборудования
    stats = {}
    for eq_type in EQUIPMENT_TYPES.keys():
        stats[eq_type] = {}
        for status in EQUIPMENT_TYPES[eq_type]["statuses"]:
            if status == "Архив":
                cursor.execute("SELECT COUNT(*) FROM archived_equipment WHERE type=?", (eq_type,))
            else:
                cursor.execute("SELECT COUNT(*) FROM equipment WHERE type=? AND status=?", (eq_type, status))
            count = cursor.fetchone()[0]
            stats[eq_type][status] = count
    
    return render_template("index.html", equipment_types=EQUIPMENT_TYPES,
                         equipment_fields=EQUIPMENT_FIELDS, stats=stats)

def get_next_local_id(db, eq_type):
    """Получает следующий локальный ID для категории"""
    cursor = db.cursor()
    cursor.execute("SELECT MAX(local_id) FROM equipment WHERE type=?", (eq_type,))
    result = cursor.fetchone()
    if result[0] is not None:
        return result[0] + 1
    return 1

@app.route('/add', methods=['GET', 'POST'])
@app.route('/add/<category>', methods=['GET', 'POST'])
@login_required
@role_required(['Администратор', 'Бухгалтер'])
def add_equipment(category=None):
    if request.method == 'POST':
        eq_type = request.form['type']
        name = request.form.get('name', '')
        # Статус "Резерв" только для нового оборудования (не для Компьютеров)
        # Логика для ADD (создание)
        status = request.form.get('status')
        if not status or status == '':
             status = 'Резерв' if eq_type != 'Компьютеры' else 'Нераспределённые'
        inventory_number = request.form.get('inventory_number', '')
        department = request.form.get('department', '') # Получаем отдел
        price = request.form.get('price', None) # Получаем стоимость
        comment = request.form.get('comment', '') # Получаем комментарий
        if price:
            try:
                price = float(price)
            except ValueError:
                price = None
        created_at = get_utc_plus6()

        # Обработка загрузки PDF
        pdf_file = request.files.get('pdf_file')
        pdf_path = None
        if pdf_file and pdf_file.filename.endswith('.pdf'):
            # Создаем безопасное имя файла
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(pdf_file.filename)}"
            pdf_path = os.path.join(PDF_UPLOAD_FOLDER, filename)
            pdf_file.save(pdf_path)
            # Сохраняем относительный путь для использования в url_for
            pdf_path = os.path.join('uploads', 'pdfs', filename).replace('\\', '/')

        # Собираем характеристики в зависимости от типа
        details_dict = {}
        if eq_type in EQUIPMENT_FIELDS:
            for field in EQUIPMENT_FIELDS[eq_type]["fields"]:
                if field != "name":
                    value = request.form.get(field, '') if field != 'type' else request.form.get('component_type', '')
                    if value:
                        details_dict[field] = value
        
        # Добавляем текст, вписанный вручную
        manual_components_text = request.form.get('manual_components_text', '')
        if manual_components_text:
            try:
                manual_data = json.loads(manual_components_text)
                # Убедимся, что 'Хранение данных' всегда является списком
                if 'Хранение данных' in manual_data and not isinstance(manual_data['Хранение данных'], list):
                    manual_data['Хранение данных'] = [manual_data['Хранение данных']]
                details_dict['manual_components'] = manual_data
            except json.JSONDecodeError:
                # Если введенный текст не является валидным JSON, игнорируем его
                pass

        db = get_db()
        cursor = db.cursor()
        
        # Получаем следующий локальный ID для этой категории
        local_id = get_next_local_id(db, eq_type)
        
        # Для компьютера собираем комплектующие
        if eq_type == "Компьютеры" and EQUIPMENT_FIELDS[eq_type]["needs_components"]:
            components_dict = {}
            multiple_components = EQUIPMENT_FIELDS[eq_type].get("multiple_components", [])
            for component_type in EQUIPMENT_FIELDS[eq_type]["components"]:
                if component_type in multiple_components:
                    component_ids = request.form.getlist(f"component_{component_type}")
                    if component_ids:
                        # Фильтруем пустые значения, если они есть
                        valid_ids = [cid for cid in component_ids if cid]
                        if valid_ids:
                            components_dict[component_type] = valid_ids
                            for component_id in valid_ids:
                                try:
                                    cursor.execute("UPDATE equipment SET status='Установленные' WHERE id=? AND status='Резерв'", (int(component_id),))
                                except:
                                    pass
                else:
                    component_id = request.form.get(f"component_{component_type}", '')
                    if component_id:
                        components_dict[component_type] = component_id
                        try:
                            cursor.execute("UPDATE equipment SET status='Установленные' WHERE id=? AND status='Резерв'", (int(component_id),))
                        except:
                            pass
            if components_dict:
                details_dict["components"] = components_dict
        
        details = json.dumps(details_dict, ensure_ascii=False) if details_dict else ''
        
        cursor.execute("""
            INSERT INTO equipment (type, name, status, details, inventory_number, local_id, created_at, pdf_path, department, price, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (eq_type, name, status, details, inventory_number, local_id, created_at, pdf_path, department, price, comment))

        new_id = cursor.lastrowid
        
        # Логируем создание нового оборудования
        log_change(new_id, 'created', 'None', f'Новое оборудование: {eq_type} - {name}', 'Добавлено новое оборудование')

        db.commit()
        
        # Редирект на страницу категории, если была указана категория
        redirect_url = request.form.get('redirect_category')
        if redirect_url:
            return redirect(url_for('category_view', category=redirect_url))
        return redirect(url_for('index'))
    
    # GET запрос - показываем форму
    pre_selected_type = category if category and category in EQUIPMENT_TYPES else None
    return render_template("add_edit.html", equipment_types=EQUIPMENT_TYPES,
                         equipment_fields=EQUIPMENT_FIELDS, pre_selected_type=pre_selected_type,
                         departments=DEPARTMENTS)

@app.route('/category/<category>')
@login_required
def category_view(category):
    if category not in EQUIPMENT_TYPES:
        return redirect(url_for('index'))

    # Получаем параметры фильтрации из GET-запроса
    selected_department = request.args.get('department', 'all')
    selected_status = request.args.get('status', 'all')

    category_icon = EQUIPMENT_TYPES.get(category, {}).get('icon', 'fas fa-question-circle')

    db = get_db()
    cursor = db.cursor()

    # Формируем данные для таблицы
    cursor.execute("PRAGMA table_info(equipment)")
    db_columns_info = cursor.fetchall()
    db_columns = [col[1] for col in db_columns_info]

    # Если local_id отсутствует для старых записей, заполняем его
    cursor.execute("SELECT id, type FROM equipment WHERE local_id IS NULL")
    missing_local_ids = cursor.fetchall()
    for item_id, item_type in missing_local_ids:
        local_id = get_next_local_id(db, item_type)
        cursor.execute("UPDATE equipment SET local_id=? WHERE id=?", (local_id, item_id))
    db.commit()

    # --- Фильтрация ---
    base_query = "SELECT id, type, name, status, details, inventory_number, local_id, created_at, pdf_path, department, price, comment FROM equipment WHERE type=?"
    params = [category]

    if selected_department != 'all':
        base_query += " AND department=?"
        params.append(selected_department)

    if selected_status != 'all':
        base_query += " AND status=?"
        params.append(selected_status)

    cursor.execute(base_query, params)
    items = cursor.fetchall()
    
    # Для компьютеров загружаем информацию о комплектующих
    if category == "Компьютеры" and EQUIPMENT_FIELDS.get("Компьютеры", {}).get("needs_components"):
        components_info = {}
        for item in items:
            # Парсим details для получения компонентов
            item_dict_temp = {}
            for i, col_name in enumerate(['id', 'type', 'name', 'status', 'details', 'inventory_number', 'local_id', 'created_at', 'pdf_path', 'department', 'price', 'comment']):
                if col_name in db_columns and i < len(item):
                    item_dict_temp[col_name] = item[i]
            
            if item_dict_temp.get('details'):
                try:
                    details_parsed = json.loads(item_dict_temp['details'])
                    if details_parsed.get('components'):
                        for comp_type, comp_ids_raw in details_parsed['components'].items():
                            # Убедимся, что comp_ids это всегда список
                            if not isinstance(comp_ids_raw, list):
                                comp_ids_raw = [comp_ids_raw]
                            
                            # Преобразуем все ID в int, отфильтровывая пустые значения
                            comp_ids = [int(cid) for cid in comp_ids_raw if cid]
                            if not comp_ids: continue

                            placeholders = ','.join('?' for _ in comp_ids)
                            cursor.execute(f"SELECT id, name, details FROM equipment WHERE id IN ({placeholders})", comp_ids)
                            
                            all_comp_data = cursor.fetchall()
                            comps_data_map = {c['id']: c for c in all_comp_data}

                            comp_info_list = []
                            for comp_id in comp_ids:
                                comp_data = comps_data_map.get(comp_id) # Теперь и ключ, и ID - целые числа
                                if comp_data:
                                    comp_name = comp_data['name'] or f'ID: {comp_id}'
                                    comp_details_json = comp_data['details'] or '{}'
                                    comp_info = {'name': comp_name, 'id': comp_id}
                                    try:
                                        cdp = json.loads(comp_details_json)
                                        comp_info['formatted_details'] = format_component_details(comp_type, cdp)
                                    except:
                                        comp_info['formatted_details'] = "Ошибка в деталях"
                                    comp_info_list.append(comp_info)

                            if comp_info_list:
                                key = f"{item_dict_temp['id']}_{comp_type}"
                                components_info[key] = comp_info_list
                except:
                    pass
        available_components = components_info
    else:
        available_components = {}
    
    # Определяем порядок колонок (явно указан в SELECT)
    columns = ['id', 'type', 'name', 'status', 'details', 'inventory_number', 'local_id', 'created_at', 'pdf_path', 'department', 'price', 'comment']
    # Берем только те колонки, которые есть в БД
    actual_columns = [col for col in columns if col in db_columns]
    
    equipment_list = []
    for item in items:
        # Создаем словарь с правильным маппингом колонок
        item_dict = {}
        for i, col_name in enumerate(columns):
            if col_name in db_columns:
                try:
                    item_dict[col_name] = item[i] if i < len(item) else None
                except:
                    item_dict[col_name] = None
            else:
                item_dict[col_name] = None
        
        # Инициализируем отсутствующие поля
        if 'inventory_number' not in item_dict:
            item_dict['inventory_number'] = None
        if 'local_id' not in item_dict:
            item_dict['local_id'] = None
        if 'department' not in item_dict:
            item_dict['department'] = None
        if 'price' not in item_dict:
            item_dict['price'] = None
        if 'comment' not in item_dict:
            item_dict['comment'] = None
        
        # Очищаем name от JSON, если он там случайно попал
        if item_dict.get('name') and isinstance(item_dict['name'], str) and item_dict['name'].strip().startswith('{'):
            try:
                # Если name содержит JSON, пытаемся извлечь нормальное имя
                name_data = json.loads(item_dict['name'])
                if isinstance(name_data, dict):
                    # Если в JSON есть поле name, используем его
                    if 'name' in name_data:
                        item_dict['name'] = name_data['name']
                    # Иначе пытаемся найти любое текстовое значение
                    else:
                        item_dict['name'] = ''
                        # Если details пустое, переносим данные туда
                        if not item_dict['details']:
                            item_dict['details'] = json.dumps(name_data, ensure_ascii=False)
                else:
                    item_dict['name'] = ''
            except:
                # Если не удалось распарсить, оставляем как есть, но проверяем
                if item_dict['name'].startswith('{'):
                    item_dict['name'] = ''
        
        # Парсим details из JSON
        if item_dict['details']:
            try:
                details_str = item_dict['details'].strip()
                if details_str.startswith('{') or details_str.startswith('['):
                    details_parsed = json.loads(details_str)
                    # --- НАЧАЛО ИСПРАВЛЕНИЯ ---
                    # Убедимся, что manual_components['Хранение данных'] всегда является списком
                    if 'manual_components' in details_parsed and 'Хранение данных' in details_parsed['manual_components']:
                        storage_data = details_parsed['manual_components']['Хранение данных']
                        if not isinstance(storage_data, list):
                            details_parsed['manual_components']['Хранение данных'] = [storage_data]
                    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
                    item_dict['details_parsed'] = details_parsed
                else:
                    item_dict['details_parsed'] = {}
            except (json.JSONDecodeError, TypeError):
                item_dict['details_parsed'] = {}
        else:
            item_dict['details_parsed'] = {}
        equipment_list.append(item_dict)
    
    # Получаем конфигурацию полей для текущей категории
    category_fields_config = EQUIPMENT_FIELDS.get(category, {"fields": ["name"], "needs_components": False})
    
    # Получаем список компонентов для передачи в шаблон
    components_list = EQUIPMENT_FIELDS.get('Компьютеры', {}).get('components', [])
    
    # Проверяем, является ли текущая категория комплектующим
    is_component_category = category in components_list

    return render_template("category.html", category=category, equipment=equipment_list,
                           equipment_types=EQUIPMENT_TYPES, equipment_fields=EQUIPMENT_FIELDS,
                           category_fields_config=category_fields_config,
                           available_components=available_components,
                           departments=DEPARTMENTS,
                           category_icon=category_icon,
                           selected_department=selected_department,
                           selected_status=selected_status,
                           components_list_json=json.dumps(components_list),
                           is_component_category=is_component_category)

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['Администратор', 'Бухгалтер'])
def edit_equipment(id):
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        # Получаем старые данные перед обновлением для логирования
        cursor.execute("SELECT type, name, status, details, inventory_number, pdf_path, department, price, comment FROM equipment WHERE id=?", (id,))
        old_item_data = cursor.fetchone()
        if not old_item_data:
            return redirect(url_for('index'))
            
        old_type, old_name, old_status, old_details, old_inventory_number, old_pdf_path, old_department, old_price, old_comment = old_item_data

        eq_type = request.form['type']
        name = request.form.get('name', '')
        
        status = request.form.get('status', old_status)
        inventory_number = request.form.get('inventory_number', '')
        department = request.form.get('department', '') # Получаем отдел
        price = request.form.get('price', None) # Получаем стоимость
        comment = request.form.get('comment', '') # Получаем комментарий
        if price:
            try:
                price = float(price)
            except ValueError:
                price = None
        
        # Собираем характеристики в зависимости от типа
        # Если тип был изменен, мы начинаем с чистого словаря деталей.
        # В противном случае, мы загружаем существующие детали.
        if old_type != eq_type:
            details_dict = {}
        else:
            try:
                details_dict = json.loads(old_details) if old_details else {}
            except (json.JSONDecodeError, TypeError):
                details_dict = {}

        # Обновляем/заполняем поля на основе данных из формы
        if eq_type in EQUIPMENT_FIELDS:
            for field in EQUIPMENT_FIELDS[eq_type]["fields"]:
                if field == 'name':
                    continue
                input_name = 'component_type' if field == 'type' else field
                if input_name in request.form:
                    value = request.form.get(input_name)
                    if value:
                        details_dict[field] = value
                    elif field in details_dict:
                        del details_dict[field]
        
        # Обновляем `manual_components`
        manual_components_text = request.form.get('manual_components_text')
        if manual_components_text:
            try:
                manual_data = json.loads(manual_components_text)
                # Убедимся, что 'Хранение данных' является списком, только если оно существует
                if 'Хранение данных' in manual_data and not isinstance(manual_data['Хранение данных'], list):
                    manual_data['Хранение данных'] = [manual_data['Хранение данных']]
                
                # Удаляем пустые записи из списка, если он есть
                if 'Хранение данных' in manual_data and isinstance(manual_data['Хранение данных'], list):
                    manual_data['Хранение данных'] = [s for s in manual_data['Хранение данных'] if s]
                
                if manual_data:
                    details_dict['manual_components'] = manual_data
                elif 'manual_components' in details_dict:
                    del details_dict['manual_components']

            except json.JSONDecodeError:
                pass  # Оставляем старые данные, если новый JSON невалиден
        elif 'manual_components' in details_dict:
            del details_dict['manual_components']

        # Обрабатываем `components` из базы
        if eq_type == "Компьютеры" and EQUIPMENT_FIELDS[eq_type].get("needs_components"):
            old_components = details_dict.get('components', {})
            new_components = {}
            
            # Собираем новые компоненты из формы
            for comp_type in EQUIPMENT_FIELDS[eq_type]["components"]:
                is_multiple = comp_type in EQUIPMENT_FIELDS[eq_type].get("multiple_components", [])
                if is_multiple:
                    ids = request.form.getlist(f"component_{comp_type}")
                    # Фильтруем пустые значения
                    valid_ids = [cid for cid in ids if cid]
                    if valid_ids:
                        new_components[comp_type] = valid_ids
                else:
                    id_val = request.form.get(f"component_{comp_type}")
                    if id_val:
                        new_components[comp_type] = id_val

            # Обновляем статусы
            all_comp_types = set(old_components.keys()) | set(new_components.keys())
            for comp_type in all_comp_types:
                # Гарантируем, что old_ids_raw и new_ids_raw всегда являются списками
                old_ids_raw = old_components.get(comp_type, [])
                if not isinstance(old_ids_raw, list):
                    old_ids_raw = [old_ids_raw]

                new_ids_raw = new_components.get(comp_type, [])
                if not isinstance(new_ids_raw, list):
                    new_ids_raw = [new_ids_raw]

                old_ids = {str(i) for i in old_ids_raw if i}
                new_ids = {str(i) for i in new_ids_raw if i}

                to_reserve = old_ids - new_ids
                to_install = new_ids - old_ids

                for cid in to_reserve:
                    try:
                        cursor.execute("UPDATE equipment SET status='Резерв' WHERE id=?", (int(cid),))
                        log_change(id, 'details', f'Удален компонент ID {cid}', '', f'Компонент возвращен в резерв')
                    except: pass
                for cid in to_install:
                    try:
                        cursor.execute("UPDATE equipment SET status='Установленные' WHERE id=?", (int(cid),))
                        log_change(id, 'details', '', f'Добавлен компонент ID {cid}', f'Компонент установлен')
                    except: pass
            
            # Обновляем словарь деталей новыми компонентами
            details_dict['components'] = new_components
        else:
            # Если новый тип - не "Компьютеры", удаляем информацию о компонентах
            details_dict.pop('components', None)
            details_dict.pop('manual_components', None)

        # Преобразуем итоговый словарь в JSON
        details = json.dumps(details_dict, ensure_ascii=False) if details_dict else ''
        
        # Обработка загрузки PDF
        pdf_file = request.files.get('pdf_file')
        pdf_path = request.form.get('existing_pdf_path') # Получаем существующий путь

        if pdf_file and pdf_file.filename.endswith('.pdf'):
            # Если есть старый файл, удаляем его
            if pdf_path and os.path.exists(os.path.join('static', pdf_path)):
                os.remove(os.path.join('static', pdf_path))

            # Сохраняем новый файл
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(pdf_file.filename)}"
            save_path = os.path.join(PDF_UPLOAD_FOLDER, filename)
            pdf_file.save(save_path)
            pdf_path = os.path.join('uploads', 'pdfs', filename).replace('\\', '/')
        
        # Логируем изменения
        if old_type != eq_type:
            log_change(id, 'type', old_type, eq_type, f'Изменен тип с {old_type} на {eq_type}')
        if old_name != name:
            log_change(id, 'name', old_name, name, f'Изменено название с {old_name} на {name}')
        if old_status != status:
            log_change(id, 'status', old_status, status, f'Изменен статус с {old_status} на {status}')
        if old_inventory_number != inventory_number:
            log_change(id, 'inventory_number', old_inventory_number, inventory_number, f'Изменен инвентарный номер с {old_inventory_number} на {inventory_number}')
        if old_pdf_path != pdf_path:
            log_change(id, 'pdf_path', old_pdf_path, pdf_path, f'Изменен путь к PDF с {old_pdf_path} на {pdf_path}')
        if old_department != department:
            log_change(id, 'department', old_department, department, f'Изменен отдел с {old_department} на {department}')
        # Улучшенное логирование для цены и комментария
        if old_price != price:
            old_p = old_price or 'None'
            new_p = price or 'None'
            log_change(id, 'price', old_price, price, f'Изменена цена с {old_p} на {new_p}')
        
        if old_comment != comment:
            old_c = f'"{old_comment}"' if old_comment else 'None'
            new_c = f'"{comment}"' if comment else 'None'
            log_change(id, 'comment', old_comment, comment, f'Изменен комментарий с {old_c} на {new_c}')
        # Сравниваем old_details и new_details более гранулярно
        try:
            old_details_dict = json.loads(old_details) if old_details else {}
            new_details_dict = json.loads(details) if details else {}

            # Нормализация 'Хранение данных' в 'manual_components'
            if 'manual_components' in old_details_dict and 'Хранение данных' in old_details_dict['manual_components']:
                if not isinstance(old_details_dict['manual_components']['Хранение данных'], list):
                    old_details_dict['manual_components']['Хранение данных'] = [old_details_dict['manual_components']['Хранение данных']]
            if 'manual_components' in new_details_dict and 'Хранение данных' in new_details_dict['manual_components']:
                if not isinstance(new_details_dict['manual_components']['Хранение данных'], list):
                    new_details_dict['manual_components']['Хранение данных'] = [new_details_dict['manual_components']['Хранение данных']]

            # Сравниваем нормализованные словари
            if old_details_dict != new_details_dict:
                # Разделяем на 'manual_components' и 'other_details' для более чистого лога
                old_manual = old_details_dict.pop('manual_components', {})
                new_manual = new_details_dict.pop('manual_components', {})
                old_components_from_db = old_details_dict.pop('components', {})
                new_components_from_db = new_details_dict.pop('components', {})

                # Логируем изменения в 'manual_components'
                if old_manual != new_manual:
                    log_change(id, 'details',
                               json.dumps({'manual_components': old_manual}, ensure_ascii=False) if old_manual else '',
                               json.dumps({'manual_components': new_manual}, ensure_ascii=False) if new_manual else '',
                               'Изменены компоненты (вручную)')

                # Логируем изменения в остальных деталях
                if old_details_dict != new_details_dict:
                    log_change(id, 'details',
                               json.dumps(old_details_dict, ensure_ascii=False) if old_details_dict else '',
                               json.dumps(new_details_dict, ensure_ascii=False) if new_details_dict else '',
                               'Изменены прочие детали')

        except (json.JSONDecodeError, TypeError):
            # Если детали не в формате JSON, сравниваем как строки
            if old_details != details:
                log_change(id, 'details', old_details, details, 'Изменены детали оборудования')


        cursor.execute("UPDATE equipment SET type=?, name=?, status=?, details=?, inventory_number=?, pdf_path=?, department=?, price=?, comment=? WHERE id=?",
                      (eq_type, name, status, details, inventory_number, pdf_path, department, price, comment, id))
        db.commit()
        
        # Редирект на страницу НОВОЙ категории
        return redirect(url_for('category_view', category=eq_type))
    
    # GET запрос - показываем форму редактирования
    cursor.execute("SELECT id, type, name, status, details, inventory_number, pdf_path, department, price, comment FROM equipment WHERE id=?", (id,))
    item = cursor.fetchone()
    
    if not item:
        return redirect(url_for('index'))
    
    item_dict = {
        'id': item[0],
        'type': item[1],
        'name': item[2] or '',
        'status': item[3],
        'details': item[4] or '{}',
        'inventory_number': item[5] or '',
        'pdf_path': item[6] or '',
        'department': item[7] or '',
        'price': item[8] if item[8] is not None else '',
        'comment': item[9] or ''
    }
    
    # Парсим details
    try:
        details_parsed = json.loads(item_dict['details'])
        item_dict['details_parsed'] = details_parsed
        # Добавляем отформатированные детали для каждого компонента, если есть
        if 'components' in details_parsed:
            formatted_components = {}
            for comp_type, comp_ids_raw in details_parsed['components'].items():
                comp_ids = comp_ids_raw if isinstance(comp_ids_raw, list) else [comp_ids_raw]
                if not comp_ids: continue

                placeholders = ','.join('?' for _ in comp_ids)
                comp_cursor = get_db().cursor()
                comp_cursor.execute(f"SELECT id, name, details FROM equipment WHERE id IN ({placeholders})", comp_ids)
                
                components_data = comp_cursor.fetchall()
                if not components_data: continue

                formatted_components[comp_type] = []
                for comp_data in components_data:
                    comp_details_dict = {}
                    try:
                        comp_details_dict = json.loads(comp_data['details'] or '{}')
                    except (json.JSONDecodeError, TypeError):
                        pass
                    
                    # Передаем сам словарь, а не список словарей для обычных компонентов
                    details_to_format = comp_details_dict
                    formatted_components[comp_type].append({
                        "id": comp_data['id'],
                        "name": comp_data['name'],
                        "details": format_component_details(comp_type, details_to_format)
                    })

            item_dict['details_parsed']['formatted_components'] = formatted_components
    except (json.JSONDecodeError, TypeError) as e:
        # Убеждаемся, что details_parsed всегда является объектом, даже при ошибке парсинга
        item_dict['details_parsed'] = {}
    
    return render_template("add_edit.html", equipment_types=EQUIPMENT_TYPES,
                         equipment_fields=EQUIPMENT_FIELDS,
                         edit_item=item_dict, is_edit=True,
                         departments=DEPARTMENTS)
@app.route('/view/<int:id>')
@login_required
def view_equipment(id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM equipment WHERE id=?", (id,))
    item_data = cursor.fetchone()

    if not item_data:
        return redirect(url_for('index'))

    columns = [description[0] for description in cursor.description]
    item_dict = dict(zip(columns, item_data))

    # Parse details
    try:
        details_parsed = json.loads(item_dict.get('details', '{}'))
        item_dict['details_parsed'] = details_parsed
    except (json.JSONDecodeError, TypeError):
        item_dict['details_parsed'] = {}
    
    available_components = {}
    if item_dict.get('type') == "Компьютеры":
        details_parsed = item_dict.get('details_parsed', {})
        if details_parsed and details_parsed.get('components'):
            components_info = {}
            for comp_type, comp_ids_raw in details_parsed['components'].items():
                comp_ids = comp_ids_raw if isinstance(comp_ids_raw, list) else [comp_ids_raw]
                if not comp_ids: continue

                placeholders = ','.join('?' for _ in comp_ids)
                cursor.execute(f"SELECT id, name, details FROM equipment WHERE id IN ({placeholders})", comp_ids)
                all_comp_data = cursor.fetchall()
                if not all_comp_data: continue

                comp_data_map = {c['id']: c for c in all_comp_data}
                
                comp_infos = []
                for comp_id in comp_ids:
                    comp_data = comp_data_map.get(int(comp_id))
                    if not comp_data: continue

                    comp_name = comp_data['name'] or f'ID: {comp_id}'
                    comp_details_json = comp_data['details'] or '{}'
                    comp_info = {'name': comp_name, 'id': comp_id}
                    try:
                        comp_details_parsed = json.loads(comp_details_json)
                        comp_info['formatted_details'] = format_component_details(comp_type, comp_details_parsed)
                    except (json.JSONDecodeError, TypeError):
                        comp_info['formatted_details'] = "Детали в неверном формате"
                    comp_infos.append(comp_info)
                
                if comp_infos:
                    components_info[f"{item_dict['id']}_{comp_type}"] = comp_infos
            available_components = components_info


    return render_template("view.html", 
                           item=item_dict, 
                           equipment_types=EQUIPMENT_TYPES, 
                           equipment_fields=EQUIPMENT_FIELDS,
                           field_labels=FIELD_LABELS,
                           available_components=available_components,
                           format_component_details=format_component_details)
 
@app.route('/archive_equipment/<int:id>')
@login_required
@role_required(['Администратор', 'Бухгалтер'])
def archive_equipment(id):
    """Перемещает элемент в архив"""
    db = get_db()
    cursor = db.cursor()
    
    # Копируем запись в архивную таблицу
    cursor.execute("SELECT * FROM equipment WHERE id=?", (id,))
    item_data = cursor.fetchone()
    if item_data:
        columns = [description[0] for description in cursor.description]
        # Создаем словарь из данных
        item_dict = dict(zip(columns, item_data))
        
        # Вставляем в архивную таблицу
        placeholders = ', '.join(['?'] * len(item_dict))
        cols = ', '.join(item_dict.keys())
        sql = f"INSERT INTO archived_equipment ({cols}) VALUES ({placeholders})"
        cursor.execute(sql, list(item_dict.values()))

        # Удаляем из основной таблицы
        cursor.execute("DELETE FROM equipment WHERE id=?", (id,))
        log_change(id, 'archived', item_dict['status'], 'Архив', f'Оборудование {item_dict["name"]} (ID: {id}) перемещено в архив')
    
    db.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/unarchive_equipment/<int:id>')
@login_required
@role_required(['Администратор', 'Бухгалтер'])
def unarchive_equipment(id):
    """Возвращает элемент из архива"""
    db = get_db()
    cursor = db.cursor()
    
    # Копируем запись в основную таблицу
    cursor.execute("SELECT * FROM archived_equipment WHERE id=?", (id,))
    item_data = cursor.fetchone()
    if item_data:
        columns = [description[0] for description in cursor.description]
        item_dict = dict(zip(columns, item_data))
        
        placeholders = ', '.join(['?'] * len(item_dict))
        cols = ', '.join(item_dict.keys())
        sql = f"INSERT INTO equipment ({cols}) VALUES ({placeholders})"
        cursor.execute(sql, list(item_dict.values()))

        # Удаляем из архивной таблицы
        cursor.execute("DELETE FROM archived_equipment WHERE id=?", (id,))
        log_change(id, 'unarchived', item_dict['status'], 'Восстановлено', f'Оборудование {item_dict["name"]} (ID: {id}) восстановлено из архива')
    
    db.commit()
    return redirect(url_for('archive_view'))

@app.route('/delete/<int:id>')
@login_required
@role_required(['Администратор', 'Бухгалтер'])
def delete_equipment(id):
    """Окончательно удаляет элемент из БД"""
    db = get_db()
    cursor = db.cursor()
    
    # Если удаляем компьютер, возвращаем компоненты в резерв
    cursor.execute("SELECT type, details FROM archived_equipment WHERE id=?", (id,))
    item_data = cursor.fetchone()
    if item_data and item_data[0] == "Компьютеры" and item_data[1]:
        try:
            details_parsed = json.loads(item_data[1])
            components = details_parsed.get('components', {})
            for comp_id in components.values():
                try:
                    cursor.execute("UPDATE equipment SET status='Резерв' WHERE id=?", (int(comp_id),))
                except:
                    pass
        except:
            pass
    
    cursor.execute("DELETE FROM archived_equipment WHERE id=?", (id,))
    log_change(id, 'deleted', 'Архив', 'Удалено', f'Оборудование (ID: {id}) окончательно удалено из архива')
    db.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/update_status/<int:id>', methods=['POST'])
@login_required
@role_required(['Администратор', 'Бухгалтер'])
def update_status(id):
    new_status = request.json.get('status')
    db = get_db()
    cursor = db.cursor()

    # Сначала получаем информацию о типе оборудования
    cursor.execute("SELECT type, details FROM equipment WHERE id=?", (id,))
    item_data = cursor.fetchone()
    
    if item_data:
        item_type = item_data[0]
        item_details = item_data[1]
        
        # Получаем старый статус для логирования
        cursor.execute("SELECT status FROM equipment WHERE id=?", (id,))
        old_status = cursor.fetchone()[0]

        # Обновляем статус основного элемента
        cursor.execute("UPDATE equipment SET status=? WHERE id=?", (new_status, id))
        log_change(id, 'status', old_status, new_status, f'Статус изменен с {old_status} на {new_status}') # Логируем изменение статуса

        # Если это компьютер, обновляем статус его компонентов на такой же, как у компьютера
        if item_type == "Компьютеры" and item_details:
            try:
                details_parsed = json.loads(item_details)
                components = details_parsed.get('components', {})
                for comp_id in components.values():
                    try:
                        # Получаем старый статус компонента для логирования
                        cursor.execute("SELECT status FROM equipment WHERE id=?", (int(comp_id),))
                        old_comp_status = cursor.fetchone()[0]
                        # Устанавливаем компоненту тот же статус, что и у компьютера
                        cursor.execute("UPDATE equipment SET status=? WHERE id=?", (new_status, int(comp_id)))
                        log_change(int(comp_id), 'status', old_comp_status, new_status, f'Статус компонента изменен с {old_comp_status} на {new_status} (вместе с компьютером)')
                    except:
                        pass # Игнорируем ошибки, если компонент не найден
            except json.JSONDecodeError:
                pass # Игнорируем ошибки, если details невалидный JSON
 
    db.commit()
    return jsonify({'success': True})

@app.route('/api/components/<component_type>')
def get_components(component_type):
    """API для получения доступных компонентов определенного типа"""
    # Получаем ID компонента для редактирования, если есть
    component_ids_str = request.args.get('component_ids', '[]')
    try:
        component_ids = json.loads(component_ids_str)
        if not isinstance(component_ids, list):
            component_ids = [component_ids]
    except json.JSONDecodeError:
        component_ids = []

    db = get_db()
    cursor = db.cursor()

    # Формируем запрос для получения компонентов в резерве ИЛИ тех, что уже выбраны
    query = "SELECT id, name, details, status FROM equipment WHERE type=? AND (status='Резерв'"
    params = [component_type]
    
    if component_ids:
        placeholders = ','.join(['?'] * len(component_ids))
        query += f" OR id IN ({placeholders})"
        params.extend(component_ids)
    
    query += ")"
    cursor.execute(query, params)
    components = cursor.fetchall()
    
    result = []
    for comp in components:
        # Парсим details для получения дополнительной информации
        details_json = comp[2] or '{}'
        
        comp_status = comp['status']
        is_installed = comp_status != 'Резерв'
        status_label = ' (Установлен)' if is_installed else ''

        formatted_details = ""
        try:
            details_dict = json.loads(details_json)
            formatted_details = format_component_details(component_type, details_dict)
        except (json.JSONDecodeError, TypeError):
            formatted_details = details_json

        comp_dict = {
            'id': comp['id'],
            'name': (comp['name'] or f'ID: {comp["id"]}') + status_label,
            'details': formatted_details,
            'is_installed': is_installed,
            'status': comp_status
        }
        result.append(comp_dict)
    
    return jsonify(result)

@app.route('/api/field_values/<field_name>')
def get_field_values(field_name):
    """API для получения уникальных значений для поля."""
    db = get_db()
    cursor = db.cursor()
    
    # Для поля 'name' ищем в 'name', для остальных - в 'details'
    if field_name == 'name':
        cursor.execute(f"SELECT DISTINCT name FROM equipment WHERE name IS NOT NULL")
    else:
        cursor.execute(f"SELECT details FROM equipment WHERE details IS NOT NULL")
    
    values = []
    if field_name == 'name':
        values = [row[0] for row in cursor.fetchall()]
    else:
        for row in cursor.fetchall():
            try:
                details = json.loads(row[0])
                if field_name in details:
                    values.append(details[field_name])
            except json.JSONDecodeError:
                pass
    
    return jsonify(list(set(values)))

@app.route('/export/<category>')
@login_required
@role_required(['Администратор', 'Бухгалтер', 'АДС'])
def export_excel(category):
    import pandas as pd
    import sqlite3, json
    from flask import send_file
    import xlsxwriter
    from io import BytesIO
 
    db = get_db()
    cursor = db.cursor()
 
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    workbook = writer.book
    sheet_name = 'Компьютеры'

    # === Форматы ===
    border_fmt = {'border': 1, 'align': 'left', 'valign': 'vcenter'}
    fmt_bold = workbook.add_format({'bold': True, 'font_size': 11})
    fmt_header = workbook.add_format({
        'bold': True,
        'align': 'center',
        'valign': 'vcenter',
        'border': 1,
        'bg_color': '#D9D9D9'
    })
    fmt_normal = workbook.add_format(border_fmt)
    fmt_wrap = workbook.add_format({**border_fmt, 'text_wrap': True})

    # === Колонки: теперь 6 столбцов ===
    cols = ["Комплектующее", "Модель", "ИНВ", "Статус", "Характеристики", "Стоимость"]

    worksheet = workbook.add_worksheet(sheet_name)
    worksheet.set_column(0, 0, 28)  # Комплектующее
    worksheet.set_column(1, 1, 30)  # Модель
    worksheet.set_column(2, 2, 12)  # ИНВ
    worksheet.set_column(3, 3, 14)  # Статус
    worksheet.set_column(4, 4, 40)  # Характеристики
    worksheet.set_column(5, 5, 12)  # Стоимость

    row = 0

    if category == "Компьютеры":
        cursor.execute("""
            SELECT id, name, inventory_number, details, status, local_id, department, price
            FROM equipment WHERE type=?
        """, (category,))
        computers = cursor.fetchall()

        preferred_order = [
            "Процессор", "Оперативная память", "Хранение данных",
            "Материнская плата", "Блок питания", "Корпус"
        ]

        for comp_id, name, inv_number, details_json, status, local_id, department, comp_price in computers:
            details = json.loads(details_json or '{}')

            # === Заголовок компьютера ===
            header_text = (
                f"Компьютер: {name or ''}, ИНВ: {inv_number or ''}, "
                f"Отдел: {department or ''}, Стоимость: {comp_price or ''}"
            )
            worksheet.merge_range(row, 0, row, 5, header_text, fmt_bold)
            row += 1

            # === Шапка таблицы ===
            for col_idx, col_name in enumerate(cols):
                worksheet.write(row, col_idx, col_name, fmt_header)
            row += 1

            # === Компоненты ===
            components = details.get('components', {}) or {}
            ordered_keys = []
            for k in preferred_order:
                if k in components:
                    ordered_keys.append(k)
            for k in components.keys():
                if k not in ordered_keys:
                    ordered_keys.append(k)

            for comp_type in ordered_keys:
                c_id = components.get(comp_type)
                if not c_id:
                    continue

                # теперь добавляем извлечение цены
                # Преобразуем c_id в список, если это не так
                c_ids = c_id if isinstance(c_id, list) else [c_id]
                placeholders = ','.join('?' for _ in c_ids)
                
                cursor.execute(f"""
                    SELECT name, details, inventory_number, status, price
                    FROM equipment WHERE id IN ({placeholders})
                """, c_ids)
                
                all_comp_data = cursor.fetchall()

                if not all_comp_data:
                    worksheet.write(row, 0, comp_type, fmt_normal)
                    for i in range(1, 6):
                        worksheet.write(row, i, '', fmt_normal)
                    row += 1
                    continue

                for comp_sql_data in all_comp_data:
                    comp_name = comp_sql_data['name']
                    comp_details_json = comp_sql_data['details']
                    comp_inv_number = comp_sql_data['inventory_number']
                    comp_status = comp_sql_data['status']
                    comp_price = comp_sql_data['price']
                    comp_details = json.loads(comp_details_json or '{}')

                    char_parts = []
                    if isinstance(comp_details, dict):
                        for k, v in comp_details.items():
                            if v is None or v == '':
                                continue
                            if isinstance(v, (list, tuple)):
                                for vv in v:
                                    if vv not in (None, ''):
                                        char_parts.append(str(vv))
                            else:
                                char_parts.append(str(v))
                    elif isinstance(comp_details, (list, tuple)):
                        for v in comp_details:
                            if v not in (None, ''):
                                char_parts.append(str(v))
                    elif comp_details not in (None, ''):
                        char_parts.append(str(comp_details))

                    formatted_chars = ", ".join(char_parts)

                    worksheet.write(row, 0, comp_type, fmt_normal)
                    worksheet.write(row, 1, comp_name or '', fmt_normal)
                    worksheet.write(row, 2, comp_inv_number or '', fmt_normal)
                    worksheet.write(row, 3, comp_status or '', fmt_normal)
                    worksheet.write(row, 4, formatted_chars, fmt_wrap)
                    worksheet.write(row, 5, comp_price or '', fmt_normal)
                    row += 1

            # === Ручные комплектующие ===
            manual_components = details.get('manual_components', {}) or {}
            manual_components = details.get('manual_components', {}) or {}
            for manual_comp_type, manual_comp_items in manual_components.items():
                # Если это не список, делаем его списком для единообразия
                if not isinstance(manual_comp_items, list):
                    manual_comp_items = [manual_comp_items]

                for item_details in manual_comp_items:
                    model = item_details.get('model', '')
                    inv = item_details.get('inventory_number', '')
                    price = item_details.get('price', '')
                    
                    char_parts = []
                    for k, v in item_details.items():
                        if k in ('model', 'inventory_number', 'price', 'name'): # name тоже часто основное поле
                            continue
                        if v: char_parts.append(str(v))

                    formatted_chars = ", ".join(char_parts)

                    # Используем 'name' если есть, иначе 'model'
                    display_name = item_details.get('name', model)

                    worksheet.write(row, 0, manual_comp_type, fmt_normal)
                    worksheet.write(row, 1, display_name or '', fmt_normal)
                    worksheet.write(row, 2, inv or '', fmt_normal)
                    worksheet.write(row, 3, "Установленные", fmt_normal)
                    worksheet.write(row, 4, formatted_chars, fmt_wrap)
                    worksheet.write(row, 5, price or '', fmt_normal)
                    row += 1

            # === Пустая строка ===
            row += 1

    # --- Остальные категории (без изменений, просто добавлен price в SELECT) ---
    else:
        cursor.execute("""
            SELECT id, type, name, status, details, inventory_number, local_id, created_at, pdf_path, department, price
            FROM equipment WHERE type=?
        """, (category,))
        items = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        df_rows = []
        for item in items:
            item_dict = dict(zip(columns, item))
            details_for_excel = parse_details_for_excel(item_dict.get('type'), item_dict.get('details'))
            row_data = {
                FIELD_LABELS['name']: item_dict.get('name', ''),
                FIELD_LABELS['inventory_number']: item_dict.get('inventory_number', ''),
                'Статус': item_dict.get('status', ''),
                'Отдел': item_dict.get('department', ''),
                'Стоимость': item_dict.get('price', ''),
            }
            row_data.update(details_for_excel)
            df_rows.append(row_data)

        if df_rows:
            df = pd.DataFrame(df_rows)
            df.to_excel(writer, sheet_name=category, index=False)

    writer.close()
 
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"{category}_export.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/help')
@login_required
def help_page():
    """Рендерит страницу справки"""
    return render_template("help.html", equipment_types=EQUIPMENT_TYPES, equipment_fields=EQUIPMENT_FIELDS)

@app.route('/archive')
@login_required
def archive_view():
    """Рендерит страницу архива"""
    selected_department = request.args.get('department', 'all')
    selected_status = request.args.get('status', 'all')

    db = get_db()
    cursor = db.cursor()

    # --- Фильтрация ---
    base_query = "SELECT id, type, name, inventory_number, status, created_at, local_id, department, price FROM archived_equipment"
    filters = []
    params = []

    if selected_department != 'all':
        filters.append("department=?")
        params.append(selected_department)

    if selected_status != 'all':
        filters.append("status=?")
        params.append(selected_status)

    if filters:
        base_query += " WHERE " + " AND ".join(filters)

    cursor.execute(base_query, params)
    equipment = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

    # Получаем все возможные статусы из основной таблицы для фильтра
    cursor.execute("SELECT DISTINCT status FROM equipment UNION SELECT DISTINCT status FROM archived_equipment")
    all_statuses = [row[0] for row in cursor.fetchall() if row[0]]

    return render_template("archive.html",
                           equipment=equipment,
                           equipment_types=EQUIPMENT_TYPES,
                           equipment_fields=EQUIPMENT_FIELDS,
                           departments=DEPARTMENTS,
                           all_statuses=all_statuses,
                           selected_department=selected_department,
                           selected_status=selected_status,
                           components_list_json=json.dumps(EQUIPMENT_FIELDS.get('Компьютеры', {}).get('components', [])))

@app.route('/download_pdf/<path:filename>')
def download_pdf(filename):
    """Безопасно отдает загруженный PDF-файл"""
    # Путь к папке с PDF внутри static
    pdf_dir = os.path.join(app.root_path, 'static', 'uploads', 'pdfs')
    safe_filename = secure_filename(filename)
    if not safe_filename:
        return "Некорректное имя файла", 400
    try:
        return send_file(os.path.join(pdf_dir, safe_filename), as_attachment=True)
    except FileNotFoundError:
        return "Файл не найден", 404
    
@app.route('/history/<int:equipment_id>')
def history_view(equipment_id):
    db = get_db()
    cursor = db.cursor()

    # Получаем информацию о комплектующем
    cursor.execute("SELECT type, name, inventory_number, details FROM equipment WHERE id=?", (equipment_id,))
    equipment_info = cursor.fetchone()

    if not equipment_info:
        # Если не найдено в основной таблице, ищем в архиве
        cursor.execute("SELECT type, name, inventory_number, details FROM archived_equipment WHERE id=?", (equipment_id,))
        equipment_info = cursor.fetchone()
        if not equipment_info:
            flash('Оборудование не найдено.', 'danger')
            return redirect(url_for('index'))

    eq_type, eq_name, eq_inv_number, eq_details = equipment_info

    # Получаем историю изменений для данного комплектующего
    cursor.execute("SELECT id, field_name, old_value, new_value, change_date, comment FROM history WHERE equipment_id=? ORDER BY change_date DESC", (equipment_id,))
    history_records = cursor.fetchall()

    history_list = []
    for record in history_records:
        record_id, field_name, old_value, new_value, change_date, comment = record
        
        # Обработка поля details
        if field_name == 'details':
            try:
                old_details_dict = json.loads(old_value) if old_value and old_value.strip() else {}
                new_details_dict = json.loads(new_value) if new_value and new_value.strip() else {}
                
                # Форматируем в удобочитаемый вид
                old_value_formatted = format_details_filter(json.dumps(old_details_dict, ensure_ascii=False))
                new_value_formatted = format_details_filter(json.dumps(new_details_dict, ensure_ascii=False))

            except (json.JSONDecodeError, TypeError):
                old_value_formatted = old_value
                new_value_formatted = new_value
        else:
            old_value_formatted = old_value
            new_value_formatted = new_value

        history_list.append({
            'id': record_id,
            'field_name': field_name, # Передаем оригинальное имя поля
            'old_value': old_value_formatted,
            'new_value': new_value_formatted,
            'change_date': change_date,
            'comment': comment
        })

    return render_template("history.html",
                           equipment_id=equipment_id,
                           equipment_type=eq_type,
                           equipment_name=eq_name,
                           equipment_inv_number=eq_inv_number,
                           history=history_list,
                           equipment_types=EQUIPMENT_TYPES,
                           equipment_fields=EQUIPMENT_FIELDS,
                           field_labels=FIELD_LABELS
                          )


@app.route('/update_history_comment/<int:history_id>', methods=['POST'])
@login_required
@role_required(['Администратор', 'Бухгалтер'])
def update_history_comment(history_id):
    new_comment = request.json.get('comment')
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE history SET comment=? WHERE id=?", (new_comment, history_id))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/cleanup_history')
@login_required
@role_required(['Администратор'])
def cleanup_history():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id, field_name, old_value, new_value FROM history")
    records = cursor.fetchall()
    
    ids_to_delete = []
    for record in records:
        field_name = record['field_name']
        old_val_str = record['old_value'] if record['old_value'] is not None and record['old_value'] != 'None' else ''
        new_val_str = record['new_value'] if record['new_value'] is not None and record['new_value'] != 'None' else ''

        if field_name == 'details':
            try:
                old_json = json.loads(old_val_str) if old_val_str else {}
                new_json = json.loads(new_val_str) if new_val_str else {}
                
                # Нормализация
                for data in [old_json, new_json]:
                    if 'manual_components' in data and 'Хранение данных' in data['manual_components']:
                        storage = data['manual_components']['Хранение данных']
                        if not isinstance(storage, list):
                            data['manual_components']['Хранение данных'] = [storage]

                if old_json == new_json:
                    ids_to_delete.append(record['id'])
            except (json.JSONDecodeError, TypeError):
                if old_val_str == new_val_str:
                    ids_to_delete.append(record['id'])
        else:
            if old_val_str == new_val_str:
                ids_to_delete.append(record['id'])

    if ids_to_delete:
        cursor.execute(f"DELETE FROM history WHERE id IN ({','.join('?' for _ in ids_to_delete)})", ids_to_delete)
        flash(f'Удалено {len(ids_to_delete)} некорректных записей из истории.', 'success')

    # Обновляем комментарии
    cursor.execute("UPDATE history SET comment = REPLACE(comment, 'с None на', 'на') WHERE field_name = 'price' AND comment LIKE '%с None на%'")
    cursor.execute("UPDATE history SET comment = REPLACE(comment, 'с \"\" на', 'на') WHERE field_name = 'comment' AND comment LIKE '%с \"\" на%'")
    cursor.execute("UPDATE history SET comment = REPLACE(comment, 'с None на', 'на') WHERE field_name = 'comment' AND comment LIKE '%с None на%'")
    
    db.commit()
    
    flash('Очистка истории завершена.', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')



