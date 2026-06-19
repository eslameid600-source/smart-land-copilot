"""
خدمة البريد الإلكتروني — Email Service (SMTP async)
=====================================================
إرسال إشعارات بالبريد عبر SMTP.

التهيئة عبر متغيرات البيئة:
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=notifications@smartland.eg
    SMTP_PASSWORD=app-specific-password
    SMTP_FROM=Smart Land <noreply@smartland.eg>
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)

# ── إعدادات SMTP ──
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "Smart Land <noreply@smartland.eg>")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"


def _is_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)


async def send_email(
    subject: str,
    body: str,
    recipient: str,
    html_body: Optional[str] = None,
) -> dict:
    """
    إرسال بريد إلكتروني عبر SMTP (في thread pool لتجنب الحظر).

    المعاملات:
        subject:   عنوان البريد
        body:      نص البريد (plain text)
        recipient: عنوان المُستلم
        html_body: نص HTML بديل (اختياري)

    المخرجات:
        {"success": bool, "message_id": str|None, "error": str|None}
    """
    if not _is_configured():
        logger.info(f"[Email-Stub] to {recipient}: {subject}")
        return {
            "success": True,
            "message_id": f"stub-email-{id(recipient)}",
            "error": None,
            "stub": True,
        }

    try:
        result = await asyncio.to_thread(
            _send_email_sync,
            subject, body, recipient, html_body,
        )
        return result
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return {"success": False, "message_id": None, "error": str(e)[:100]}


def _send_email_sync(
    subject: str,
    body: str,
    recipient: str,
    html_body: Optional[str],
) -> dict:
    """إرسال البريد بشكل متزامن (يُستدعى من thread pool)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = recipient

    # Plain text
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # HTML
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)

        server.sendmail(SMTP_FROM, [recipient], msg.as_string())

    msg_id = f"<{id(subject)}@smartland.eg>"
    logger.info(f"Email sent to {recipient}: {subject}")
    return {"success": True, "message_id": msg_id, "error": None}


def build_notification_email_html(
    title: str,
    body: str,
    event_type: str,
) -> str:
    """
    بناء قالب HTML للإشعار بالبريد الإلكتروني.

    يستخدم تصميم RTL عربي مع ألوان Smart Land.
    """
    return f"""\
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #f5f5f5;
         margin: 0; padding: 20px; direction: rtl; }}
  .container {{ max-width: 600px; margin: 0 auto; background: #fff;
                 border-radius: 12px; overflow: hidden;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  .header {{ background: linear-gradient(135deg, #1a5276, #2e86c1);
              padding: 30px; text-align: center; color: #fff; }}
  .header h1 {{ margin: 0; font-size: 24px; }}
  .body {{ padding: 30px; color: #333; line-height: 1.8; font-size: 16px; }}
  .badge {{ display: inline-block; background: #eaf2f8; color: #2e86c1;
            padding: 4px 12px; border-radius: 20px; font-size: 13px;
            margin-bottom: 15px; }}
  .footer {{ background: #f8f9fa; padding: 20px; text-align: center;
              color: #999; font-size: 13px; border-top: 1px solid #eee; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Smart Land Management</h1>
  </div>
  <div class="body">
    <span class="badge">{event_type}</span>
    <h2 style="margin-top:0">{title}</h2>
    <p>{body}</p>
  </div>
  <div class="footer">
    Smart Land Management Copilot &mdash; {event_type}
  </div>
</div>
</body>
</html>"""