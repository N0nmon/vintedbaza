import os.path
import base64
import re
from bs4 import BeautifulSoup
from html import escape
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from db.database import async_session
from db.models import PlatformAccount, AccountAssignment, User, SystemState

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

KEYWORDS = {
    "Twój przedmiot został sprzedany": "🔥 ПРОДАЖА",
    "Nowa oferta dotycząca ogłoszenia": "💰 Новое предложение (оферта)",
    "Nowa wiadomość na temat ogłoszenia": "💬 Новое сообщение",
    "Twoja rzecz została dodana do ulubionych!": "⭐ Добавлено в избранное"
}

def get_gmail_service():
    print("[DEBUG] Инициализация Gmail сервиса...")
    creds = None
    if os.path.exists("token.json"):
        print("[DEBUG] Найден файл токена.")
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[DEBUG] Токен истек, выполняется обновление...")
            creds.refresh(Request())
        else:
            print("[DEBUG] Токен отсутствует или недействителен, выполняется авторизация...")
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
            print("[DEBUG] Новый токен сохранен.")

    try:
        service = build("gmail", "v1", credentials=creds)
        print("[DEBUG] Gmail сервис успешно инициализирован.")
        return service
    except HttpError as error:
        print(f"[ERROR] Ошибка при инициализации Gmail сервиса: {error}")
        return None

def get_body_text(payload):
    print("[DEBUG] Извлечение текста из тела письма...")
    # Сначала ищем идеальный вариант - text/plain
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                print("[DEBUG] Найден текстовый контент (text/plain).")
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
    
    # Если text/plain не найден на верхнем уровне, ищем его в глубине
    if 'parts' in payload:
        for part in payload['parts']:
            text = get_body_text(part)
            if text:
                print("[DEBUG] Найден текст в глубине.")
                return text

    # Если text/plain вообще нигде нет, берем text/html и чистим его
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/html' and 'data' in part['body']:
                print("[DEBUG] Найден HTML контент, выполняется очистка...")
                html_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html_content, "html.parser")
                return soup.get_text(separator='\n', strip=True)

    # Обработка случая, когда тело письма не разделено на части
    if payload['mimeType'] == 'text/plain' and 'data' in payload['body']:
        print("[DEBUG] Найден текстовый контент (text/plain) без частей.")
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    if payload['mimeType'] == 'text/html' and 'data' in payload['body']:
        print("[DEBUG] Найден HTML контент без частей, выполняется очистка...")
        html_content = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text(separator='\n', strip=True)

    print("[WARNING] Текст письма не найден.")
    return ""

async def check_gmail(bot: Bot):
    print("[DEBUG] Начало проверки Gmail...")
    service = get_gmail_service()
    if not service:
        print("[ERROR] Gmail сервис недоступен.")
        return

    async with async_session() as session:
        stmt = (
            select(PlatformAccount.display_name, PlatformAccount.search_name, User.user_id)
            .join(AccountAssignment, PlatformAccount.id == AccountAssignment.account_id)
            .join(User, AccountAssignment.user_id == User.user_id)
        )
        assignments = (await session.execute(stmt)).all()
        print(f"[DEBUG] Получены назначения: {assignments}")

    search_name_to_users_map = {}
    for display_name, search_name, user_id in assignments:
        if search_name not in search_name_to_users_map:
            search_name_to_users_map[search_name] = {'display_name': display_name, 'users': []}
        search_name_to_users_map[search_name]['users'].append(user_id)
    print(f"[DEBUG] Карта поиска: {search_name_to_users_map}")

    if not search_name_to_users_map:
        print("[WARNING] Нет назначений для обработки.")
        return

    try:
        results = service.users().messages().list(userId="me", q="is:unread").execute()
        messages = results.get("messages", [])
        print(f"[DEBUG] Найдено {len(messages)} непрочитанных сообщений.")

        if not messages:
            print("[INFO] Нет новых сообщений.")
            return

        for message_info in messages:
            msg_id = message_info["id"]
            print(f"[DEBUG] Обработка сообщения с ID: {msg_id}")
            try:
                msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
                headers = msg["payload"]["headers"]
                payload = msg["payload"]
                
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                print(f"[DEBUG] Тема сообщения: {subject}")

                body_text = get_body_text(payload)
                print(f"[DEBUG] Текст сообщения: {body_text}")

                if not body_text:
                    print(f"[WARNING] Сообщение с ID {msg_id} не содержит текста.")
                    service.users().messages().modify(userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}).execute()
                    continue

                found_account_search_name = None
                for search_name in search_name_to_users_map.keys():
                    if re.search(r'\b' + re.escape(search_name) + r'\b', body_text, re.IGNORECASE):
                        found_account_search_name = search_name
                        break
                print(f"[DEBUG] Найден аккаунт: {found_account_search_name}")

                if found_account_search_name:
                    account_info = search_name_to_users_map[found_account_search_name]
                    display_name = account_info['display_name']
                    recipient_users = account_info['users']
                    
                    for keyword, event_type in KEYWORDS.items():
                        if keyword in subject:
                            if event_type == "💬 Новое сообщение":
                                message_match = re.search(r"Nowa wiadomość:\s*(.+?)(?:\n|$)", body_text, re.DOTALL)
                                message_text = message_match.group(1).strip() if message_match else "Текст сообщения не найден."
                                notification_text = (
                                    f"{event_type} на аккаунте <b>{escape(display_name)}</b>!\n\n"
                                    f"Сообщение: <i>{escape(message_text)}</i>"
                                )
                                print(f"[INFO] Уведомление: {notification_text}")
                            else:
                                notification_text = f"{event_type} на аккаунте <b>{escape(display_name)}</b>!"
                                print(f"[INFO] Уведомление: {notification_text}")
                            

                            for user_id in recipient_users:
                                try:
                                    await bot.send_message(chat_id=user_id, text=notification_text, parse_mode="HTML")
                                    print(f"[INFO] Уведомление отправлено пользователю {user_id}.")
                                except Exception as e:
                                    print(f"[ERROR] Ошибка отправки уведомления пользователю {user_id}: {e}")
                            break
                
                service.users().messages().modify(
                    userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
                ).execute()
                print(f"[DEBUG] Сообщение с ID {msg_id} помечено как прочитанное.")

            except Exception as e:
                print(f"[ERROR] Ошибка обработки сообщения с ID {msg_id}: {e}")

    except Exception as e:
        print(f"[ERROR] Ошибка проверки Gmail: {e}")