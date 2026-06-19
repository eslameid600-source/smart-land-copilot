"""
أنواع أحداث الإشعارات — Notification Event Types
===================================================
تعريف كل نوع حدث وعنوانه الافتراضي وقوالب الرسائل.
كل حدث يُرسل عبر القنوات المفعلة في تفضيلات المستخدم.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ══════════════════════════════════════════════
# 1. قنوات الإرسال
# ══════════════════════════════════════════════

class DeliveryChannel(str, Enum):
    """قنوات إرسال الإشعارات."""
    PUSH = "push"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    IN_APP = "in_app"


# ══════════════════════════════════════════════
# 2. تعريف نوع الحدث
# ══════════════════════════════════════════════

@dataclass(frozen=True)
class EventType:
    """تعريف نوع حدث إشعار واحد."""

    type_key: str
    """مفتاح الحدث — يُستخدم في الكود (مثل: auction_outbid)."""

    title_ar: str
    """العنوان الافتراضي بالعربية."""

    body_template_ar: str
    """قالب نص الرسالة بالعربية — يستخدم .format(**payload)."""

    whatsapp_template: str
    """اسم قالب WhatsApp Business (إن وُجد)."""

    supported_channels: tuple[DeliveryChannel, ...] = (
        DeliveryChannel.PUSH,
        DeliveryChannel.WHATSAPP,
        DeliveryChannel.EMAIL,
        DeliveryChannel.IN_APP,
    )
    """القنوات الافتراضية المدعومة لهذا الحدث."""

    priority: int = 0
    """الأولوية — 0=عادي، 1=مهم، 2=عاجل. يُستخدم في الترتيب والتصفية."""


# ══════════════════════════════════════════════
# 3. سجل أنواع الأحداث
# ══════════════════════════════════════════════

EVENT_REGISTRY: dict[str, EventType] = {
    # ── المزادات ──
    "auction_outbid": EventType(
        type_key="auction_outbid",
        title_ar="تم تجاوز مزايدتك",
        body_template_ar=(
            "تم تجاوز مزايدتك على أرض {land_name} (المزاد {land_id}). "
            "المزايدة الجديدة: {new_bid:,.0f} جنيه. "
            "المزاد ينتهي في: {auction_end}."
        ),
        whatsapp_template="auction_outbid",
        priority=2,
    ),
    "auction_winner": EventType(
        type_key="auction_winner",
        title_ar="تهانينا! فزت بالمزاد",
        body_template_ar=(
            "فزت بمزاد أرض {land_name} (المزاد {land_id}) "
            "بمبلغ {winning_bid:,.0f} جنيه. "
            "يرجى إتمام عملية الدفع خلال 48 ساعة."
        ),
        whatsapp_template="auction_winner",
        priority=2,
    ),
    "auction_loser": EventType(
        type_key="auction_loser",
        title_ar="انتهى المزاد",
        body_template_ar=(
            "لم تفز بمزاد أرض {land_name} (المزاد {land_id}). "
            "المزاد انتهى بمبلغ {final_bid:,.0f} جنيه."
        ),
        whatsapp_template="auction_ended",
        priority=0,
    ),
    "auction_starting": EventType(
        type_key="auction_starting",
        title_ar="مزاد جديد يطابق معاييرك",
        body_template_ar=(
            "بدأ مزاد جديد لأرض {land_name} في {governorate} "
            "النشاط: {activity}، السعر الأولي: {starting_bid:,.0f} جنيه/م²."
        ),
        whatsapp_template="new_auction_alert",
        supported_channels=(
            DeliveryChannel.PUSH,
            DeliveryChannel.EMAIL,
            DeliveryChannel.IN_APP,
        ),
        priority=1,
    ),

    # ── المطابقة الذكية ──
    "land_match": EventType(
        type_key="land_match",
        title_ar="أرض جديدة تطابق معاييرك",
        body_template_ar=(
            "أرض {land_name} في {governorate} — "
            "المساحة: {area_sqm:,.0f} م²، "
            "السعر: {price_per_sqm:,.0f} جنيه/م²، "
            "نسبة التوافق: {score}%."
        ),
        whatsapp_template="land_match_alert",
        supported_channels=(
            DeliveryChannel.PUSH,
            DeliveryChannel.EMAIL,
            DeliveryChannel.IN_APP,
        ),
        priority=1,
    ),

    # ── التنبؤات ──
    "price_prediction": EventType(
        type_key="price_prediction",
        title_ar="تحديث توقعات الأسعار",
        body_template_ar=(
            "تم تحديث توقعات أسعار أرض {land_name}: "
            "السعر الحالي: {current_price:,.0f} جنيه/م²، "
            "المتوقع بعد {years} سنوات: {predicted_price:,.0f} جنيه/م² "
            "(+{appreciation_pct}%)."
        ),
        whatsapp_template="price_update",
        supported_channels=(
            DeliveryChannel.EMAIL,
            DeliveryChannel.IN_APP,
        ),
        priority=0,
    ),

    # ── المحفظة والمعاملات ──
    "wallet_deposit": EventType(
        type_key="wallet_deposit",
        title_ar="تأكيد إيداع",
        body_template_ar=(
            "تم إيداع {amount:,.0f} جنيه في محفظتك بنجاح. "
            "الرصيد الجديد: {new_balance:,.0f} جنيه."
        ),
        whatsapp_template="payment_confirmation",
        priority=1,
    ),
    "transaction_complete": EventType(
        type_key="transaction_complete",
        title_ar="اكتملت المعاملة",
        body_template_ar=(
            "اكتملت معاملة شراء أرض {land_name} ({land_id}) "
            "بمبلغ {amount:,.0f} جنيه. "
            "رقم المعاملة: {tx_id}."
        ),
        whatsapp_template="transaction_complete",
        priority=2,
    ),

    # ── خدمة العملاء ──
    "survey_reminder": EventType(
        type_key="survey_reminder",
        title_ar="رأيك يهمنا",
        body_template_ar=(
            "نأمل تقييم تجربتك مع خدمة {service_name}. "
            "استغرق دقيقة واحدة لمساعدتنا في التحسين!"
        ),
        whatsapp_template="survey_reminder",
        supported_channels=(
            DeliveryChannel.EMAIL,
            DeliveryChannel.IN_APP,
        ),
        priority=0,
    ),
}


def get_event_type(type_key: str) -> Optional[EventType]:
    """إرجاع تعريف الحدث أو None إذا لم يُعثر عليه."""
    return EVENT_REGISTRY.get(type_key)


def format_message(event_type: EventType, payload: dict) -> str:
    """
    تنسيق رسالة الإشعار باستخدام قالب الحدث وبيانات الحمولة.
    يدعم الاستبدال الجزئي — يُبدّل المتوفر ويُشير للناقص.
    """
    try:
        return event_type.body_template_ar.format(**payload)
    except KeyError as e:
        # استبدال جزئي: نُبدّل المتوفر ونترك الناقص كـ نص عادي
        template = event_type.body_template_ar
        import re

        # نلتقط كل المتغيرات مع format specs: {var_name:format}
        all_placeholders = re.findall(r'\{(\w+)(?::[^}]*)?\}', template)
        available_keys = set(payload.keys())
        missing = set(all_placeholders) - available_keys

        # نستبدل المتوفر فقط — نحذف format spec للناقص
        for key in missing:
            # إزالة format spec من المتغير الناقص
            template = re.sub(
                r'\{' + re.escape(key) + r'(?::[^}]*)?\}',
                f'[{key}]',
                template,
            )

        try:
            result = template.format(**payload)
        except Exception:
            result = template

        if missing:
            result += f" [مفاتيح ناقصة: {', '.join(missing)}]"
        return result
    except ValueError as e:
        return f"{event_type.body_template_ar} [خطأ في التنسيق: {e}]"