import os

# Генерируем безопасный секретный ключ
SECRET_KEY = os.urandom(24).hex()