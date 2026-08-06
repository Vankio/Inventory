@echo off
echo Activating virtual environment...

:: Проверка наличия окружения
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment '.venv' not found!
    echo Please run this command first: python -m venv .venv
    pause
    exit /b
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
py -m pip install --upgrade pip
py -m pip install requests schedule flask-wtf pandas xlsxwriter

echo Starting backup script in a new window...
start "Backup" python backup.py

echo Starting Flask server...
py app.py

:: Окно не закроется, если сервер упадет с ошибкой
pause