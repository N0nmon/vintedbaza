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
from db.models import PlatformAccount, AccountAssignment, User

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

KEYWORDS = {
    "Twój przedmiot został sprzedany": "🔥 ПРОДАЖА",
    "Nowa oferta dotycząca ogłoszenia": "💰 Новое предложение (оферта)",
    "Nowa wiadomość na temat ogłoszenia": "💬 Новое сообщение"
}

def get_gmail_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    
    try:
        service = build("gmail", "v1", credentials=creds)
        return service
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None

def get_body_text(payload):
    """
    Рекурсивно извлекает текстовую часть из тела письма.
    Сначала ищет text/plain. Если не находит, берет text/html и очищает его от тегов.
    """
    # Сначала ищем идеальный вариант - text/plain
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
    
    # Если text/plain не найден на верхнем уровне, ищем его в глубине
    if 'parts' in payload:
        for part in payload['parts']:
            text = get_body_text(part)
            if text:
                return text # Возвращаем первый найденный текст

    # Если text/plain вообще нигде нет, берем text/html и чистим его
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/html' and 'data' in part['body']:
                html_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html_content, "html.parser")
                return soup.get_text(separator='\n', strip=True)

    # Обработка случая, когда тело письма не разделено на части
    if payload['mimeType'] == 'text/plain' and 'data' in payload['body']:
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    if payload['mimeType'] == 'text/html' and 'data' in payload['body']:
        html_content = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text(separator='\n', strip=True)

    return ""

async def check_gmail(bot: Bot):
    print(f"\n[{datetime.now()}] Running Gmail check...")
    service = get_gmail_service()
    if not service:
        print(f"[{datetime.now()}] EXIT: Failed to get Gmail service.")
        return

    async with async_session() as session:
        stmt = (
            select(PlatformAccount.display_name, PlatformAccount.search_name, User.user_id)
            .join(AccountAssignment, PlatformAccount.id == AccountAssignment.account_id)
            .join(User, AccountAssignment.user_id == User.user_id)
        )
        assignments = (await session.execute(stmt)).all()

    search_name_to_users_map = {}
    for display_name, search_name, user_id in assignments:
        if search_name not in search_name_to_users_map:
            search_name_to_users_map[search_name] = {'display_name': display_name, 'users': []}
        search_name_to_users_map[search_name]['users'].append(user_id)

    if not search_name_to_users_map:
        print("No accounts configured for monitoring.")
        return
        
    print(f"--- DEBUG: Tracking search names: {list(search_name_to_users_map.keys())}")

    try:
        results = service.users().messages().list(userId="me", q="is:unread").execute()
        messages = results.get("messages", [])

        if not messages:
            print("No new messages found.")
            return

        print(f"Found {len(messages)} new messages. Processing...")

        for message_info in messages:
            msg_id = message_info["id"]
            try:
                msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
                headers = msg["payload"]["headers"]
                payload = msg["payload"]
                
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                body_text = get_body_text(payload)

                if not body_text:
                    print(f"--- Email ID: {msg_id} has no text body. Marking as read.")
                    # Помечаем как прочитанное, даже если пустое
                    service.users().messages().modify(userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}).execute()
                    continue

                found_account_search_name = None
                for search_name in search_name_to_users_map.keys():
                    if re.search(r'\b' + re.escape(search_name) + r'\b', body_text, re.IGNORECASE):
                        found_account_search_name = search_name
                        break
                
                print(f"--- DEBUG: Checking email ID: {msg_id} ---")
                print(f"Subject: {subject}")
                print(f"Found account search_name in body: {found_account_search_name}")
                print("---------------------------------")

                notification_sent = False
                if found_account_search_name:
                    account_info = search_name_to_users_map[found_account_search_name]
                    display_name = account_info['display_name']
                    recipient_users = account_info['users']
                    
                    for keyword, event_type in KEYWORDS.items():
                        if keyword in subject:
                            print(f"MATCH FOUND! Account: {display_name}, Event: {event_type}")
                            notification_text = f"{event_type} на аккаунте <b>{escape(display_name)}</b>!"
                            
                            for user_id in recipient_users:
                                try:
                                    await bot.send_message(chat_id=user_id, text=notification_text, parse_mode="HTML")
                                    notification_sent = True # Уведомление успешно отправлено хотя бы одному
                                except Exception as e:
                                    print(f"Failed to send notification to user {user_id}: {e}")
                            
                            break # Выходим из цикла по ключевым словам
                
                # Помечаем как прочитанное ЛЮБОЕ обработанное письмо
                service.users().messages().modify(
                    userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
                ).execute()
                print(f"Email ID: {msg_id} marked as read.")

            except Exception as e:
                print(f"An error occurred while processing message ID {msg_id}: {e}")

    except Exception as e:
        print(f"An error occurred while checking Gmail: {e}")