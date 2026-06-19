"""
WhatsApp Business API Service
==============================
تكامل WhatsApp Business API عبر Twilio أو Meta API المباشر

Supported channels:
    1. Twilio WhatsApp API (recommended for quick setup)
       - Send/receive text messages
       - Template messages (pre-approved by Meta)
       - Interactive messages (buttons, lists)
       - Media messages (images, documents, location)

    2. Meta Cloud API (direct)
       - Same capabilities via Meta's API
       - Requires Facebook Business verification

Architecture:
    - WhatsAppService: main class
    - Webhook handler: parse incoming messages
    - Template manager: manage approved message templates
    - Conversation tracker: track message threads

Prerequisites (Twilio):
    pip install twilio
    env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER

Prerequisites (Meta):
    env: META_ACCESS_TOKEN, META_PHONE_NUMBER_ID, META_WHATSAPP_BUSINESS_ID

Free tier:
    - Twilio: Free trial with verified numbers only
    - Meta: 1,000 conversations/month free
"""

import json
import hmac
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Callable

import requests

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Enums / Constants
# ──────────────────────────────────────────────

class MessageDirection:
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus:
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class Provider:
    TWILIO = "twilio"
    META = "meta"


# ──────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────

class WhatsAppMessage:
    """نموذج رسالة واتساب"""

    def __init__(
        self,
        from_number: str,
        to_number: str,
        body: str,
        direction: str = MessageDirection.OUTBOUND,
        message_id: Optional[str] = None,
        status: str = MessageStatus.QUEUED,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        # Media fields
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,  # image, document, audio, video
        # Interactive fields
        interactive_type: Optional[str] = None,  # button, list, quick_reply
        interactive_options: Optional[List[Dict[str, str]]] = None,
        # Template fields
        template_name: Optional[str] = None,
        template_params: Optional[List[str]] = None,
    ):
        self.message_id = message_id or f"WA-{uuid.uuid4().hex[:12]}"
        self.from_number = from_number
        self.to_number = to_number
        self.body = body
        self.direction = direction
        self.status = status
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.metadata = metadata or {}

        self.media_url = media_url
        self.media_type = media_type
        self.interactive_type = interactive_type
        self.interactive_options = interactive_options or []
        self.template_name = template_name
        self.template_params = template_params

    def to_dict(self) -> Dict[str, Any]:
        """تحويل الرسالة إلى قاموس"""
        result = {
            "message_id": self.message_id,
            "from": self.from_number,
            "to": self.to_number,
            "body": self.body,
            "direction": self.direction,
            "status": self.status,
            "timestamp": self.timestamp,
        }
        if self.media_url:
            result["media_url"] = self.media_url
            result["media_type"] = self.media_type
        if self.template_name:
            result["template_name"] = self.template_name
        if self.interactive_type:
            result["interactive_type"] = self.interactive_type
            result["interactive_options"] = self.interactive_options
        return result

    def __repr__(self) -> str:
        return (
            f"WhatsAppMessage(id={self.message_id}, "
            f"from={self.from_number[:15]}, "
            f"direction={self.direction}, "
            f"status={self.status})"
        )


class WebhookEvent:
    """حدث webhook وارد"""

    def __init__(
        self,
        event_type: str,  # message, delivery, read, error
        phone_number: str,
        message_body: str = "",
        message_id: str = "",
        profile_name: str = "",
        timestamp: Optional[str] = None,
        raw_data: Optional[Dict] = None,
    ):
        self.event_type = event_type
        self.phone_number = phone_number
        self.message_body = message_body
        self.message_id = message_id
        self.profile_name = profile_name
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.raw_data = raw_data or {}


# ──────────────────────────────────────────────
# Template Manager
# ──────────────────────────────────────────────

