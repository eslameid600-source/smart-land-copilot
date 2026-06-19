"""
Customer Satisfaction Survey Service
=====================================
نظام استبيانات رضا العملاء — CSAT + NPS

Core function:
    survey_user(transaction_id, rating) → records + analyzes satisfaction

Features:
    - CSAT (Customer Satisfaction Score): 1-5 stars per transaction
    - NPS (Net Promoter Score): 0-10 likelihood to recommend
    - CES (Customer Effort Score): 1-7 ease of interaction
    - Open-ended feedback with optional comment
    - Automated survey triggers (post-transaction, post-ticket)
    - Aggregated analytics per period / channel / agent
    - Trend tracking over time
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────

class SurveyType:
    """أنواع الاستبيانات"""
    CSAT = "csat"          # رضا العميل (1-5)
    NPS = "nps"            # احتمالية التوصية (0-10)
    CES = "ces"            # مجهود العميل (1-7)
    POST_TICKET = "post_ticket"     # بعد حل التذكرة
    POST_TRANSACTION = "post_transaction"  # بعد المعاملة


class SurveyRecord:
    """سجل استبيان واحد"""

    def __init__(
        self,
        transaction_id: str,
        rating: int,
        survey_type: str = SurveyType.CSAT,
        user_id: str = "",
        user_email: str = "",
        comment: str = "",
        channel: str = "",         # web, whatsapp, email
        agent_id: str = "",        # وكيل الدعم (إن وجد)
        ticket_id: str = "",       # معرف التذكرة (إن وجد)
        metadata: Optional[Dict[str, Any]] = None,
        survey_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        self.survey_id = survey_id or f"SVY-{uuid.uuid4().hex[:8].upper()}"
        self.transaction_id = transaction_id
        self.rating = rating
        self.survey_type = survey_type
        self.user_id = user_id
        self.user_email = user_email
        self.comment = comment
        self.channel = channel
        self.agent_id = agent_id
        self.ticket_id = ticket_id
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "survey_id": self.survey_id,
            "transaction_id": self.transaction_id,
            "rating": self.rating,
            "survey_type": self.survey_type,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "comment": self.comment,
            "channel": self.channel,
            "agent_id": self.agent_id,
            "ticket_id": self.ticket_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class SurveyInvitation:
    """دعوة استبيان — تُرسل للعميل"""

    def __init__(
        self,
        invitation_id: str,
        transaction_id: str,
        survey_type: str,
        channel: str,
        recipient: str,
        sent_at: str,
        status: str = "pending",  # pending, responded, expired
        response: Optional[Dict[str, Any]] = None,
    ):
        self.invitation_id = invitation_id
        self.transaction_id = transaction_id
        self.survey_type = survey_type
        self.channel = channel
        self.recipient = recipient
        self.sent_at = sent_at
        self.status = status
        self.response = response

    def to_dict(self) -> Dict[str, Any]:
        return {
            "invitation_id": self.invitation_id,
            "transaction_id": self.transaction_id,
            "survey_type": self.survey_type,
            "channel": self.channel,
            "recipient": self.recipient,
            "sent_at": self.sent_at,
            "status": self.status,
            "response": self.response,
        }


# ──────────────────────────────────────────────
# Survey Service
# ──────────────────────────────────────────────

class SurveyService:
    """
    خدمة استبيانات رضا العملاء

    Usage:
        survey = SurveyService()

        # Core function — record a rating
        result = survey.survey_user("TXN-12345", rating=4, comment="خدمة جيدة")
        print(result)

        # NPS survey
        result = survey.survey_user("TXN-12345", rating=9, survey_type="nps")

        # Get analytics
        stats = survey.get_csat_stats()
        nps = survey.get_nps_score()
        agent_stats = survey.get_agent_performance()
    """

    # التحقق من صحة التقييم حسب النوع
    RATING_RANGES = {
        SurveyType.CSAT: (1, 5),
        SurveyType.NPS: (0, 10),
        SurveyType.CES: (1, 7),
    }

    # تصنيف NPS
    NPS_PROMOTERS = range(9, 11)     # 9-10 → داعم
    NPS_PASSIVES = range(7, 9)       # 7-8 → محايد
    NPS_DETRACTORS = range(0, 7)     # 0-6 → ناقد

    # تصنيف CSAT
    CSAT_LABELS = {
        1: "سيء جداً",
        2: "سيء",
        3: "مقبول",
        4: "جيد",
        5: "ممتاز",
    }

    def __init__(self):
        """تهيئة خدمة الاستبيانات"""
        self._surveys: Dict[str, SurveyRecord] = {}          # survey_id → record
        self._invitations: Dict[str, SurveyInvitation] = {}   # invitation_id → invitation
        self._transaction_surveys: Dict[str, List[str]] = {} # transaction_id → [survey_ids]

        logger.info("SurveyService initialized")

    # ──────────────────────────────────────────
    # Core Function
    # ──────────────────────────────────────────

    def survey_user(
        self,
        transaction_id: str,
        rating: int,
        survey_type: str = SurveyType.CSAT,
        user_id: str = "",
        user_email: str = "",
        comment: str = "",
        channel: str = "",
        agent_id: str = "",
        ticket_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        تسجيل تقييم رضا العميل — الدالة الرئيسية المطلوبة

        Args:
            transaction_id: معرف المعاملة (مطلوب)
            rating: التقييم (CSAT: 1-5, NPS: 0-10, CES: 1-7)
            survey_type: نوع الاستبيان (csat/nps/ces)
            user_id: معرف المستخدم
            user_email: بريد المستخدم
            comment: تعليق نصي اختياري
            channel: القناة (web/whatsapp/email)
            agent_id: معرف وكيل الدعم
            ticket_id: معرف التذكرة
            metadata: بيانات إضافية

        Returns:
            {
                "success": True/False,
                "survey_id": "SVY-XXXXX",
                "transaction_id": "...",
                "rating": 4,
                "label": "جيد",
                "survey_type": "csat",
                "message": "...",
            }
        """
        # Validate rating
        valid_range = self.RATING_RANGES.get(survey_type, (1, 5))
        if not (valid_range[0] <= rating <= valid_range[1]):
            return {
                "success": False,
                "transaction_id": transaction_id,
                "survey_type": survey_type,
                "rating": rating,
                "message": (
                    f"تقييم غير صالح: يجب أن يكون بين {valid_range[0]} و {valid_range[1]} "
                    f"لنوع الاستبيان '{survey_type}'"
                ),
            }

        # Create survey record
        record = SurveyRecord(
            transaction_id=transaction_id,
            rating=rating,
            survey_type=survey_type,
            user_id=user_id,
            user_email=user_email,
            comment=comment,
            channel=channel,
            agent_id=agent_id,
            ticket_id=ticket_id,
            metadata=metadata,
        )

        # Store
        self._surveys[record.survey_id] = record
        self._transaction_surveys.setdefault(transaction_id, []).append(record.survey_id)

        # Update invitation status if exists
        self._mark_invitation_responded(transaction_id, survey_type)

        # Generate label
        label = self._get_rating_label(rating, survey_type)

        logger.info(
            f"Survey recorded | id={record.survey_id} | "
            f"txn={transaction_id} | rating={rating} | type={survey_type}"
        )

        return {
            "success": True,
            "survey_id": record.survey_id,
            "transaction_id": transaction_id,
            "rating": rating,
            "label": label,
            "survey_type": survey_type,
            "message": f"تم تسجيل تقييمك ({label}) بنجاح. شكراً لمشاركتك رأيك!",
        }

    # ──────────────────────────────────────────
    # Survey Invitations
    # ──────────────────────────────────────────

    def create_invitation(
        self,
        transaction_id: str,
        survey_type: str = SurveyType.CSAT,
        channel: str = "web",
        recipient: str = "",
    ) -> Dict[str, Any]:
        """
        إنشاء دعوة استبيان (لإرسالها عبر واتساب/بريد/إلخ)

        Args:
            transaction_id: معرف المعاملة
            survey_type: نوع الاستبيان
            channel: قناة الإرسال
            recipient: رقم الهاتف أو البريد الإلكتروني

        Returns:
            بيانات الدعوة
        """
        invitation_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
        invitation = SurveyInvitation(
            invitation_id=invitation_id,
            transaction_id=transaction_id,
            survey_type=survey_type,
            channel=channel,
            recipient=recipient,
            sent_at=datetime.now(timezone.utc).isoformat(),
        )
        self._invitations[invitation_id] = invitation

        return invitation.to_dict()

    def _mark_invitation_responded(
        self, transaction_id: str, survey_type: str
    ) -> None:
        """تحديث حالة الدعوة بعد الاستجابة"""
        for inv in self._invitations.values():
            if (inv.transaction_id == transaction_id
                    and inv.survey_type == survey_type
                    and inv.status == "pending"):
                inv.status = "responded"
                break

    # ──────────────────────────────────────────
    # CSAT Analytics
    # ──────────────────────────────────────────

    def get_csat_stats(
        self,
        days: int = 30,
        channel: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        إحصائيات CSAT (Customer Satisfaction Score)

        Args:
            days: عدد الأيام الأخيرة
            channel: فلتر القناة
            agent_id: فلتر الوكيل

        Returns:
            {
                "avg_score": 4.2,
                "total_responses": 150,
                "distribution": {"1": 5, "2": 10, "3": 25, "4": 60, "5": 50},
                "satisfaction_rate": 73.3,  # % of 4+ ratings
                ...
            }
        """
        records = self._filter_surveys(
            survey_type=SurveyType.CSAT, days=days, channel=channel, agent_id=agent_id
        )

        if not records:
            return {
                "survey_type": "csat",
                "avg_score": 0,
                "total_responses": 0,
                "distribution": {},
                "satisfaction_rate": 0,
                "period_days": days,
            }

        ratings = [r.rating for r in records]
        distribution: Dict[str, int] = {}
        for r in range(1, 6):
            distribution[str(r)] = ratings.count(r)

        satisfied = sum(1 for r in ratings if r >= 4)
        satisfaction_rate = (satisfied / len(ratings)) * 100

        return {
            "survey_type": "csat",
            "avg_score": round(sum(ratings) / len(ratings), 2),
            "total_responses": len(ratings),
            "distribution": distribution,
            "satisfaction_rate": round(satisfaction_rate, 2),
            "period_days": days,
            "channel_filter": channel,
            "agent_filter": agent_id,
        }

    # ──────────────────────────────────────────
    # NPS Analytics
    # ──────────────────────────────────────────

    def get_nps_score(
        self,
        days: int = 90,
        channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        حساب NPS (Net Promoter Score)

        NPS = %Promoters - %Detractors
        Range: -100 to +100

        Returns:
            {
                "nps_score": 42,
                "promoters_pct": 55,
                "passives_pct": 25,
                "detractors_pct": 20,
                "total_responses": 200,
                ...
            }
        """
        records = self._filter_surveys(
            survey_type=SurveyType.NPS, days=days, channel=channel
        )

        if not records:
            return {
                "survey_type": "nps",
                "nps_score": 0,
                "promoters_pct": 0,
                "passives_pct": 0,
                "detractors_pct": 0,
                "total_responses": 0,
                "period_days": days,
            }

        ratings = [r.rating for r in records]
        total = len(ratings)

        promoters = sum(1 for r in ratings if r in self.NPS_PROMOTERS)
        passives = sum(1 for r in ratings if r in self.NPS_PASSIVES)
        detractors = sum(1 for r in ratings if r in self.NPS_DETRACTORS)

        promoters_pct = (promoters / total) * 100
        detractors_pct = (detractors / total) * 100
        passives_pct = (passives / total) * 100
        nps_score = round(promoters_pct - detractors_pct)

        return {
            "survey_type": "nps",
            "nps_score": nps_score,
            "nps_label": self._nps_label(nps_score),
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
            "promoters_pct": round(promoters_pct, 2),
            "passives_pct": round(passives_pct, 2),
            "detractors_pct": round(detractors_pct, 2),
            "total_responses": total,
            "period_days": days,
        }

    # ──────────────────────────────────────────
    # Agent Performance
    # ──────────────────────────────────────────

    def get_agent_performance(
        self, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        أداء وكلاء الدعم بناءً على تقييمات العملاء

        Returns:
            [
                {
                    "agent_id": "agent_001",
                    "avg_rating": 4.5,
                    "total_surveys": 30,
                    "satisfaction_rate": 83.3,
                    "nps_score": 45,
                },
                ...
            ]
        """
        records = self._filter_surveys(days=days)
        agent_map: Dict[str, List[SurveyRecord]] = {}

        for r in records:
            if r.agent_id:
                agent_map.setdefault(r.agent_id, []).append(r)

        results = []
        for agent_id, agent_records in agent_map.items():
            csat_records = [r for r in agent_records if r.survey_type == SurveyType.CSAT]
            nps_records = [r for r in agent_records if r.survey_type == SurveyType.NPS]

            avg_rating = 0
            satisfaction_rate = 0

            if csat_records:
                ratings = [r.rating for r in csat_records]
                avg_rating = round(sum(ratings) / len(ratings), 2)
                satisfaction_rate = round(
                    (sum(1 for r in ratings if r >= 4) / len(ratings)) * 100, 2
                )

            nps_score = 0
            if nps_records:
                nps_data = self._compute_nps_from_records(nps_records)
                nps_score = nps_data["nps_score"]

            results.append({
                "agent_id": agent_id,
                "avg_rating": avg_rating,
                "total_surveys": len(agent_records),
                "csat_count": len(csat_records),
                "nps_count": len(nps_records),
                "satisfaction_rate": satisfaction_rate,
                "nps_score": nps_score,
            })

        # Sort by avg_rating descending
        results.sort(key=lambda x: x["avg_rating"], reverse=True)
        return results

    # ──────────────────────────────────────────
    # Transaction Feedback
    # ──────────────────────────────────────────

    def get_transaction_feedback(
        self, transaction_id: str
    ) -> List[Dict[str, Any]]:
        """استرجاع جميع تقييمات معاملة معينة"""
        survey_ids = self._transaction_surveys.get(transaction_id, [])
        return [self._surveys[sid].to_dict() for sid in survey_ids if sid in self._surveys]

    def get_negative_feedback(
        self,
        days: int = 7,
        min_rating: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        استخراج التقييمات السلبية الأخيرة — مفيد للمتابعة الفورية

        Args:
            days: عدد الأيام الأخيرة
            min_rating: أقصى تقييم يُعتبر سلبي (2 أو أقل)

        Returns:
            قائمة بالتقييمات السلبية
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        negative = []

        for record in self._surveys.values():
            if record.timestamp and datetime.fromisoformat(record.timestamp) >= cutoff:
                if (record.survey_type == SurveyType.CSAT
                        and record.rating <= min_rating):
                    negative.append(record.to_dict())
                elif (record.survey_type == SurveyType.NPS
                      and record.rating <= 6):
                    negative.append(record.to_dict())

        # Sort by time (most recent first)
        negative.sort(key=lambda x: x["timestamp"], reverse=True)
        return negative

    # ──────────────────────────────────────────
    # Trend Analytics
    # ──────────────────────────────────────────

    def get_rating_trend(
        self, days: int = 30, granularity: str = "daily"
    ) -> List[Dict[str, Any]]:
        """
        اتجاه التقييمات خلال فترة زمنية

        Args:
            days: عدد الأيام
            granularity: مستوى التفصيل (daily/weekly)

        Returns:
            [
                {"period": "2025-01-15", "avg_rating": 4.2, "count": 10},
                ...
            ]
        """
        records = self._filter_surveys(
            survey_type=SurveyType.CSAT, days=days
        )

        if not records:
            return []

        # Group by period
        period_map: Dict[str, List[int]] = {}

        for record in records:
            if not record.timestamp:
                continue
            dt = datetime.fromisoformat(record.timestamp)

            if granularity == "weekly":
                # ISO week: year-week
                period_key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
            else:
                period_key = dt.strftime("%Y-%m-%d")

            period_map.setdefault(period_key, []).append(record.rating)

        # Compute averages
        trend = []
        for period, ratings in sorted(period_map.items()):
            trend.append({
                "period": period,
                "avg_rating": round(sum(ratings) / len(ratings), 2),
                "count": len(ratings),
                "min": min(ratings),
                "max": max(ratings),
            })

        return trend

    # ──────────────────────────────────────────
    # Dashboard Summary
    # ──────────────────────────────────────────

    def get_dashboard_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        ملخص شامل لخدمة العملاء — يُعرض في لوحة المعلومات

        Returns:
            {
                "csat": {...},
                "nps": {...},
                "agent_performance": [...],
                "negative_feedback_count": N,
                "total_surveys": N,
                "response_rate": X%,
                "most_common_channel": "whatsapp",
            }
        """
        csat = self.get_csat_stats(days=days)
        nps = self.get_nps_score(days=days)
        agents = self.get_agent_performance(days=days)
        negative = self.get_negative_feedback(days=days, min_rating=2)

        # Channel distribution
        all_records = self._filter_surveys(days=days)
        channel_counts: Dict[str, int] = {}
        for r in all_records:
            if r.channel:
                channel_counts[r.channel] = channel_counts.get(r.channel, 0) + 1
        most_common_channel = max(channel_counts, key=channel_counts.get) if channel_counts else ""

        # Invitation response rate
        total_invitations = sum(
            1 for inv in self._invitations.values() if inv.status != "expired"
        )
        responded = sum(
            1 for inv in self._invitations.values() if inv.status == "responded"
        )
        response_rate = (responded / max(total_invitations, 1)) * 100

        return {
            "csat": csat,
            "nps": nps,
            "agent_performance": agents[:5],  # Top 5
            "negative_feedback_count": len(negative),
            "total_surveys": len(all_records),
            "response_rate": round(response_rate, 2),
            "channel_distribution": channel_counts,
            "most_common_channel": most_common_channel,
            "period_days": days,
        }

    # ──────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────

    def _filter_surveys(
        self,
        survey_type: Optional[str] = None,
        days: int = 365,
        channel: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> List[SurveyRecord]:
        """فلترة الاستبيانات حسب المعايير"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results = []

        for record in self._surveys.values():
            if survey_type and record.survey_type != survey_type:
                continue
            if channel and record.channel != channel:
                continue
            if agent_id and record.agent_id != agent_id:
                continue
            if record.timestamp:
                try:
                    if datetime.fromisoformat(record.timestamp) < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            results.append(record)

        return results

    def _get_rating_label(self, rating: int, survey_type: str) -> str:
        """الحصول على تصنيف التقييم"""
        if survey_type == SurveyType.CSAT:
            return self.CSAT_LABELS.get(rating, str(rating))
        elif survey_type == SurveyType.NPS:
            if rating in self.NPS_PROMOTERS:
                return "داعم (Promoter)"
            elif rating in self.NPS_PASSIVES:
                return "محايد (Passive)"
            else:
                return "ناقد (Detractor)"
        elif survey_type == SurveyType.CES:
            if rating <= 2:
                return "سهل جداً"
            elif rating <= 4:
                return "سهل"
            elif rating <= 5:
                return "متوسط"
            else:
                return "صعب"
        return str(rating)

    @staticmethod
    def _compute_nps_from_records(records: List[SurveyRecord]) -> Dict[str, Any]:
        """حساب NPS من قائمة سجلات"""
        ratings = [r.rating for r in records]
        total = len(ratings)
        if total == 0:
            return {"nps_score": 0}

        promoters = sum(1 for r in ratings if 9 <= r <= 10)
        detractors = sum(1 for r in ratings if 0 <= r <= 6)
        p_pct = (promoters / total) * 100
        d_pct = (detractors / total) * 100

        return {
            "nps_score": round(p_pct - d_pct),
            "promoters": promoters,
            "detractors": detractors,
        }

    @staticmethod
    def _nps_label(score: int) -> str:
        """وصف درجة NPS"""
        if score >= 50:
            return "ممتاز"
        elif score >= 30:
            return "جيد جداً"
        elif score >= 0:
            return "مقبول"
        elif score >= -30:
            return "يحتاج تحسين"
        else:
            return "حرج"