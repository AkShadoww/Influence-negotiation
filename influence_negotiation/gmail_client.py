"""
Gmail API client — read unread messages in tracked threads, send replies.
Uses OAuth2 credentials stored in credentials.json / token.json.
"""

import base64
import logging
import os
from email.mime.text import MIMEText
from typing import List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import GMAIL_CREDENTIALS_FILE, GMAIL_TOKEN_FILE, GMAIL_SCOPES

logger = logging.getLogger(__name__)


def _get_credentials() -> Credentials:
    creds = None
    if os.path.exists(GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return creds


def get_service():
    return build("gmail", "v1", credentials=_get_credentials())


def get_unread_messages_in_thread(thread_id: str) -> List[dict]:
    """
    Return all unread messages in a Gmail thread, oldest first.
    Each item: {"id": str, "body": str, "from": str, "subject": str}
    """
    service = get_service()
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    messages = thread.get("messages", [])
    result = []
    for msg in messages:
        label_ids = msg.get("labelIds", [])
        if "UNREAD" not in label_ids:
            continue
        result.append(_parse_message(msg))
    return result


def get_unread_messages_from_email(sender_email: str) -> List[dict]:
    """
    Search for unread messages from a specific sender (used when thread_id unknown).
    Returns parsed message dicts.
    """
    service = get_service()
    query = f"from:{sender_email} is:unread"
    response = service.users().messages().list(userId="me", q=query).execute()
    messages = response.get("messages", [])
    result = []
    for m in messages:
        full = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        result.append(_parse_message(full))
    return result


def _parse_message(msg: dict) -> dict:
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    body = _extract_body(msg["payload"])
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "body": body,
    }


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if mime_type.startswith("multipart"):
        for part in payload.get("parts", []):
            text = _extract_body(part)
            if text:
                return text
    return ""


def send_reply(
    thread_id: str,
    to_email: str,
    subject: str,
    body: str,
    in_reply_to_message_id: Optional[str] = None,
) -> str:
    """Send an email reply within a Gmail thread. Returns the sent message id."""
    service = get_service()
    mime_msg = MIMEText(body, "plain")
    mime_msg["To"] = to_email
    mime_msg["Subject"] = subject
    if in_reply_to_message_id:
        mime_msg["In-Reply-To"] = in_reply_to_message_id
        mime_msg["References"] = in_reply_to_message_id

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw, "threadId": thread_id})
        .execute()
    )
    logger.info("Sent message id=%s to %s (thread %s)", sent["id"], to_email, thread_id)
    return sent["id"]


def mark_as_read(message_id: str) -> None:
    service = get_service()
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()


def get_thread_id_for_message(message_id: str) -> Optional[str]:
    service = get_service()
    msg = service.users().messages().get(userId="me", id=message_id, format="minimal").execute()
    return msg.get("threadId")
