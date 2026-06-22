"""
infrastructure.external.email_service
=====================================
خدمة إرسال البريد الإلكتروني — تعمل في وضع stub عند عدم تهيئة SMTP.

عند توفّر متغيرات البيئة SMTP_HOST / SMTP_USER / SMTP_PASS،
تتحول تلقائياً إلى وضع الإرسال الفعلي عبر aiosmtplib.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# إعدادات SMTP (تُقرأ من env)
# ──────────────────────────────────────────────

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@smartland.example")


def is_smtp_configured() -> bool:
    """هل إعدادات SMTP متوفرة؟"""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS)


# ──────────────────────────────────────────────
#send_email (async)
# ──────────────────────────────────────────────

async def send_email(
    subject: str,
    body: str,
    to: str,
    html: Optional[str] = None,
    from_addr: str = SMTP_FROM,
) -> Dict[str, Any]:
    """إرسال بريد إلكتروني.

    Args:
        subject: الموضوع
        body: النص العادي
        to: عنوان المستلم
        html: محتوى HTML اختياري
        from_addr: عنوان المرسل

    Returns:
        dict: {"success": bool, "stub": bool, "to": str, "subject": str, ...}
    """
    if not is_smtp_configured():
        # وضع stub — لا إرسال فعلي
        logger.info("[EMAIL STUB] to=%s subject=%s", to, subject)
        return {
            "success": True,
            "stub": True,
            "to": to,
            "subject": subject,
            "from": from_addr,
            "body_preview": body[:80] + "..." if len(body) > 80 else body,
        }

    # وضع الإرسال الفعلي عبر aiosmtplib
    try:
        import aiosmtplib  # noqa
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=True,
        )
        logger.info("[EMAIL] sent to=%s subject=%s", to, subject)
        return {
            "success": True,
            "stub": False,
            "to": to,
            "subject": subject,
            "from": from_addr,
        }
    except ImportError:
        logger.warning("aiosmtplib غير مثبّت — العودة لوضع stub")
        return {
            "success": True,
            "stub": True,
            "to": to,
            "subject": subject,
            "from": from_addr,
        }
    except Exception as e:
        logger.error("[EMAIL] فشل الإرسال إلى %s: %s", to, e)
        return {
            "success": False,
            "stub": False,
            "to": to,
            "subject": subject,
            "from": from_addr,
            "error": str(e),
        }


# ──────────────────────────────────────────────
# build_notification_email_html
# ──────────────────────────────────────────────

# قالب HTML أساسي (RTL + تنسيق عربي)
_EMAIL_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #f8fafc; margin: 0; padding: 20px; }}
    .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }}
    .header {{ background: linear-gradient(135deg, #1E3A8A, #2563EB); color: white;
               padding: 24px 32px; }}
    .header h1 {{ margin: 0; font-size: 20px; font-weight: 600; }}
    .header .event-tag {{ display: inline-block; margin-top: 8px; padding: 4px 12px;
                          background: rgba(255,255,255,0.2); border-radius: 12px;
                          font-size: 11px; font-weight: 500; }}
    .body {{ padding: 32px; color: #1F2937; line-height: 1.6; font-size: 15px; }}
    .footer {{ padding: 16px 32px; background: #F1F5F9; color: #64748B;
               font-size: 12px; text-align: center; }}
    .footer a {{ color: #2563EB; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{title}</h1>
      <span class="event-tag">{event_type}</span>
    </div>
    <div class="body">
      {body}
    </div>
    <div class="footer">
      Smart Land Management Copilot · <a href="https://smartland.example">إدارة الإشعارات</a>
    </div>
  </div>
</body>
</html>"""


def build_notification_email_html(
    title: str,
    body: str,
    event_type: str = "notification",
) -> str:
    """يبني HTML لبريد إشعار عربي (RTL)."""
    # escapaة بسيطة
    safe_title = title.replace("<", "&lt;").replace(">", "&gt;")
    safe_body = body.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    safe_event = event_type.replace("<", "&lt;").replace(">", "&gt;")

    return _EMAIL_HTML_TEMPLATE.format(
        title=safe_title,
        body=safe_body,
        event_type=safe_event,
    )


__all__ = [
    "send_email",
    "build_notification_email_html",
    "is_smtp_configured",
]
