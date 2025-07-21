import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Определяем, какие права мы запрашиваем у Google.
# В данном случае - "читать и изменять" почту (изменять нужно, чтобы помечать письма прочитанными).
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def main():
    """
    Выполняет процесс авторизации и создает файл token.json.
    """
    creds = None
    # Проверяем, есть ли у нас уже пропуск (token.json).
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    # Если пропуска нет или он просрочен, запрашиваем новый.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Обновляю просроченный пропуск...")
            creds.refresh(Request())
        else:
            print("Пропуска нет. Запускаю процесс авторизации...")
            # Используем наш "паспорт" (credentials.json) для запроса.
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            # Эта строка откроет у тебя браузер для подтверждения.
            creds = flow.run_local_server(port=0)
        
        # Сохраняем полученный пропуск в файл token.json для будущего использования.
        with open("token.json", "w") as token:
            token.write(creds.to_json())
            print("\nПропуск успешно получен и сохранен в файл token.json!")

if __name__ == "__main__":
    main()
