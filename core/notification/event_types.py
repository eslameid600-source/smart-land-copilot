"""
Event Types for Notification System
=====================================
Defines event registry, delivery channels, and message formatting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class DeliveryChannel(str, Enum):
    """قنوات توصيل الإشعارات."""
    PUSH = "push"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    IN_APP = "in_app"
    SMS = "sms"


@dataclass
class EventType:
    """نوع الحدث — تعريف كامل للحدث."""
    key: str
    title_ar: str
    body_template_ar: str
    priority: int = 0  # 0=عادي, 1=مهم, 2=عاجل
    supported_channels: List[DeliveryChannel] = field(default_factory=lambda: [
        DeliveryChannel.PUSH,
        DeliveryChannel.EMAIL,
        DeliveryChannel.WHATSAPP,
        DeliveryChannel.IN_APP,
    ])
    throttle_per_hour: int = 0  # صفر = بدون تحديد


# ─── سجل الأحداث ───

EVENT_REGISTRY: Dict[str, EventType] = {
    "auction_outbid": EventType(
        key="auction_outbid",
        title_ar="تم تجاوز مزايدتك",
        body_template_ar="تم تجاوز مزايدتك على {land_name} ({land_id}) بمبلغ {new_bid} ج.م — المزاد ينتهي {auction_end}",
        priority=2,
        supported_channels=[DeliveryChannel.PUSH, DeliveryChannel.EMAIL, DeliveryChannel.WHATSAPP, DeliveryChannel.IN_APP],
        throttle_per_hour=5,
    ),
    "auction_winner": EventType(
        key="auction_winner",
        title_ar="تهانينا! فزت بالمزاد",
        body_template_ar="لقد فزت في مزاد {land_name} ({land_id}) بمبلغ {winning_bid} ج.م",
        priority=2,
    ),
    "auction_loser": EventType(
        key="auction_loser",
        title_ar="لم تفز بالمزاد",
        body_template_ar="لم تفز في مزاد {land_name} ({land_id}) — عرضك النهائي: {final_bid} ج.م",
        priority=1,
    ),
    "auction_starting": EventType(
        key="auction_starting",
        title_ar="مزاد جديد يبدأ قريباً",
        body_template_ar="مزاد {land_name} في {governorate} (نشاط: {activity}) يبدأ بسعر {starting_bid} ج.م/م²",
        priority=1,
    ),
    "land_match": EventType(
        key="land_match",
        title_ar="تم العثور على أرض مطابقة",
        body_template_ar="تم العثور على {land_name} في {governorate} — {area_sqm} م² بسعر {price_per_sqm} ج.م/م² — نسبة التطابق: {score}%",
        priority=0,
    ),
    "price_prediction": EventType(
        key="price_prediction",
        title_ar="توقعات الأسعار متاحة",
        body_template_ar="توقع سعر {land_name}: من {current_price} إلى {predicted_price} ج.م/م² خلال {years} سنوات (نمو {appreciation_pct}%)",
        priority=0,
        supported_channels=[DeliveryChannel.EMAIL, DeliveryChannel.IN_APP],
    ),
    "wallet_deposit": EventType(
        key="wallet_deposit",
        title_ar="تم إيداع المبلغ في المحفظة",
        body_template_ar="تم إيداع {amount} ج.م في محفظتك — الرصيد الجديد: {new_balance} ج.م",
        priority=1,
    ),
    "transaction_complete": EventType(
        key="transaction_complete",
        title_ar="اكتملت المعاملة",
        body_template_ar="اكتملت معاملة شراء {land_name} ({land_id}) بمبلغ {amount} ج.م — رقم المعاملة: {tx_id}",
        priority=2,
    ),
    "survey_reminder": EventType(
        key="survey_reminder",
        title_ar="تذكير باستبيان",
        body_template_ar="ندعوك لتقييم تجربتك مع {service_name}",
        priority=0,
        throttle_per_hour=1,
    ),
}


def get_event_type(event_key: str) -> Optional[EventType]:
    """الحصول على تعريف نوع الحدث."""
    return EVENT_REGISTRY.get(event_key)


def format_message(event_type: EventType, payload: Dict[str, object]) -> str:
    """تنسيق رسالة الحدث باستخدام القالب والبيانات."""
    missing_keys = []
    try:
        return event_type.body_template_ar.format(**payload)
    except KeyError as e:
        missing_keys.append(str(e))
    return f"{event_type.body_template_ar} (تنسيق غير مكتمل — مفاتيح ناقصة: {', '.join(missing_keys)})"