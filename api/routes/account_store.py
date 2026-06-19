"""
مخزن الحسابات — InvestorStore + LandownerStore + transfer_ownership()
=====================================================================
Smart Land Management Copilot — Account Data Layer
====================================================
• InvestorStore — جدول المستثمرين (user_id, wallet_balance_egp, total_lands_purchased, loyalty_points)
• LandownerStore — جدول ملاك الأراضي (user_id, total_sales_egp, total_lands_listed, default_commission_pct)
• transfer_ownership(land_id, buyer_id) — نقل ملكية أرض عند اكتمال الشراء
• سجل معاملات المحفظة (wallet_transactions)
• حماية تزامنية بـ threading.Lock

في الإنتاج: استبدل الذاكرة الداخلية بـ PostgreSQL / SQLAlchemy.

الاستخدام:
    from account_store import investor_store, landowner_store, transfer_ownership

    # إنشاء مستثمر
    investor_store.create(user_id="inv-001", initial_deposit=500_000)

    # نقل ملكية
    result = transfer_ownership(land_id="EG-CAI-01", buyer_id="inv-001")
"""

import os
import uuid
import logging
import threading
import sys
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# إعدادات عامة
# ──────────────────────────────────────────────────────────────

LOYALTY_POINTS_PER_EGP = float(os.getenv("LOYALTY_POINTS_PER_EGP", "0.0001"))
# 0.0001 = 10,000 جنيه = 1 نقطة ولاء
LOYALTY_REDEEM_RATE = float(os.getenv("LOYALTY_REDEEM_RATE", "10.0"))
# كل نقطة ولاء = 10 جنيه عند الاستبدال
MIN_WALLET_BALANCE = float(os.getenv("MIN_WALLET_BALANCE", "0"))
PLATFORM_COMMISSION_PCT = float(os.getenv("PLATFORM_COMMISSION_PCT", "0.5"))
# عمولة المنصة 0.5% من كل معاملة


# ──────────────────────────────────────────────────────────────
# 1. مخزن المستثمرين — جدول investors
# ──────────────────────────────────────────────────────────────

