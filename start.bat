@echo off
echo Activating virtual environment...

:: Ïðîâåðêà íàëè÷èÿ îêðóæåíèÿ
if not exist ".venv\Scripts\activate.bat" (
    py -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
py -m pip install --upgrade pip
py -m pip install requests schedule flask-wtf pandas xlsxwriter

echo Starting backup script in a new window...
start "Backup" python backup.py

echo Starting Flask server...
py app.py

:: Îêíî íå çàêðîåòñÿ, åñëè ñåðâåð óïàäåò ñ îøèáêîé
pause
