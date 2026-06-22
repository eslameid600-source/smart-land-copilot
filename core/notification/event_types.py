"""
core.notification.event_types
==============================
سجل أنواع أحداث الإشعارات + قوالب الرسائل العربية.

كل حدث له:
    - key: معرّف فريد (str)
    - title_ar: عنوان عربي
    - body_template_ar: قالب النص (يُنسَّق من payload)
    - priority: 0=عادي، 1=هام، 2=عاجل
    - supported_channels: القنوات المسموحة لهذا الحدث
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


# ──────────────────────────────────────────────
# قنوات التوصيل
# ──────────────────────────────────────────────

class DeliveryChannel(str, Enum):
    """قنوات توصيل الإشعارات."""
    PUSH = "push"           # FCM / mobile push
    WHATSAPP = "whatsapp"   # Twilio / Meta Cloud API
    EMAIL = "email"         # SMTP / SendGrid
    IN_APP = "in_app"       # إشعار داخل التطبيق (DB-stored)
    SMS = "sms"             # رسالة SMS


# ──────────────────────────────────────────────
# نموذج نوع الحدث
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class EventType:
    """تعريف نوع حدث إشعار واحد."""
    key: str
    title_ar: str
    body_template_ar: str
    priority: int = 0                                   # 0=عادي، 1=هام، 2=عاجل
    supported_channels: tuple = (DeliveryChannel.PUSH,
                                 DeliveryChannel.IN_APP,
                                 DeliveryChannel.EMAIL,
                                 DeliveryChannel.WHATSAPP)
    required_payload_keys: tuple = ()                   # مفاتيح يجب توفرها في الـ payload

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title_ar": self.title_ar,
            "body_template_ar": self.body_template_ar,
            "priority": self.priority,
            "supported_channels": [c.value for c in self.supported_channels],
            "required_payload_keys": list(self.required_payload_keys),
        }


# ──────────────────────────────────────────────
# سجل الأحداث
# ──────────────────────────────────────────────

EVENT_REGISTRY: Dict[str, EventType] = {
    "auction_outbid": EventType(
        key="auction_outbid",
        title_ar="تم تجاوز مزايدتك",
        body_template_ar=(
            "تم تجاوز مزايدتك على {land_name} ({land_id}) "
            "بمبلغ {new_bid:,.0f} ج.م. ينتهي المزاد في {auction_end}."
        ),
        priority=2,  # عاجل
        supported_channels=(DeliveryChannel.PUSH, DeliveryChannel.IN_APP,
                             DeliveryChannel.EMAIL, DeliveryChannel.WHATSAPP),
        required_payload_keys=("land_name", "land_id", "new_bid", "auction_end"),
    ),
    "auction_winner": EventType(
        key="auction_winner",
        title_ar="تهانينا! لقد فزت بالمزاد",
        body_template_ar=(
            "فزت بمزاد {land_name} ({land_id}) بمبلغ {winning_bid:,.0f} ج.م. "
            "سنتواصل معك قريباً لإتمام الإجراءات."
        ),
        priority=2,
        supported_channels=(DeliveryChannel.PUSH, DeliveryChannel.IN_APP,
                             DeliveryChannel.EMAIL, DeliveryChannel.WHATSAPP),
        required_payload_keys=("land_name", "land_id", "winning_bid"),
    ),
    "auction_loser": EventType(
        key="auction_loser",
        title_ar="انتهى المزاد",
        body_template_ar=(
            "انتهى مزاد {land_name} ({land_id}) بمبلغ نهائي {final_bid:,.0f} ج.م. "
            "لم تكن المزايد الأعلى."
        ),
        priority=1,
        supported_channels=(DeliveryChannel.IN_APP, DeliveryChannel.EMAIL),
        required_payload_keys=("land_name", "land_id", "final_bid"),
    ),
    "auction_starting": EventType(
        key="auction_starting",
        title_ar="مزاد على وشك البدء",
        body_template_ar=(
            "مزاد جديد على {land_name} في {governorate} ({activity}) "
            "بسعر ابتدائي {starting_bid:,.0f} ج.م/م² سيبدأ قريباً."
        ),
        priority=1,
        supported_channels=(DeliveryChannel.PUSH, DeliveryChannel.IN_APP,
                             DeliveryChannel.EMAIL),
        required_payload_keys=("land_name", "governorate", "activity", "starting_bid"),
    ),
    "land_match": EventType(
        key="land_match",
        title_ar="أرض جديدة تطابق معاييرك",
        body_template_ar=(
            "وجدنا أرضاً تطابق تفضيلاتك: {land_name} في {governorate}، "
            "المساحة {area_sqm:,.0f} م² بسعر {price_per_sqm:,.0f} ج.م/م² "
            "(درجة التطابق: {score}%)."
        ),
        priority=1,
        supported_channels=(DeliveryChannel.PUSH, DeliveryChannel.IN_APP,
                             DeliveryChannel.EMAIL),
        required_payload_keys=("land_name", "governorate", "area_sqm",
                               "price_per_sqm", "score"),
    ),
    "price_prediction": EventType(
        key="price_prediction",
        title_ar="تنبؤ بسعر الأرض",
        body_template_ar=(
            "{land_name}: السعر الحالي {current_price:,.0f} ج.م/م²، "
            "المتوقع بعد {years} سنوات: {predicted_price:,.0f} ج.م/م² "
            "(نمو {appreciation_pct}%)."
        ),
        priority=0,  # عادي
        supported_channels=(DeliveryChannel.EMAIL, DeliveryChannel.IN_APP),  # لا Push ولا WhatsApp
        required_payload_keys=("land_name", "current_price", "predicted_price",
                               "years", "appreciation_pct"),
    ),
    "wallet_deposit": EventType(
        key="wallet_deposit",
        title_ar="تم إيداع مبلغ في محفظتك",
        body_template_ar=(
            "تم إيداع {amount:,.0f} ج.م في محفظتك. رصيدك الجديد: {new_balance:,.0f} ج.م."
        ),
        priority=1,
        supported_channels=(DeliveryChannel.PUSH, DeliveryChannel.IN_APP,
                             DeliveryChannel.EMAIL),
        required_payload_keys=("amount", "new_balance"),
    ),
    "transaction_complete": EventType(
        key="transaction_complete",
        title_ar="تمت المعاملة بنجاح",
        body_template_ar=(
            "تمت معاملة شراء {land_name} ({land_id}) بمبلغ {amount:,.0f} ج.م "
            "(رقم المعاملة: {tx_id})."
        ),
        priority=2,
        supported_channels=(DeliveryChannel.PUSH, DeliveryChannel.IN_APP,
                             DeliveryChannel.EMAIL, DeliveryChannel.WHATSAPP),
        required_payload_keys=("land_name", "land_id", "amount", "tx_id"),
    ),
    "survey_reminder": EventType(
        key="survey_reminder",
        title_ar="تذكير: استبيان جديد",
        body_template_ar=(
            "لديك استبيان جديد عن {service_name}. شارك برأيك واحصل على نقاط ولاء إضافية."
        ),
        priority=0,  # عادي
        supported_channels=(DeliveryChannel.IN_APP, DeliveryChannel.EMAIL),
        required_payload_keys=("service_name",),
    ),
}


# ──────────────────────────────────────────────
# دوال مساعدة
# ──────────────────────────────────────────────

def get_event_type(key: str) -> Optional[EventType]:
    """يسترجع EventType عبر مفتاحه. يُرجع None لو غير موجود."""
    return EVENT_REGISTRY.get(key)


def format_message(evt: EventType, payload: dict) -> str:
    """ينسّق رسالة الحدث من القالب + payload.

    لو نقصت مفاتيح مطلوبة، يُرجع نص تنبيه بدلاً من رفع استثناء.
    """
    if not evt:
        return ""
    missing = [k for k in evt.required_payload_keys if k not in payload]
    if missing:
        return f"تنسيق غير مكتمل — مفاتيح ناقصة: {', '.join(missing)}"
    try:
        return evt.body_template_ar.format(**payload)
    except (KeyError, ValueError, IndexError):
        # في حالة فشل التنسيق رغم وجود المفاتيح
        return f"تنسيق غير مكتمل — تعذّر بناء الرسالة من {evt.key}"


__all__ = [
    "DeliveryChannel",
    "EventType",
    "EVENT_REGISTRY",
    "get_event_type",
    "format_message",
]