class InvestorStore:
    """
    جدول المستثمرين (in-memory).

    الحقول:
        user_id              — معرّف المستخدم الفريد (مفتاح رئيسي)
        wallet_balance_egp   — رصيد المحفظة الحالي
        frozen_balance_egp   — رصيد مجمد في معاملات قيد التنفيذ
        total_lands_purchased — عدد الأراضي المشتراة
        loyalty_points       — نقاط الولاء المكتسبة
        total_spent_egp      — إجمالي المبالغ المنفقة
        created_at           — تاريخ إنشاء الحساب
        updated_at           — تاريخ آخر تحديث

    حماية التزامن:
        جميع عمليات الكتابة محمية بـ threading.Lock.
    """

    def __init__(self):
        # {user_id: {field: value, ...}}
        self._investors: Dict[str, Dict[str, Any]] = {}
        # سجل معاملات المحفظة: {user_id: [tx_dict, ...]}
        self._wallet_transactions: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    # ─── إنشاء حساب مستثمر ───

    def create(
        self,
        user_id: str,
        initial_deposit: float = 0.0,
    ) -> Dict[str, Any]:
        """
        إنشاء حساب مستثمر جديد.

        Args:
            user_id: معرّف المستخدم من خدمة المصادقة
            initial_deposit: الإيداع الأولي (الافتراضي: 0)

        Returns:
            بيانات المستثمر المنشأ

        Raises:
            ValueError: إذا كان المستثمر موجوداً مسبقاً
        """
        with self._lock:
            if user_id in self._investors:
                raise ValueError(f"المستثمر {user_id} مسجل مسبقاً")

            now = datetime.now(timezone.utc).isoformat()
            investor = {
                "user_id": user_id,
                "wallet_balance_egp": float(initial_deposit),
                "frozen_balance_egp": 0.0,
                "total_lands_purchased": 0,
                "loyalty_points": 0,
                "total_spent_egp": 0.0,
                "created_at": now,
                "updated_at": now,
            }
            self._investors[user_id] = investor
            self._wallet_transactions[user_id] = []

            # سجل إيداع أولي إن وُجد
            if initial_deposit > 0:
                self._add_transaction(
                    user_id=user_id,
                    tx_type="deposit",
                    amount=initial_deposit,
                    description="إيداع أولي عند إنشاء الحساب",
                    reference_id="",
                )

            logger.info(f"تم إنشاء حساب مستثمر: {user_id} (إيداع أولي: {initial_deposit:,.2f} ج.م)")
            return dict(investor)

    # ─── استرجاع بيانات ───

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع بيانات مستثمر واحد."""
        with self._lock:
            data = self._investors.get(user_id)
            return dict(data) if data else None

    def get_all(self) -> List[Dict[str, Any]]:
        """استرجاع جميع المستثمرين."""
        with self._lock:
            return [dict(inv) for inv in self._investors.values()]

    def exists(self, user_id: str) -> bool:
        """التحقق من وجود مستثمر."""
        return user_id in self._investors

    def count(self) -> int:
        """عدد المستثمرين المسجلين."""
        return len(self._investors)

    # ─── عمليات المحفظة ───

    def get_wallet(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        بيانات المحفظة الكاملة لمستثمر.

        Returns:
            {
                "user_id", "wallet_balance_egp", "frozen_balance_egp",
                "available_balance_egp", "loyalty_points",
                "total_lands_purchased", "total_spent_egp",
                "last_transaction_at"
            }
            أو None إذا لم يُوجد المستثمر.
        """
        with self._lock:
            inv = self._investors.get(user_id)
            if not inv:
                return None

            txs = self._wallet_transactions.get(user_id, [])
            last_tx_time = txs[-1]["created_at"] if txs else None

            return {
                "user_id": user_id,
                "wallet_balance_egp": inv["wallet_balance_egp"],
                "frozen_balance_egp": inv["frozen_balance_egp"],
                "available_balance_egp": inv["wallet_balance_egp"] - inv["frozen_balance_egp"],
                "loyalty_points": inv["loyalty_points"],
                "total_lands_purchased": inv["total_lands_purchased"],
                "total_spent_egp": inv["total_spent_egp"],
                "last_transaction_at": last_tx_time,
            }

    def deposit(self, user_id: str, amount: float, description: str = "", reference_id: str = "") -> Dict[str, Any]:
        """
        إيداع مبلغ في محفظة المستثمر.

        Args:
            user_id: معرّف المستثمر
            amount: مبلغ الإيداع (يجب أن يكون موجباً)
            description: وصف العملية
            reference_id: مرجع المعاملة (رقم فاتورة / معاملة دفع)

        Returns:
            بيانات المحفظة بعد الإيداع

        Raises:
            ValueError: إذا كان المبلغ غير صالح أو المستثمر غير موجود
        """
        if amount <= 0:
            raise ValueError("مبلغ الإيداع يجب أن يكون موجباً")

        with self._lock:
            inv = self._investors.get(user_id)
            if not inv:
                raise ValueError(f"المستثمر {user_id} غير موجود")

            inv["wallet_balance_egp"] += amount
            inv["updated_at"] = datetime.now(timezone.utc).isoformat()

            self._add_transaction(
                user_id=user_id,
                tx_type="deposit",
                amount=amount,
                description=description or "إيداع في المحفظة",
                reference_id=reference_id,
            )

            logger.info(f"إيداع {amount:,.2f} ج.م في محفظة {user_id}")
            return self._wallet_dict(inv, user_id)

    def withdraw(self, user_id: str, amount: float, description: str = "", reference_id: str = "") -> Dict[str, Any]:
        """
        سحب مبلغ من محفظة المستثمر.

        Args:
            user_id: معرّف المستثمر
            amount: مبلغ السحب
            description: وصف العملية
            reference_id: مرجع المعاملة

        Returns:
            بيانات المحفظة بعد السحب

        Raises:
            ValueError: إذا كان الرصيد غير كافٍ أو المبلغ غير صالح
        """
        if amount <= 0:
            raise ValueError("مبلغ السحب يجب أن يكون موجباً")

        with self._lock:
            inv = self._investors.get(user_id)
            if not inv:
                raise ValueError(f"المستثمر {user_id} غير موجود")

            available = inv["wallet_balance_egp"] - inv["frozen_balance_egp"]
            if available < amount:
                raise ValueError(
                    f"الرصيد المتاح غير كافٍ. المتاح: {available:,.2f} ج.م، المطلوب: {amount:,.2f} ج.م"
                )

            inv["wallet_balance_egp"] -= amount
            inv["updated_at"] = datetime.now(timezone.utc).isoformat()

            self._add_transaction(
                user_id=user_id,
                tx_type="withdrawal",
                amount=-amount,
                description=description or "سحب من المحفظة",
                reference_id=reference_id,
            )

            logger.info(f"سحب {amount:,.2f} ج.م من محفظة {user_id}")
            return self._wallet_dict(inv, user_id)

    def freeze_amount(self, user_id: str, amount: float) -> bool:
        """
        تجميد مبلغ في المحفظة (عند بدء معاملة شراء).

        Args:
            user_id: معرّف المستثمر
            amount: المبلغ المطلوب تجميده

        Returns:
            True إذا نجح التجميد

        Raises:
            ValueError: إذا كان الرصيد المتاح غير كافٍ
        """
        with self._lock:
            inv = self._investors.get(user_id)
            if not inv:
                raise ValueError(f"المستثمر {user_id} غير موجود")

            available = inv["wallet_balance_egp"] - inv["frozen_balance_egp"]
            if available < amount:
                raise ValueError(f"الرصيد المتاح غير كافٍ لتجميد {amount:,.2f} ج.م")

            inv["frozen_balance_egp"] += amount
            inv["updated_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"تجميد {amount:,.2f} ج.م في محفظة {user_id}")
            return True

    def unfreeze_amount(self, user_id: str, amount: float) -> bool:
        """إلغاء تجميد مبلغ (عند إلغاء المعاملة)."""
        with self._lock:
            inv = self._investors.get(user_id)
            if not inv:
                return False

            actual_unfreeze = min(amount, inv["frozen_balance_egp"])
            inv["frozen_balance_egp"] -= actual_unfreeze
            inv["updated_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"إلغاء تجميد {actual_unfreeze:,.2f} ج.م في محفظة {user_id}")
            return True

    # ─── نقاط الولاء ───

    def add_loyalty_points(self, user_id: str, spent_amount: float) -> int:
        """
        إضافة نقاط ولاء بناءً على المبلغ المنفق.

        معدل: كل 10,000 ج.م = 1 نقطة ولاء (قابل للتعديل عبر LOYALTY_POINTS_PER_EGP).

        Args:
            user_id: معرّف المستثمر
            spent_amount: المبلغ المنفق

        Returns:
            عدد النقاط المضافة
        """
        points_earned = int(spent_amount * LOYALTY_POINTS_PER_EGP)
        if points_earned <= 0:
            return 0

        with self._lock:
            inv = self._investors.get(user_id)
            if not inv:
                return 0

            inv["loyalty_points"] += points_earned
            inv["updated_at"] = datetime.now(timezone.utc).isoformat()

            self._add_transaction(
                user_id=user_id,
                tx_type="loyalty_earn",
                amount=0.0,
                description=f"كسب {points_earned} نقطة ولاء من شراء بقيمة {spent_amount:,.2f} ج.م",
                reference_id="",
            )

            logger.info(f"كسب المستثمر {user_id} عدد {points_earned} نقطة ولاء")
            return points_earned

    def redeem_loyalty_points(self, user_id: str, points: int) -> float:
        """
        استبدال نقاط الولاء برصيد في المحفظة.

        معدل: كل نقطة = 10 ج.م (قابل للتعديل عبر LOYALTY_REDEEM_RATE).

        Args:
            user_id: معرّف المستثمر
            points: عدد النقاط المطلوب استبدالها

        Returns:
            المبلغ المضاف بالجنيه

        Raises:
            ValueError: إذا لم تكن النقاط كافية
        """
        if points <= 0:
            raise ValueError("عدد النقاط يجب أن يكون موجباً")

        with self._lock:
            inv = self._investors.get(user_id)
            if not inv:
                raise ValueError(f"المستثمر {user_id} غير موجود")

            if inv["loyalty_points"] < points:
                raise ValueError(
                    f"نقاط الولاء غير كافية. المتاح: {inv['loyalty_points']}, المطلوب: {points}"
                )

            egp_amount = points * LOYALTY_REDEEM_RATE
            inv["loyalty_points"] -= points
            inv["wallet_balance_egp"] += egp_amount
            inv["updated_at"] = datetime.now(timezone.utc).isoformat()

            self._add_transaction(
                user_id=user_id,
                tx_type="loyalty_redeem",
                amount=egp_amount,
                description=f"استبدال {points} نقطة ولاء = {egp_amount:,.2f} ج.م",
                reference_id="",
            )

            logger.info(f"استبدال المستثمر {user_id} عدد {points} نقطة = {egp_amount:,.2f} ج.م")
            return egp_amount

    # ─── تحديث إحصائيات الشراء ───

    def increment_purchased(self, user_id: str, amount_spent: float) -> None:
        """زيادة عداد الأراضي المشتراة وإجمالي المبالغ المنفقة (يُستدعى داخلياً من transfer_ownership)."""
        with self._lock:
            inv = self._investors.get(user_id)
            if inv:
                inv["total_lands_purchased"] += 1
                inv["total_spent_egp"] += amount_spent
                inv["updated_at"] = datetime.now(timezone.utc).isoformat()

    # ─── سجل المعاملات ───

    def get_transactions(
        self,
        user_id: str,
        tx_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        استرجاع سجل معاملات المحفظة.

        Args:
            user_id: معرّف المستثمر
            tx_type: فلتر نوع المعاملة (اختياري)
            limit: الحد الأقصى للنتائج

        Returns:
            قائمة المعاملات (الأحدث أولاً)
        """
        with self._lock:
            txs = self._wallet_transactions.get(user_id, [])
            if tx_type:
                txs = [t for t in txs if t["type"] == tx_type]
            # الأحدث أولاً
            return list(reversed(txs[-limit:]))

    # ─── دوال مساعدة داخلية ───

    def _add_transaction(
        self,
        user_id: str,
        tx_type: str,
        amount: float,
        description: str,
        reference_id: str,
    ) -> None:
        """إضافة معاملة لسجل المحفظة (يجب استدعاؤها داخل _lock)."""
        inv = self._investors.get(user_id)
        if not inv:
            return

        tx = {
            "tx_id": f"tx-{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "type": tx_type,
            "amount_egp": amount,
            "balance_after_egp": inv["wallet_balance_egp"],
            "description_ar": description,
            "reference_id": reference_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._wallet_transactions.setdefault(user_id, []).append(tx)

    def _wallet_dict(self, inv: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """بناء قاموس المحفظة (يُستدعى داخل _lock)."""
        txs = self._wallet_transactions.get(user_id, [])
        return {
            "user_id": user_id,
            "wallet_balance_egp": inv["wallet_balance_egp"],
            "frozen_balance_egp": inv["frozen_balance_egp"],
            "available_balance_egp": inv["wallet_balance_egp"] - inv["frozen_balance_egp"],
            "loyalty_points": inv["loyalty_points"],
            "total_lands_purchased": inv["total_lands_purchased"],
            "total_spent_egp": inv["total_spent_egp"],
            "last_transaction_at": txs[-1]["created_at"] if txs else None,
        }


# ──────────────────────────────────────────────────────────────
# 2. مخزن ملاك الأراضي — جدول landowners
# ──────────────────────────────────────────────────────────────

class LandownerStore:
    """
    جدول ملاك الأراضي (in-memory).

    الحقول:
        user_id                  — معرّف المستخدم (مفتاح رئيسي)
        total_sales_egp          — إجمالي المبيعات
        total_lands_listed       — إجمالي الأراضي المُعلنة (تاريخياً)
        active_lands_count       — الأراضي المعروضة حالياً
        default_commission_pct   — نسبة العمولة الافتراضية
        total_commission_earned_egp — إجمالي العمولات المحصّلة
        created_at / updated_at  — التواريخ
    """

    def __init__(self):
        self._landowners: Dict[str, Dict[str, Any]] = {}
        # سجل الأراضي المملوكة: {user_id: [land_record, ...]}
        self._owned_lands: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    # ─── إنشاء حساب مالك أرض ───

    def create(
        self,
        user_id: str,
        default_commission_pct: float = 2.5,
    ) -> Dict[str, Any]:
        """
        إنشاء حساب مالك أرض جديد.

        Args:
            user_id: معرّف المستخدم
            default_commission_pct: نسبة العمولة الافتراضية (0-50%)

        Returns:
            بيانات المالك المنشأ

        Raises:
            ValueError: إذا كان المالك موجوداً مسبقاً
        """
        if not (0 <= default_commission_pct <= 50):
            raise ValueError("نسبة العمولة يجب أن تكون بين 0% و 50%")

        with self._lock:
            if user_id in self._landowners:
                raise ValueError(f"مالك الأرض {user_id} مسجل مسبقاً")

            now = datetime.now(timezone.utc).isoformat()
            landowner = {
                "user_id": user_id,
                "total_sales_egp": 0.0,
                "total_lands_listed": 0,
                "active_lands_count": 0,
                "default_commission_pct": float(default_commission_pct),
                "total_commission_earned_egp": 0.0,
                "created_at": now,
                "updated_at": now,
            }
            self._landowners[user_id] = landowner
            self._owned_lands[user_id] = []

            logger.info(f"تم إنشاء حساب مالك أرض: {user_id} (عمولة: {default_commission_pct}%)")
            return dict(landowner)

    # ─── استرجاع بيانات ───

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع بيانات مالك أرض."""
        with self._lock:
            data = self._landowners.get(user_id)
            return dict(data) if data else None

    def get_all(self) -> List[Dict[str, Any]]:
        """استرجاع جميع ملاك الأراضي."""
        with self._lock:
            return [dict(lo) for lo in self._landowners.values()]

    def exists(self, user_id: str) -> bool:
        return user_id in self._landowners

    def count(self) -> int:
        return len(self._landowners)

    # ─── إدارة الأراضي المملوكة ───

    def list_land(self, user_id: str, land_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        إضافة أرض لقائمة المالك المعروضة.

        Args:
            user_id: معرّف المالك
            land_data: بيانات الأرض (land_id, name, governorate, activity, ...)

        Returns:
            سجل الأرض المُضافة

        Raises:
            ValueError: إذا كان المالك غير موجود أو الأرض مسجلة مسبقاً
        """
        land_id = land_data.get("land_id", "")
        if not land_id:
            raise ValueError("بيانات الأرض يجب أن تحتوي على land_id")

        with self._lock:
            lo = self._landowners.get(user_id)
            if not lo:
                raise ValueError(f"مالك الأرض {user_id} غير موجود")

            # منع التكرار
            existing_ids = {l["land_id"] for l in self._owned_lands.get(user_id, [])}
            if land_id in existing_ids:
                raise ValueError(f"الأرض {land_id} مسجلة مسبقاً لدى هذا المالك")

            land_record = {
                **land_data,
                "owner_id": user_id,
                "listed_at": datetime.now(timezone.utc).isoformat(),
                "views_count": 0,
                "inquiries_count": 0,
            }

            self._owned_lands.setdefault(user_id, []).append(land_record)
            lo["total_lands_listed"] += 1
            lo["active_lands_count"] += 1
            lo["updated_at"] = datetime.now(timezone.utc).isoformat()

            logger.info(f"إعلان أرض {land_id} بواسطة المالك {user_id}")
            return dict(land_record)

    def get_lands(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        استرجاع أراضي المالك.

        Args:
            user_id: معرّف المالك
            status: فلتر حالة الاستثمار (متاح / مباع / مزاد)
            limit: الحد الأقصى

        Returns:
            قائمة الأراضي
        """
        with self._lock:
            lands = self._owned_lands.get(user_id, [])
            if status:
                lands = [l for l in lands if l.get("investment_status") == status]
            return [dict(l) for l in lands[-limit:]]

    def get_land_by_id(self, user_id: str, land_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع أرض محددة لمالك محدد."""
        with self._lock:
            for land in self._owned_lands.get(user_id, []):
                if land["land_id"] == land_id:
                    return dict(land)
            return None

    def remove_land(self, user_id: str, land_id: str) -> bool:
        """حذف أرض من قائمة المالك (إلغاء الإعلان)."""
        with self._lock:
            lo = self._landowners.get(user_id)
            if not lo:
                return False

            lands = self._owned_lands.get(user_id, [])
            original_len = len(lands)
            self._owned_lands[user_id] = [
                l for l in lands if l["land_id"] != land_id
            ]
            removed = len(self._owned_lands[user_id]) < original_len

            if removed:
                lo["active_lands_count"] = max(0, lo["active_lands_count"] - 1)
                lo["updated_at"] = datetime.now(timezone.utc).isoformat()
                logger.info(f"حذف أرض {land_id} من قائمة المالك {user_id}")

            return removed

    def increment_views(self, user_id: str, land_id: str) -> None:
        """زيادة عداد المشاهدات لأرض محددة."""
        with self._lock:
            for land in self._owned_lands.get(user_id, []):
                if land["land_id"] == land_id:
                    land["views_count"] += 1
                    break

    def increment_inquiries(self, user_id: str, land_id: str) -> None:
        """زيادة عداد الاستفسارات لأرض محددة."""
        with self._lock:
            for land in self._owned_lands.get(user_id, []):
                if land["land_id"] == land_id:
                    land["inquiries_count"] += 1
                    break

    # ─── تحديث إحصائيات البيع ───

    def record_sale(
        self,
        user_id: str,
        sale_amount: float,
        commission_pct: float,
    ) -> float:
        """
        تسجيل عملية بيع وتحديث إحصائيات المالك.

        Args:
            user_id: معرّف المالك
            sale_amount: مبلغ البيع
            commission_pct: نسبة العمولة المُطبّقة

        Returns:
            مبلغ العمولة المحسوب
        """
        commission = sale_amount * (commission_pct / 100.0)

        with self._lock:
            lo = self._landowners.get(user_id)
            if lo:
                lo["total_sales_egp"] += sale_amount
                lo["total_commission_earned_egp"] += commission
                lo["updated_at"] = datetime.now(timezone.utc).isoformat()
                logger.info(
                    f"تسجيل بيع للمالك {user_id}: {sale_amount:,.2f} ج.م (عمولة: {commission:,.2f} ج.م)"
                )

        return commission

    def update_commission(self, user_id: str, new_pct: float) -> Dict[str, Any]:
        """تحديث نسبة العمولة الافتراضية للمالك."""
        if not (0 <= new_pct <= 50):
            raise ValueError("نسبة العمولة يجب أن تكون بين 0% و 50%")

        with self._lock:
            lo = self._landowners.get(user_id)
            if not lo:
                raise ValueError(f"مالك الأرض {user_id} غير موجود")

            old_pct = lo["default_commission_pct"]
            lo["default_commission_pct"] = float(new_pct)
            lo["updated_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"تحديث عمولة المالك {user_id}: {old_pct}% → {new_pct}%")
            return dict(lo)

    # ─── نقل ملكية (داخلي) ───

    def transfer_land_ownership(
        self,
        seller_id: str,
        land_id: str,
        new_owner_id: str,
    ) -> bool:
        """
        نقل أرض من مالك لآخر (يُستدعى من transfer_ownership).

        يُزيل الأرض من قائمة البائع ويُضيفها للمشتري الجديد
        (إذا كان المشتري مالكاً مسجلاً).
        """
        with self._lock:
            # إزالة من البائع
            seller_lands = self._owned_lands.get(seller_id, [])
            self._owned_lands[seller_id] = [
                l for l in seller_lands if l["land_id"] != land_id
            ]

            seller = self._landowners.get(seller_id)
            if seller:
                seller["active_lands_count"] = max(0, seller["active_lands_count"] - 1)
                seller["updated_at"] = datetime.now(timezone.utc).isoformat()

            # إذا المشتري مالك مسجل → أضف الأرض لقائمته
            if new_owner_id in self._landowners:
                # لا نضيف الأرض للمشتري تلقائياً لأنه مستثمر
                # الأرض تنتقل لقائمة الأراضي المملوكة للمشتري
                pass

        return True


# ──────────────────────────────────────────────────────────────
# 3. دالة نقل الملكية — transfer_ownership()
# ──────────────────────────────────────────────────────────────

def transfer_ownership(
    land_id: str,
    buyer_id: str,
    investor_store: Optional[InvestorStore] = None,
    landowner_store: Optional[LandownerStore] = None,
    lands_catalog: Optional[Dict[str, Dict[str, Any]]] = None,
    commission_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """
    نقل ملكية أرض عند اكتمال عملية الشراء.

    هذه الدالة تنفذ الخطوات التالية بالترتيب:
        1. التحقق من وجود الأرض في الكتالوج وأنها متاحة للبيع
        2. التحقق من أن المشتري مستثمر مسجل برصيد كافٍ
        3. حساب سعر البيع وعمولة المالك وعمولة المنصة
        4. خصم السعر من محفظة المشتري (إلغاء تجميد + خصم)
        5. تحديث حالة الأرض في الكتالوج إلى "مباع"
        6. تحديث إحصائيات المشتري (عدد الأراضي، إجمالي المنفق)
        7. تحديث إحصائيات البائع (إجمالي المبيعات، العمولات)
        8. إضافة نقاط ولاء للمشتري
        9. إزالة الأرض من قائمة البائع

    Args:
        land_id: معرّف الأرض المراد نقل ملكيتها
        buyer_id: معرّف المشتري (المستثمر)
        investor_store: مخزن المستثمرين (إذا None يُستخدم المثيل العام)
        landowner_store: مخزن ملاك الأراضي (إذا None يُستخدم المثيل العام)
        lands_catalog: كتالوج الأراضي (إذا None يُستخدم الكتالوج العام)
        commission_pct: نسبة العمولة (إذا None تُستخدم نسبة المالك الافتراضية)

    Returns:
        {
            "success": True,
            "land_id": str,
            "seller_id": str,
            "buyer_id": str,
            "sale_price_egp": float,
            "commission_egp": float,
            "platform_fee_egp": float,
            "loyalty_points_earned": int,
            "new_owner_id": str,
            "transaction_id": str,
            "transferred_at": str (ISO),
            "message_ar": str,
        }

    Raises:
        ValueError: في حالات الخطأ المختلفة مع رسائل عربية واضحة
    """
    _inv_store = investor_store or investor_store_global
    _lo_store = landowner_store or landowner_store_global
    _catalog = lands_catalog or lands_catalog_global

    if _inv_store is None or _lo_store is None:
        raise ValueError("لم يتم تهيئة المخازن — استدعِ init_stores() أولاً")

    # ─── الخطوة 1: التحقق من الأرض ───
    land = _catalog.get(land_id)
    if not land:
        raise ValueError(f"الأرض {land_id} غير موجودة في الكتالوج")

    if land.get("investment_status") != "متاح":
        raise ValueError(f"الأرض {land_id} غير متاحة للبيع (الحالة: {land.get('investment_status', 'غير محددة')})")

    seller_id = land.get("owner_id", "")
    if not seller_id:
        raise ValueError(f"الأرض {land_id} ليس لها مالك مسجل")

    sale_price = float(land.get("total_price_egp", 0))
    if sale_price <= 0:
        raise ValueError(f"سعر الأرض {land_id} غير صالح: {sale_price}")

    # ─── الخطوة 2: التحقق من المشتري ───
    buyer = _inv_store.get(buyer_id)
    if not buyer:
        raise ValueError(f"المشتري {buyer_id} ليس مستثمراً مسجلاً")

    available_balance = buyer["wallet_balance_egp"] - buyer["frozen_balance_egp"]
    if available_balance < sale_price:
        raise ValueError(
            f"رصيد المشتري غير كافٍ. المتاح: {available_balance:,.2f} ج.م، المطلوب: {sale_price:,.2f} ج.م"
        )

    # ─── الخطوة 3: حساب العمولات ───
    seller = _lo_store.get(seller_id)
    if seller:
        actual_commission_pct = commission_pct if commission_pct is not None else seller["default_commission_pct"]
    else:
        actual_commission_pct = commission_pct if commission_pct is not None else 2.5

    commission_amount = sale_price * (actual_commission_pct / 100.0)
    platform_fee = sale_price * (PLATFORM_COMMISSION_PCT / 100.0)
    net_to_seller = sale_price - commission_amount - platform_fee

    # ─── الخطوة 4: خصم من محفظة المشتري ───
    try:
        # إلغاء التجميد أولاً (لو كان مجمداً من قبل)
        _inv_store.unfreeze_amount(buyer_id, sale_price)
        # خصم المبلغ
        _inv_store.withdraw(
            buyer_id,
            amount=sale_price,
            description=f"شراء أرض {land_id} — {land.get('name', '')}",
            reference_id=f"sale-{land_id}",
        )
    except ValueError as e:
        raise ValueError(f"فشل خصم المبلغ من محفظة المشتري: {str(e)}")

    # ─── الخطوة 5: تحديث حالة الأرض ───
    land["investment_status"] = "مباع"
    land["sold_at"] = datetime.now(timezone.utc).isoformat()
    land["buyer_id"] = buyer_id
    land["sale_price_egp"] = sale_price
    land["commission_pct"] = actual_commission_pct

    # ─── الخطوة 6: تحديث إحصائيات المشتري ───
    _inv_store.increment_purchased(buyer_id, sale_price)

    # ─── الخطوة 7: تحديث إحصائيات البائع ───
    if seller:
        _lo_store.record_sale(seller_id, sale_price, actual_commission_pct)
        _lo_store.transfer_land_ownership(seller_id, land_id, buyer_id)

    # ─── الخطوة 8: نقاط الولاء ───
    loyalty_earned = _inv_store.add_loyalty_points(buyer_id, sale_price)

    # ─── الخطوة 9: إيداع صافي البيع في محفظة البائع (لو هو مستثمر أيضاً) ───
    if seller_id in _inv_store._investors:
        try:
            _inv_store.deposit(
                seller_id,
                amount=net_to_seller,
                description=f"صافي بيع أرض {land_id} (بعد عمولة {actual_commission_pct}% + رسوم منصة)",
                reference_id=f"sale-{land_id}",
            )
        except Exception as e:
            logger.warning(f"فشل إيداع صافي البيع للمستثمر-البائع {seller_id}: {e}")

    # ─── بناء النتيجة ───
    transaction_id = f"tx-own-{uuid.uuid4().hex[:12]}"
    transferred_at = datetime.now(timezone.utc).isoformat()

    result = {
        "success": True,
        "land_id": land_id,
        "seller_id": seller_id,
        "buyer_id": buyer_id,
        "sale_price_egp": sale_price,
        "commission_egp": round(commission_amount, 2),
        "platform_fee_egp": round(platform_fee, 2),
        "net_to_seller_egp": round(net_to_seller, 2),
        "loyalty_points_earned": loyalty_earned,
        "new_owner_id": buyer_id,
        "transaction_id": transaction_id,
        "transferred_at": transferred_at,
        "message_ar": f"تم نقل ملكية الأرض {land_id} من {seller_id} إلى {buyer_id} بنجاح",
    }

    logger.info(
        f"نقل ملكية ناجح: {land_id} | البائع: {seller_id} | المشتري: {buyer_id} | "
        f"السعر: {sale_price:,.2f} ج.م | العمولة: {commission_amount:,.2f} ج.م | "
        f"نقاط الولاء: {loyalty_earned}"
    )

    return result


# ──────────────────────────────────────────────────────────────
# 4. مثيلات عامة + بيانات تجريبية + تهيئة
# ──────────────────────────────────────────────────────────────

# المثيلات العامة (تُستخدم إذا لم يُمرّر مخزن مخصص)
investor_store_global: Optional[InvestorStore] = None
landowner_store_global: Optional[LandownerStore] = None
lands_catalog_global: Dict[str, Dict[str, Any]] = {}


def init_stores(
    lands_data: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[InvestorStore, LandownerStore]:
    """
    تهيئة المخازن العامة مع بيانات تجريبية اختيارية.

    Args:
        lands_data: قائمة بيانات الأراضي (من land_database.get_all_lands())

    Returns:
        (investor_store, landowner_store)
    """
    _mod = sys.modules[__name__]
    _mod.investor_store_global = InvestorStore()  # type: ignore[attr-defined]
    _mod.landowner_store_global = LandownerStore()  # type: ignore[attr-defined]

    # بناء كتالوج الأراضي
    if lands_data:
        for land in lands_data:
            lid = land.get("land_id", "")
            if lid:
                lands_catalog_global[lid] = dict(land)
                # ربط كل أرض بمالك افتراضي
                if "owner_id" not in land:
                    lands_catalog_global[lid]["owner_id"] = f"owner-{lid}"

                # تسجيل المالكين تلقائياً
                owner_id = lands_catalog_global[lid].get("owner_id", "")
                if owner_id and landowner_store_global is not None:
                    if not landowner_store_global.exists(owner_id):
                        landowner_store_global.create(owner_id, default_commission_pct=2.5)

                # إضافة الأرض لقائمة المالك
                if owner_id and landowner_store_global is not None:
                    try:
                        landowner_store_global.list_land(owner_id, lands_catalog_global[lid])
                    except ValueError:
                        pass  # الأرض مسجلة مسبقاً

    # إنشاء مستثمرين تجريبيين
    if investor_store_global is not None:
        _seed_demo_investors(investor_store_global)

    logger.info(
        f"تم تهيئة المخازن: {investor_store_global.count() if investor_store_global else 0} مستثمر، "
        f"{landowner_store_global.count() if landowner_store_global else 0} مالك أرض، "
        f"{len(lands_catalog_global)} أرض"
    )

    return investor_store_global, landowner_store_global  # type: ignore[return-value]


def _seed_demo_investors(store: InvestorStore) -> None:
    """بذر بيانات مستثمرين تجريبيين."""
    demo_investors = [
        ("inv-demo-001", "أحمد محمد علي", 5_000_000),
        ("inv-demo-002", "شركة النيل للاستثمار", 25_000_000),
        ("inv-demo-003", "سارة حسن إبراهيم", 1_500_000),
        ("inv-demo-004", "مجموعة الأفق العقارية", 50_000_000),
        ("inv-demo-005", "محمد أشرف سليمان", 800_000),
    ]

    for user_id, _name, deposit in demo_investors:
        try:
            store.create(user_id=user_id, initial_deposit=deposit)
        except ValueError:
            pass  # موجود مسبقاً
