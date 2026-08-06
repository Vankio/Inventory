from werkzeug.security import generate_password_hash

passwords = {
    "admin": "724Tis204",
    "buh": "buh724",
    "prakt": "prakt724",
    "ADS": "ADS123"
}

for user, password in passwords.items():
    hashed_password = generate_password_hash(password)
    print(f'"{user}": \'{hashed_password}\',')