class TemplateManager:
    """
    إدارة قوالب الرسائل المعتمدة من Meta

    القوالب يجب أن تُعتمد من Meta قبل استخدامها.
    هذا المكون يدير القوالب محلياً للإرسال السريع.
    """

    # قوالب مُعاد استخدامها — النسخة العربية
    TEMPLATES: Dict[str, Dict[str, Any]] = {
        "greeting": {
            "name": "smart_land_greeting",
            "ar": "مرحباً {{1}}! مرحباً بك في Smart Land Copilot.",
            "en": "Hello {{1}}! Welcome to Smart Land Copilot.",
            "params": ["name"],
        },
        "ticket_created": {
            "name": "smart_land_ticket_created",
            "ar": "تم إنشاء تذكرتك بنجاح. رقم التذكرة: {{1}}. سنتواصل معك قريباً.",
            "en": "Your ticket has been created. Ticket #: {{1}}. We'll contact you soon.",
            "params": ["ticket_number"],
        },
        "ticket_resolved": {
            "name": "smart_land_ticket_resolved",
            "ar": "تم حل تذكرتك {{1}}. هل أنت راضٍ عن الخدمة؟ رجّعنا من 1 إلى 5.",
            "en": "Ticket {{1}} has been resolved. Rate us 1-5.",
            "params": ["ticket_number"],
        },
        "survey_prompt": {
            "name": "smart_land_survey",
            "ar": "بعد معاملة رقم {{1}}، ما تقييمك لخدمتنا؟ (1-5 نجوم)",
            "en": "After transaction #{{1}}, how would you rate our service? (1-5 stars)",
            "params": ["transaction_id"],
        },
        "match_alert": {
            "name": "smart_land_match_alert",
            "ar": "وجدنا أرضاً مناسبة لك في {{1}}! المساحة: {{2}} فدان. السعر: {{3}} جنيه.",
            "en": "We found a matching land in {{1}}! Area: {{2}} feddans. Price: {{3}} EGP.",
            "params": ["governorate", "area", "price"],
        },
    }

    def get_template(self, template_key: str, lang: str = "ar") -> Optional[Dict[str, Any]]:
        """استرجاع قالب بالاسم واللغة"""
        template = self.TEMPLATES.get(template_key)
        if template and lang in template:
            return {
                "name": template["name"],
                "body": template[lang],
                "params": template["params"],
            }
        return None

    def fill_template(
        self, template_key: str, params: Dict[str, str], lang: str = "ar"
    ) -> str:
        """
        ملء القالب بالقيم الفعلية

        Args:
            template_key: مفتاح القالب
            params: قاموس المعاملات (مثال: {"name": "أحمد"})
            lang: اللغة (ar/en)

        Returns:
            النص المُكمل
        """
        template = self.get_template(template_key, lang)
        if not template:
            return ""

        body = template["body"]
        template_params = template["params"]
        for i, param_name in enumerate(template_params):
            placeholder = "{{" + str(i + 1) + "}}"
            value = params.get(param_name, "")
            body = body.replace(placeholder, str(value))

        return body


# ──────────────────────────────────────────────
# Main WhatsApp Service
# ──────────────────────────────────────────────

class WhatsAppService:
    """
    خدمة واتساب للأعمال — تكامل كامل عبر Twilio أو Meta

    Usage:
        # Demo mode:
        wa = WhatsAppService(demo_mode=True)

        # Twilio mode:
        wa = WhatsAppService(
            provider="twilio",
            account_sid="ACxxxxx",
            auth_token="xxxxx",
            whatsapp_number="whatsapp:+14155238886",
        )

        # Meta mode:
        wa = WhatsAppService(
            provider="meta",
            access_token="EAAGxxxxx",
            phone_number_id="100xxxxx",
            business_id="10xxxxx",
        )

    Sending messages:
        # Simple text
        wa.send_text("+201012345678", "مرحباً!")

        # Template
        wa.send_template("+201012345678", "greeting", {"name": "أحمد"})

        # Interactive buttons
        wa.send_interactive_buttons(
            "+201012345678",
            "كيف يمكننا مساعدتك؟",
            options=[
                {"id": "faq", "title": "أسئلة شائعة"},
                {"id": "ticket", "title": "فتح تذكرة"},
                {"id": "agent", "title": "التحدث مع وكيل"},
            ]
        )
    """

    # Meta Cloud API endpoints
    META_API_BASE = "https://graph.facebook.com/v18.0"

    def __init__(
        self,
        provider: str = Provider.TWILIO,
        demo_mode: bool = False,
        # Twilio credentials
        account_sid: str = "",
        auth_token: str = "",
        whatsapp_number: str = "",
        # Meta credentials
        access_token: str = "",
        phone_number_id: str = "",
        business_id: str = "",
        # Webhook verification
        webhook_verify_token: str = "smartland_verify_token",
        # General
        timeout: int = 30,
    ):
        """
        تهيئة خدمة واتساب

        Args:
            provider: مزود الخدمة (twilio/meta)
            demo_mode: وضع العرض التوضيحي
            account_sid: معرف حساب Twilio
            auth_token: رمز المصادقة
            whatsapp_number: رقم واتساب التابع للحساب
            access_token: رمز Meta API
            phone_number_id: معرف رقم هاتف Meta
            business_id: معرف الحساب التجاري
            webhook_verify_token: رمز التحقق من webhook
            timeout: مهلة الاتصال
        """
        self.provider = provider
        self.demo_mode = demo_mode
        self.webhook_verify_token = webhook_verify_token
        self.timeout = timeout

        # Twilio
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.whatsapp_number = whatsapp_number

        # Meta
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.business_id = business_id

        # Template manager
        self.templates = TemplateManager()

        # Message log (demo + production)
        self._message_log: List[WhatsAppMessage] = []

        # Webhook handlers
        self._message_handlers: List[Callable[[WebhookEvent], Any]] = []

        # Conversation state tracker
        self._conversations: Dict[str, Dict[str, Any]] = {}

        if not demo_mode:
            if provider == Provider.TWILIO and (not account_sid or not auth_token):
                logger.warning("WhatsApp/Twilio: بيانات غير مكتملة — التبديل لوضع العرض")
                self.demo_mode = True
            elif provider == Provider.META and (not access_token or not phone_number_id):
                logger.warning("WhatsApp/Meta: بيانات غير مكتملة — التبديل لوضع العرض")
                self.demo_mode = True

        logger.info(
            f"WhatsAppService initialized | provider={provider} | "
            f"demo={self.demo_mode}"
        )

    # ──────────────────────────────────────────
    # Sending Messages
    # ──────────────────────────────────────────

    def send_text(
        self,
        to: str,
        body: str,
        from_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        إرسال رسالة نصية عادية

        Args:
            to: رقم المستلم (بصيغة international، مثال: +201012345678)
            body: نص الرسالة
            from_number: رقم المرسل (اختياري، يستخدم الرقم الافتراضي)

        Returns:
            نتيجة الإرسال
        """
        sender = from_number or self.whatsapp_number
        message = WhatsAppMessage(
            from_number=sender,
            to_number=to,
            body=body,
        )

        if self.demo_mode:
            message.status = MessageStatus.SENT
            self._message_log.append(message)
            logger.info(f"[DEMO] WhatsApp text sent to {to[:15]}")
            return message.to_dict()

        if self.provider == Provider.TWILIO:
            result = self._send_twilio_text(sender, to, body)
        else:
            result = self._send_meta_text(to, body)

        message.message_id = result.get("message_id", message.message_id)
        message.status = result.get("status", MessageStatus.QUEUED)
        self._message_log.append(message)

        return {**message.to_dict(), **result}

    def send_template(
        self,
        to: str,
        template_key: str,
        params: Dict[str, str],
        lang: str = "ar",
        from_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        إرسال رسالة قالب (Template Message)

        القوالب معتمدة مسبقاً من Meta لضمان جودة المحتوى.

        Args:
            to: رقم المستلم
            template_key: مفتاح القالب (greeting/ticket_created/survey_prompt/...)
            params: معاملات القالب (مثال: {"name": "أحمد"})
            lang: لغة القالب
            from_number: رقم المرسل

        Returns:
            نتيجة الإرسال
        """
        template = self.templates.get_template(template_key, lang)
        if not template:
            logger.error(f"Template '{template_key}' not found")
            return {"success": False, "error": f"Template '{template_key}' not found"}

        # ملء القالب بالقيم
        filled_body = self.templates.fill_template(template_key, params, lang)

        sender = from_number or self.whatsapp_number
        message = WhatsAppMessage(
            from_number=sender,
            to_number=to,
            body=filled_body,
            template_name=template["name"],
            template_params=[params.get(p, "") for p in template["params"]],
        )

        if self.demo_mode:
            message.status = MessageStatus.SENT
            self._message_log.append(message)
            logger.info(f"[DEMO] Template '{template_key}' sent to {to[:15]}")
            return message.to_dict()

        if self.provider == Provider.TWILIO:
            result = self._send_twilio_template(sender, to, template["name"],
                                                  template["params"], params)
        else:
            result = self._send_meta_template(to, template["name"], lang, params)

        message.message_id = result.get("message_id", message.message_id)
        message.status = result.get("status", MessageStatus.QUEUED)
        self._message_log.append(message)

        return {**message.to_dict(), **result}

    def send_interactive_buttons(
        self,
        to: str,
        body: str,
        options: List[Dict[str, str]],
        from_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        إرسال رسالة تفاعلية بأزرار (Interactive Buttons)

        Args:
            to: رقم المستلم
            body: نص الرسالة الرئيسي
            options: قائمة الخيارات [{"id": "faq", "title": "أسئلة شائعة"}, ...]
            from_number: رقم المرسل

        Returns:
            نتيجة الإرسال
        """
        sender = from_number or self.whatsapp_number
        message = WhatsAppMessage(
            from_number=sender,
            to_number=to,
            body=body,
            interactive_type="button",
            interactive_options=options,
        )

        if self.demo_mode:
            message.status = MessageStatus.SENT
            self._message_log.append(message)
            logger.info(f"[DEMO] Interactive buttons sent to {to[:15]}")
            return message.to_dict()

        if self.provider == Provider.TWILIO:
            result = self._send_twilio_interactive(sender, to, body, options)
        else:
            result = self._send_meta_interactive(to, body, options)

        message.message_id = result.get("message_id", message.message_id)
        message.status = result.get("status", MessageStatus.QUEUED)
        self._message_log.append(message)

        return {**message.to_dict(), **result}

    def send_document(
        self,
        to: str,
        document_url: str,
        filename: str = "document.pdf",
        caption: str = "",
        from_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        إرسال مستند عبر واتساب (PDF, DOCX, etc.)

        Args:
            to: رقم المستلم
            document_url: رابط المستند
            filename: اسم الملف
            caption: تعليق اختياري
            from_number: رقم المرسل
        """
        sender = from_number or self.whatsapp_number
        message = WhatsAppMessage(
            from_number=sender,
            to_number=to,
            body=caption,
            media_url=document_url,
            media_type="document",
        )

        if self.demo_mode:
            message.status = MessageStatus.SENT
            self._message_log.append(message)
            return message.to_dict()

        if self.provider == Provider.META:
            url = f"{self.META_API_BASE}/{self.phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "document",
                "document": {
                    "link": document_url,
                    "filename": filename,
                    "caption": caption,
                },
            }
            headers = {"Authorization": f"Bearer {self.access_token}"}
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                message.status = MessageStatus.SENT
            else:
                message.status = MessageStatus.FAILED

        self._message_log.append(message)
        return message.to_dict()

    # ──────────────────────────────────────────
    # Webhook Handling
    # ──────────────────────────────────────────

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """
        التحقق من webhook (GET request من Meta/Twilio)

        Meta يرسل:
            hub.mode=subscribe
            hub.verify_token=YOUR_TOKEN
            hub.challenge=RANDOM_STRING

        Returns:
            challenge string if valid, None otherwise
        """
        if mode == "subscribe" and token == self.webhook_verify_token:
            logger.info("Webhook verified successfully")
            return challenge
        logger.warning("Webhook verification failed — invalid token")
        return None

    def process_webhook_payload(self, payload: Dict[str, Any]) -> List[WebhookEvent]:
        """
        معالجة حمولة webhook واردة

        Args:
            payload: JSON payload من Meta أو Twilio

        Returns:
            قائمة بالأحداث المستخرجة
        """
        events: List[WebhookEvent] = []

        if self.provider == Provider.META:
            events = self._parse_meta_webhook(payload)
        elif self.provider == Provider.TWILIO:
            events = self._parse_twilio_webhook(payload)
        else:
            events = self._parse_meta_webhook(payload)  # default

        # Fire registered handlers
        for event in events:
            for handler in self._message_handlers:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Webhook handler error: {e}")

        return events

    def on_message(self, handler: Callable[[WebhookEvent], Any]) -> None:
        """تسجيل معالج للرسائل الواردة"""
        self._message_handlers.append(handler)

    def _parse_meta_webhook(self, payload: Dict[str, Any]) -> List[WebhookEvent]:
        """تحليل webhook من Meta Cloud API"""
        events = []
        try:
            entries = payload.get("entry", [])
            for entry in entries:
                changes = entry.get("changes", [])
                for change in changes:
                    value = change.get("value", {})

                    # Text message
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])
                    profile_name = ""
                    if contacts:
                        profile_name = contacts[0].get("profile", {}).get("name", "")

                    for msg in messages:
                        msg_type = msg.get("type", "")
                        if msg_type == "text":
                            events.append(WebhookEvent(
                                event_type="message",
                                phone_number=msg.get("from", ""),
                                message_body=msg.get("text", {}).get("body", ""),
                                message_id=msg.get("id", ""),
                                profile_name=profile_name,
                                timestamp=msg.get("timestamp", ""),
                                raw_data=msg,
                            ))

                    # Status updates
                    statuses = value.get("statuses", [])
                    for status in statuses:
                        events.append(WebhookEvent(
                            event_type=status.get("status", "unknown"),
                            phone_number=status.get("recipient_id", ""),
                            message_id=status.get("id", ""),
                            timestamp=status.get("timestamp", ""),
                            raw_data=status,
                        ))

        except Exception as e:
            logger.error(f"Error parsing Meta webhook: {e}")

        return events

    def _parse_twilio_webhook(self, payload: Dict[str, Any]) -> List[WebhookEvent]:
        """تحليل webhook من Twilio"""
        events = []
        try:
            body = payload.get("Body", "")
            from_number = payload.get("From", "")
            message_sid = payload.get("MessageSid", "")
            profile_name = payload.get("ProfileName", "")

            if body and from_number:
                events.append(WebhookEvent(
                    event_type="message",
                    phone_number=from_number.replace("whatsapp:", ""),
                    message_body=body,
                    message_id=message_sid,
                    profile_name=profile_name,
                    raw_data=payload,
                ))

        except Exception as e:
            logger.error(f"Error parsing Twilio webhook: {e}")

        return events

    # ──────────────────────────────────────────
    # Conversation Tracking
    # ──────────────────────────────────────────

    def start_conversation(
        self, phone_number: str, context: Optional[Dict] = None
    ) -> str:
        """
        بدء محادثة جديدة وتتبع حالتها

        Args:
            phone_number: رقم العميل
            context: بيانات سياقية (معرف المستخدم، المعاملة، إلخ)

        Returns:
            معرف المحادثة
        """
        conversation_id = f"CONV-{uuid.uuid4().hex[:8].upper()}"
        self._conversations[phone_number] = {
            "conversation_id": conversation_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "message_count": 0,
            "last_message_at": None,
            "context": context or {},
            "state": "active",
        }
        return conversation_id

    def get_conversation(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """استرجاع بيانات المحادثة"""
        return self._conversations.get(phone_number)

    def end_conversation(self, phone_number: str) -> bool:
        """إنهاء محادثة"""
        conv = self._conversations.get(phone_number)
        if conv:
            conv["state"] = "ended"
            return True
        return False

    # ──────────────────────────────────────────
    # Twilio Transport
    # ──────────────────────────────────────────

    def _send_twilio_text(
        self, from_number: str, to: str, body: str
    ) -> Dict[str, Any]:
        """إرسال نص عبر Twilio API"""
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = {
            "From": f"whatsapp:{from_number}",
            "To": f"whatsapp:{to}",
            "Body": body,
        }
        auth = (self.account_sid, self.auth_token)

        response = requests.post(url, data=data, auth=auth, timeout=self.timeout)

        if response.status_code in (200, 201):
            resp_json = response.json()
            return {
                "success": True,
                "message_id": resp_json.get("sid"),
                "status": MessageStatus.SENT,
                "provider": "twilio",
            }
        else:
            logger.error(f"Twilio send failed: {response.status_code} {response.text[:200]}")
            return {
                "success": False,
                "error": f"Twilio error {response.status_code}",
                "status": MessageStatus.FAILED,
                "provider": "twilio",
            }

    def _send_twilio_template(
        self,
        from_number: str,
        to: str,
        template_name: str,
        template_params: List[str],
        params: Dict[str, str],
    ) -> Dict[str, Any]:
        """إرسال قالب عبر Twilio — Content SID approach"""
        # Twilio uses Content API for templates
        # For simplicity, we send as formatted text
        body = self.templates.fill_template(
            template_name.split("_")[-1] if "_" in template_name else template_name,
            params
        )
        if not body:
            body = f"[Template: {template_name}] " + ", ".join(params.values())
        return self._send_twilio_text(from_number, to, body)

    def _send_twilio_interactive(
        self, from_number: str, to: str, body: str, options: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """إرسال أزرار تفاعلية عبر Twilio"""
        # Format as text with numbered options for Twilio
        lines = [body, ""]
        for i, opt in enumerate(options, 1):
            lines.append(f"{i}. {opt.get('title', opt.get('id', ''))}")
        formatted = "\n".join(lines)
        return self._send_twilio_text(from_number, to, formatted)

    # ──────────────────────────────────────────
    # Meta Cloud API Transport
    # ──────────────────────────────────────────

    def _send_meta_text(self, to: str, body: str) -> Dict[str, Any]:
        """إرسال نص عبر Meta Cloud API"""
        url = f"{self.META_API_BASE}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}

        response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)

        if response.status_code == 200:
            resp_json = response.json()
            return {
                "success": True,
                "message_id": resp_json.get("messages", [{}])[0].get("id"),
                "status": MessageStatus.SENT,
                "provider": "meta",
            }
        else:
            logger.error(f"Meta send failed: {response.status_code} {response.text[:200]}")
            return {
                "success": False,
                "error": f"Meta error {response.status_code}",
                "status": MessageStatus.FAILED,
                "provider": "meta",
            }

    def _send_meta_template(
        self,
        to: str,
        template_name: str,
        lang: str,
        params: Dict[str, str],
    ) -> Dict[str, Any]:
        """إرسال قالب عبر Meta Cloud API"""
        url = f"{self.META_API_BASE}/{self.phone_number_id}/messages"

        components = []
        if params:
            param_objects = [{"type": "text", "text": v} for v in params.values()]
            components.append({
                "type": "body",
                "parameters": param_objects,
            })

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "ar" if lang == "ar" else "en_US"},
                "components": components,
            },
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}

        response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)

        if response.status_code == 200:
            resp_json = response.json()
            return {
                "success": True,
                "message_id": resp_json.get("messages", [{}])[0].get("id"),
                "status": MessageStatus.SENT,
                "provider": "meta",
            }
        else:
            logger.error(
                "Meta template failed: status_code=%s, response_body_length=%s",
                response.status_code,
                len(response.text or ""),
            )
            return {
                "success": False,
                "error": f"Meta error {response.status_code}",
                "status": MessageStatus.FAILED,
                "provider": "meta",
            }

    def _send_meta_interactive(
        self, to: str, body: str, options: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """إرسال أزرار تفاعلية عبر Meta Cloud API"""
        url = f"{self.META_API_BASE}/{self.phone_number_id}/messages"

        # Meta allows max 3 buttons
        buttons = []
        for opt in options[:3]:
            buttons.append({
                "type": "reply",
                "reply": {
                    "id": opt.get("id", ""),
                    "title": opt.get("title", ""),
                },
            })

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {"buttons": buttons},
            },
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}

        response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)

        if response.status_code == 200:
            resp_json = response.json()
            return {
                "success": True,
                "message_id": resp_json.get("messages", [{}])[0].get("id"),
                "status": MessageStatus.SENT,
                "provider": "meta",
            }
        else:
            return {
                "success": False,
                "error": f"Meta error {response.status_code}",
                "status": MessageStatus.FAILED,
                "provider": "meta",
            }

    # ──────────────────────────────────────────
    # Message Log & Metrics
    # ──────────────────────────────────────────

    def get_message_history(
        self,
        phone_number: Optional[str] = None,
        direction: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """استرجاع سجل الرسائل"""
        messages = self._message_log
        if phone_number:
            messages = [
                m for m in messages
                if phone_number in (m.from_number, m.to_number)
            ]
        if direction:
            messages = [m for m in messages if m.direction == direction]

        return [m.to_dict() for m in messages[-limit:]]

    def get_metrics(self) -> Dict[str, Any]:
        """مقاييس المراسلة"""
        total = len(self._message_log)
        sent = sum(1 for m in self._message_log if m.direction == MessageDirection.OUTBOUND)
        received = sum(1 for m in self._message_log if m.direction == MessageDirection.INBOUND)
        failed = sum(1 for m in self._message_log if m.status == MessageStatus.FAILED)

        return {
            "total_messages": total,
            "sent": sent,
            "received": received,
            "failed": failed,
            "active_conversations": sum(
                1 for c in self._conversations.values() if c["state"] == "active"
            ),
        }