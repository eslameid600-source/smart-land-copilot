"""
محرك المزادات الحقيقية — AuctionEngine
==========================================
Smart Land Management Copilot — Real-Time Auction Engine
=========================================================
محرك مزادات متكامل يعمل مع PostgreSQL عبر AsyncSession:

  • place_bid()       — تقديم مزايدة مع حماية 5% وتجميد المحفظة
  • get_current_bid() — استعلام السعر الحالي
  • close_auction()   — إغلاق المزاد وإعلان الفائز وإشعارات Webhook
  • create_auction()  — إنشاء مزاد جديد من بيانات الارض
  • cancel_auction()  — إلغاء المزاد وتحرير الضمانات

الحماية:
  1. لا يمكن لمستثمر تقديم عرض اعلى من عرضه السابق بـ < 5%
  2. يجب ان يكون العرض اعلى من السعر الحالي + الحد الادنى للزيادة
  3. تجميد 10% من سعر البداية كضمان عند اول مزايدة
  4. Row-level locking عبر SELECT ... FOR UPDATE

التكامل:
  • InvestorStore.freeze_amount() / unfreeze_amount() — ضمان المزاد
  • Webhook إشعار عند الفوز — يُرسل POST إلى رابط مسجل
  • transaction_service — تحديث حالة المعاملة عند اتمام الشراء

الاستخدام:
    from infrastructure.database import get_session
    from core.auction.engine import AuctionEngine

    async with get_session() as session:
        engine = AuctionEngine(session)
        ok = await engine.place_bid("EG-CAI-02", "inv-001", 2_000_000_000)
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

import aiohttp
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.auction.models import (
    Auction, Bid,
    AUCTION_STATUS_ACTIVE, AUCTION_STATUS_CLOSED, AUCTION_STATUS_CANCELLED,
    GUARANTEE_DEPOSIT_PCT, SELF_BID_MIN_INCREMENT_PCT,
)
from core.account.models import Investor, WalletTransaction
from core.account.store import InvestorStore

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# استثناءات المزادات
# ──────────────────────────────────────────────────────────────

class AuctionError(Exception):
    """خطأ عام في المزاد."""
    pass


class AuctionNotActiveError(AuctionError):
    """المزاد ليس نشطاً."""
    pass


class BidTooLowError(AuctionError):
    """العرض اقل من الحد المطلوب."""
    pass


class SelfBidIncrementTooSmallError(AuctionError):
    """زيادة المستثمر على عرضه السابق اقل من 5%."""
    pass


class InsufficientBalanceError(AuctionError):
    """رصيد المحفظة غير كافٍ."""
    pass


class AuctionClosedError(AuctionError):
    """المزاد مغلق بالفعل."""
    pass


# ──────────────────────────────────────────────────────────────
# محرك المزادات
# ──────────────────────────────────────────────────────────────

class AuctionEngine:
    """
    محرك المزادات — يعمل مع AsyncSession و PostgreSQL.

    يوفر كل عمليات المزاد مع حماية من التكرار وتكامل مع المحفظة.
    التزامن يُدار عبر PostgreSQL row-level locks.
    """

    def __init__(
        self,
        session: AsyncSession,
        webhook_url: Optional[str] = None,
        http_timeout: float = 10.0,
    ):
        """
        تهيئة المحرك.

        المعاملات:
            session:     جلسة SQLAlchemy غير متزامنة
            webhook_url: رابط إشعار Webhook عند إعلان الفائز
                         (يُسمح بالتجاوز لكل مزاد عبر auction metadata)
            http_timeout: مهلة إرسال Webhook بالثواني
        """
        self.session = session
        self.investor_store = InvestorStore(session)
        self._webhook_url = webhook_url
        self._http_timeout = http_timeout

    # ══════════════════════════════════════════════════════════
    # إنشاء مزاد جديد
    # ══════════════════════════════════════════════════════════

    async def create_auction(
        self,
        land_id: str,
        start_price_egp: float,
        start_date: datetime,
        end_date: datetime,
        min_bid_increment_pct: float = 0.02,
        guarantee_deposit_pct: float = GUARANTEE_DEPOSIT_PCT,
    ) -> Dict[str, Any]:
        """
        إنشاء مزاد جديد على ارض.

        المعاملات:
            land_id:               معرف الارض
            start_price_egp:       سعر البداية الاجمالي
            start_date:            تاريخ بدء المزاد
            end_date:              تاريخ انتهاء المزاد
            min_bid_increment_pct: الحد الادنى لنسبة الزيادة (الافتراضي 2%)
            guarantee_deposit_pct: نسبة الضمان من سعر البداية (الافتراضي 10%)

        المخرجات:
            بيانات المزاد المنشأ

        يرفع:
            ValueError: إذا كان land_id مسجلاً في مزاد آخر
        """
        # التحقق من عدم وجود مزاد آخر لنفس الارض
        existing = await self._get_auction_by_land(land_id, lock=False)
        if existing is not None:
            raise ValueError(
                f"الارض {land_id} مسجلة بالفعل في مزاد (الحالة: {existing.status}). "
                f"أغلق أو ألغِ المزاد الحالي أولاً."
            )

        guarantee = round(start_price_egp * guarantee_deposit_pct, 2)

        auction = Auction(
            land_id=land_id,
            start_price_egp=start_price_egp,
            current_price_egp=start_price_egp,
            min_bid_increment_pct=min_bid_increment_pct,
            guarantee_deposit_egp=guarantee,
            start_date=start_date,
            end_date=end_date,
            status=AUCTION_STATUS_ACTIVE
            if start_date <= datetime.now(timezone.utc)
            else "pending",
        )
        self.session.add(auction)
        await self.session.flush()

        logger.info(
            "تم إنشاء مزاد %s للارض %s — سعر البداية: %,.0f ج.م | الضمان: %,.0f ج.م | من %s إلى %s",
            auction.id, land_id, start_price_egp, guarantee,
            start_date.strftime("%Y-%m-%d %H:%M"), end_date.strftime("%Y-%m-%d %H:%M"),
        )

        return auction.to_dict()

    # ══════════════════════════════════════════════════════════
    # تقديم مزايدة — place_bid()
    # ══════════════════════════════════════════════════════════

    async def place_bid(
        self,
        land_id: str,
        investor_id: str,
        bid_amount: float,
    ) -> bool:
        """
        تقديم مزايدة جديدة في مزاد نشط.

        خطوات التنفيذ (داخل معاملة واحدة):
          1. قفل المزاد بـ FOR UPDATE
          2. التحقق من أن المزاد نشط
          3. التحقق من أن العرض >= السعر الحالي + الحد الأدنى للزيادة
          4. التحقق من حماية 5% (عرض المستثمر >= آخر عرض له × 1.05)
          5. تجميد ضمان المزاد (10%) إن كانت اول مزايدة لهذا المستثمر
          6. إلغاء تجميد الخاسر السابق (إن وُجد)
          7. إنشاء سجل المزايدة وتحديث السعر الحالي
          8. إلغاء علامة is_winning عن المزايدة السابقة

        المعاملات:
            land_id:     معرف الارض
            investor_id: معرف المستثمر
            bid_amount:  مبلغ العرض بالجنيه

        المخرجات:
            True إذا تم قبول العرض

        يرفع:
            AuctionNotActiveError:         المزاد ليس نشطاً
            BidTooLowError:                العرض اقل من المطلوب
            SelfBidIncrementTooSmallError: زيادة اقل من 5% على عرضه السابق
            InsufficientBalanceError:      رصيد غير كافٍ للضمان
            ValueError:                    المستثمر غير موجود
        """
        # ── الخطوة 1: قفل المزاد ──
        auction = await self._get_auction_by_land(land_id, lock=True)
        if auction is None:
            raise AuctionError(f"لا يوجد مزاد للارض {land_id}")

        # ── الخطوة 2: التحقق من الحالة ──
        if auction.status != AUCTION_STATUS_ACTIVE:
            if auction.status == AUCTION_STATUS_CLOSED:
                raise AuctionClosedError(f"المزاد على {land_id} مغلق بالفعل")
            raise AuctionNotActiveError(
                f"المزاد على {land_id} ليس نشطاً (الحالة: {auction.status})"
            )

        # ── التحقق من وجود المستثمر ──
        investor = await self.investor_store.get(investor_id)
        if investor is None:
            raise ValueError(f"المستثمر {investor_id} غير موجود")

        # ── الخطوة 3: التحقق من الحد الأدنى للعرض ──
        min_required = auction.current_price_egp * (1.0 + auction.min_bid_increment_pct)
        if bid_amount < min_required:
            raise BidTooLowError(
                f"العرض {bid_amount:,.0f} ج.م اقل من الحد المطلوب "
                f"{min_required:,.0f} ج.م (السعر الحالي {auction.current_price_egp:,.0f} "
                f"+ {auction.min_bid_increment_pct:.1%} زيادة)"
            )

        # ── الخطوة 4: حماية 5% من التكرار ──
        last_bid = await self._get_last_bid_by_investor(auction.id, investor_id)
        if last_bid is not None:
            min_self_bid = last_bid.amount_egp * (1.0 + SELF_BID_MIN_INCREMENT_PCT)
            if bid_amount < min_self_bid:
                raise SelfBidIncrementTooSmallError(
                    f"عرضك السابق {last_bid.amount_egp:,.0f} ج.م — "
                    f"الحد الأدنى للعرض الجديد {min_self_bid:,.0f} ج.م "
                    f"(+{SELF_BID_MIN_INCREMENT_PCT:.0%} حماية من التكرار)"
                )

        # ── الخطوة 5: تجميد الضمان (أول مزايدة فقط) ──
        is_first_bid = last_bid is None
        if is_first_bid:
            guarantee = auction.guarantee_deposit_egp
            available = investor.get("available_balance_egp", 0)
            if available < guarantee:
                raise InsufficientBalanceError(
                    f"الرصيد المتاح {available:,.0f} ج.م غير كافٍ لضمان المزاد "
                    f"{guarantee:,.0f} ج.م ({GUARANTEE_DEPOSIT_PCT:.0%} من سعر البداية)"
                )
            await self.investor_store.freeze_amount(
                user_id=investor_id,
                amount=guarantee,
            )
            # إعادة تسجيل المعاملة باسم المزاد
            await self._override_last_tx_description(
                investor_id,
                f"ضمان مزاد {land_id} — تجميد {guarantee:,.0f} ج.م",
                f"auction-guarantee-{land_id}",
            )
            logger.info(
                "تجميد ضمان %,.0f ج.م للمستثمر %s في مزاد %s",
                guarantee, investor_id, land_id,
            )

        # ── الخطوة 6: إلغاء تجميد الخاسر السابق ──
        previous_winning = await self._get_winning_bid(auction.id)
        if previous_winning is not None and previous_winning.investor_id != investor_id:
            # الخاسر السابق يبقى ضمانه مجمداً حتى إغلاق المزاد
            # (لأنه قد يعود ويزايد مجدداً)
            pass

        # ── الخطوة 7: إنشاء سجل المزايدة الجديدة ──
        new_bid = Bid(
            auction_id=auction.id,
            investor_id=investor_id,
            amount_egp=bid_amount,
            is_winning=True,
        )
        self.session.add(new_bid)

        # ── الخطوة 8: إلغاء علامة is_winning عن المزايدة السابقة ──
        if previous_winning is not None:
            previous_winning.is_winning = False

        # ── تحديث سعر المزاد ──
        auction.current_price_egp = bid_amount
        auction.updated_at = datetime.now(timezone.utc)

        await self.session.flush()

        logger.info(
            "مزايدة جديدة في %s: المستثمر %s عرض %,.0f ج.م (السابق: %,.0f) | أول مزايدة: %s",
            land_id, investor_id, bid_amount,
            previous_winning.amount_egp if previous_winning else auction.start_price_egp,
            is_first_bid,
        )

        return True

    # ══════════════════════════════════════════════════════════
    # استعلام السعر الحالي — get_current_bid()
    # ══════════════════════════════════════════════════════════

    async def get_current_bid(self, land_id: str) -> float:
        """
        استعلام اعلى عرض حالي في مزاد.

        المعاملات:
            land_id: معرف الارض

        المخرجات:
            السعر الحالي (اعلى عرض) بالجنيه

        يرفع:
            AuctionError: إذا لم يوجد مزاد للارض
        """
        auction = await self._get_auction_by_land(land_id, lock=False)
        if auction is None:
            raise AuctionError(f"لا يوجد مزاد للارض {land_id}")
        return auction.current_price_egp

    # ══════════════════════════════════════════════════════════
    # إغلاق المزاد — close_auction()
    # ══════════════════════════════════════════════════════════

    async def close_auction(self, land_id: str) -> str:
        """
        إغلاق مزاد وإعلان الفائز.

        خطوات التنفيذ:
          1. قفل المزاد بـ FOR UPDATE
          2. التحقق من أن المزاد نشط
          3. تحديد الفائز (صاحب اعلى عرض)
          4. تحديث حالة المزاد = closed
          5. تحرير ضمانات الخاسرين
          6. إبقاء ضمان الفائز مجمداً (يُستخدم في عملية الشراء)
          7. إرسال Webhook إشعار الفوز
          8. تسجيل معاملة في transaction_service

        المعاملات:
            land_id: معرف الارض

        المخرجات:
            معرف المستثمر الفائز (winner_id)

        يرفع:
            AuctionError:    إذا لم يوجد مزاد أو لم يُقدَّم أي عرض
            AuctionClosedError: إذا كان المزاد مغلقاً بالفعل
        """
        # ── الخطوة 1: قفل المزاد ──
        auction = await self._get_auction_by_land(land_id, lock=True)
        if auction is None:
            raise AuctionError(f"لا يوجد مزاد للارض {land_id}")

        # ── الخطوة 2: التحقق ──
        if auction.status == AUCTION_STATUS_CLOSED:
            raise AuctionClosedError(f"المزاد على {land_id} مغلق بالفعل")
        if auction.status != AUCTION_STATUS_ACTIVE:
            raise AuctionNotActiveError(f"المزاد على {land_id} ليس نشطاً (الحالة: {auction.status})")

        # ── الخطوة 3: تحديد الفائز ──
        winning_bid = await self._get_winning_bid(auction.id)
        if winning_bid is None:
            # لا مزايدات — إغلاق بدون فائز
            auction.status = AUCTION_STATUS_CLOSED
            auction.closed_at = datetime.now(timezone.utc)
            auction.final_price_egp = None
            auction.winner_id = None
            auction.winning_bid_id = None
            await self.session.flush()
            logger.warning("تم إغلاق مزاد %s بدون مزايدات", land_id)
            raise AuctionError(f"لا توجد مزايدات في مزاد {land_id} — لا يمكن تحديد فائز")

        winner_id = winning_bid.investor_id
        final_price = winning_bid.amount_egp

        # ── الخطوة 4: تحديث المزاد ──
        auction.status = AUCTION_STATUS_CLOSED
        auction.winner_id = winner_id
        auction.winning_bid_id = winning_bid.id
        auction.final_price_egp = final_price
        auction.closed_at = datetime.now(timezone.utc)

        # ── الخطوة 5: تحرير ضمانات الخاسرين ──
        all_bidders = await self._get_all_bidders(auction.id)
        for bidder_id in all_bidders:
            if bidder_id != winner_id:
                try:
                    await self.investor_store.unfreeze_amount(
                        user_id=bidder_id,
                        amount=auction.guarantee_deposit_egp,
                    )
                    await self._override_last_tx_description(
                        bidder_id,
                        f"إلغاء ضمان مزاد {land_id} — لم تفز بالمزاد",
                        f"auction-release-{land_id}",
                    )
                    logger.info("تحرير ضمان المزاد للمستثمر الخاسر %s", bidder_id)
                except Exception as e:
                    logger.error(
                        "فشل تحرير ضمان المستثمر %s: %s", bidder_id, e,
                    )

        # ── الخطوة 6: ضمان الفائز يبقى مجمداً ──
        # يبقى مجمداً لأنه سيُستخدم كجزء من دفعة الشراء
        # عند إتمام transfer_ownership يُنقل من مجمد إلى مخصوم
        logger.info(
            "ضمان الفائز %s (%.0f ج.م) يبقى مجمداً لاستخدامه في دفعة الشراء",
            winner_id, auction.guarantee_deposit_egp,
        )

        await self.session.flush()

        # ── الخطوة 7: إرسال إشعار Webhook (غير متزامن — لا يوقف العملية) ──
        webhook_payload = {
            "event": "auction.won",
            "auction_id": auction.id,
            "land_id": land_id,
            "winner_id": winner_id,
            "final_price_egp": final_price,
            "guarantee_frozen_egp": auction.guarantee_deposit_egp,
            "total_bids": len(auction.bids) if auction.bids else 0,
            "closed_at": auction.closed_at.isoformat() if auction.closed_at else None,
            "next_step": "complete_purchase",
            "next_step_description": (
                f"الفائز يجب إتمام شراء {land_id} بالسعر النهائي {final_price:,.0f} ج.م. "
                f"الضمان المجمد {auction.guarantee_deposit_egp:,.0f} ج.م يُخصم من الثمن."
            ),
        }
        await self._send_webhook_notification(
            event="auction.won",
            payload=webhook_payload,
            investor_id=winner_id,
        )

        logger.info(
            "تم إغلاق مزاد %s — الفائز: %s بالسعر %,.0f ج.م | إجمالي المزايدات: %d",
            land_id, winner_id, final_price,
            len(auction.bids) if auction.bids else 0,
        )

        return winner_id

    # ══════════════════════════════════════════════════════════
    # إلغاء مزاد — cancel_auction()
    # ══════════════════════════════════════════════════════════

    async def cancel_auction(self, land_id: str) -> bool:
        """
        إلغاء مزاد وتحرير كل الضمانات المجمدة.

        يمكن إلغاء المزاد فقط إذا كان في حالة pending أو active.

        المعاملات:
            land_id: معرف الارض

        المخرجات:
            True إذا تم الإلغاء بنجاح
        """
        auction = await self._get_auction_by_land(land_id, lock=True)
        if auction is None:
            raise AuctionError(f"لا يوجد مزاد للارض {land_id}")

        if auction.status == AUCTION_STATUS_CLOSED:
            raise AuctionClosedError(f"لا يمكن إلغاء مزاد مغلق: {land_id}")

        auction.status = AUCTION_STATUS_CANCELLED

        # تحرير ضمانات جميع المزايدين
        all_bidders = await self._get_all_bidders(auction.id)
        for bidder_id in all_bidders:
            try:
                await self.investor_store.unfreeze_amount(
                    user_id=bider_id,
                    amount=auction.guarantee_deposit_egp,
                )
                await self._override_last_tx_description(
                    bidder_id,
                    f"إلغاء ضمان مزاد {land_id} — تم إلغاء المزاد",
                    f"auction-cancel-{land_id}",
                )
            except Exception as e:
                logger.error("فشل تحرير ضمان %s عند الإلغاء: %s", bidder_id, e)

        await self.session.flush()

        # إشعار إلغاء
        await self._send_webhook_notification(
            event="auction.cancelled",
            payload={
                "event": "auction.cancelled",
                "auction_id": auction.id,
                "land_id": land_id,
                "affected_bidders": all_bidders,
            },
        )

        logger.info("تم إلغاء مزاد %s — تحرير ضمانات %d مزايد", land_id, len(all_bidders))
        return True

    # ══════════════════════════════════════════════════════════
    # استعلامات مساعدة
    # ══════════════════════════════════════════════════════════

    async def get_auction(self, land_id: str) -> Optional[Dict[str, Any]]:
        """استعلام بيانات المزاد."""
        auction = await self._get_auction_by_land(land_id, lock=False)
        return auction.to_dict() if auction else None

    async def get_bid_history(
        self, land_id: str, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """استعلام تاريخ المزايدات لعقار."""
        auction = await self._get_auction_by_land(land_id, lock=False)
        if auction is None:
            return []
        return [b.to_dict() for b in auction.bids[:limit]]

    async def get_auction_leaderboard(
        self, land_id: str,
    ) -> List[Dict[str, Any]]:
        """
        لوحة المتصدرين — كل المزايدين مرتبين حسب أعلى عرض.

        المخرجات:
            قائمة [{"investor_id", "highest_bid", "bid_count", "is_current_winner"}]
        """
        auction = await self._get_auction_by_land(land_id, lock=False)
        if auction is None:
            return []

        # تجميع البيانات من المزايدات
        bidder_stats: Dict[str, Dict] = {}
        for bid in auction.bids:
            iid = bid.investor_id
            if iid not in bidder_stats:
                bidder_stats[iid] = {
                    "investor_id": iid,
                    "highest_bid": 0.0,
                    "bid_count": 0,
                    "is_current_winner": False,
                }
            bidder_stats[iid]["bid_count"] += 1
            if bid.amount_egp > bidder_stats[iid]["highest_bid"]:
                bidder_stats[iid]["highest_bid"] = bid.amount_egp

        # تحديد الفائز الحالي
        if auction.bids:
            for bid in auction.bids:
                if bid.is_winning:
                    bidder_stats[bid.investor_id]["is_current_winner"] = True
                    break

        # ترتيب تنازلي حسب اعلى عرض
        sorted_board = sorted(
            bidder_stats.values(),
            key=lambda x: x["highest_bid"],
            reverse=True,
        )
        return sorted_board

    async def get_active_auctions(self) -> List[Dict[str, Any]]:
        """استعلام كل المزادات النشطة."""
        stmt = select(Auction).where(Auction.status == AUCTION_STATUS_ACTIVE)
        result = await self.session.execute(stmt)
        auctions = result.scalars().all()
        return [a.to_dict() for a in auctions]

    async def get_investor_auctions(
        self, investor_id: str,
    ) -> List[Dict[str, Any]]:
        """كل المزادات التي شارك فيها مستثمر."""
        stmt = (
            select(Auction)
            .join(Bid, Bid.auction_id == Auction.id)
            .where(Bid.investor_id == investor_id)
            .distinct()
            .order_by(Auction.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [a.to_dict() for a in result.scalars().all()]

    async def get_investor_winning_auctions(
        self, investor_id: str,
    ) -> List[Dict[str, Any]]:
        """المزادات التي المستثمر هو المتصدر فيها حالياً."""
        stmt = (
            select(Auction)
            .join(Bid, Bid.auction_id == Auction.id)
            .where(
                and_(
                    Bid.investor_id == investor_id,
                    Bid.is_winning == True,  # noqa: E712
                    Auction.status == AUCTION_STATUS_ACTIVE,
                )
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        return [a.to_dict() for a in result.scalars().all()]

    # ══════════════════════════════════════════════════════════
    # دوال داخلية
    # ══════════════════════════════════════════════════════════

    async def _get_auction_by_land(
        self, land_id: str, lock: bool = False,
    ) -> Optional[Auction]:
        """استعلام المزاد بمعرف الارض مع قفل اختياري."""
        stmt = select(Auction).where(Auction.land_id == land_id)
        if lock:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_winning_bid(self, auction_id: str) -> Optional[Bid]:
        """است_query آخر مزايدة فائزة."""
        stmt = (
            select(Bid)
            .where(and_(Bid.auction_id == auction_id, Bid.is_winning == True))  # noqa: E712
            .order_by(Bid.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_last_bid_by_investor(
        self, auction_id: str, investor_id: str,
    ) -> Optional[Bid]:
        """استعلام آخر مزايدة للمستثمر في مزاد محدد."""
        stmt = (
            select(Bid)
            .where(and_(
                Bid.auction_id == auction_id,
                Bid.investor_id == investor_id,
            ))
            .order_by(Bid.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_all_bidders(self, auction_id: str) -> List[str]:
        """استعلام قائمة بكل المزايدين الفريدين في مزاد."""
        stmt = (
            select(Bid.investor_id)
            .where(Bid.auction_id == auction_id)
            .distinct()
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _override_last_tx_description(
        self, investor_id: str, description: str, reference_id: str,
    ) -> None:
        """
        تعديل وصف آخر معاملة محفظة للمستثمر.
        يُستخدم لإضافة سياق المزاد لمعاملات التجميد/التحرير.
        """
        stmt = (
            select(WalletTransaction)
            .where(WalletTransaction.investor_id == investor_id)
            .order_by(WalletTransaction.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        last_tx = result.scalar_one_or_none()
        if last_tx is not None:
            last_tx.description_ar = description
            last_tx.reference_id = reference_id

    async def _send_webhook_notification(
        self,
        event: str,
        payload: Dict[str, Any],
        investor_id: Optional[str] = None,
    ) -> None:
        """
        إرسال إشعار Webhook غير متزامن.

        لا يوقف العملية الرئيسية — الأخطاء تُسجَّل فقط.
        يبحث عن WEBHOOK_URL في متغيرات البيئة أو يستخدم الرابط المُمرَّر.
        """
        url = self._webhook_url
        if not url:
            url = os.environ.get("AUCTION_WEBHOOK_URL", "")
        if not url:
            logger.debug("لا يوجد رابط Webhook — تخطي إشعار %s", event)
            return

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self._http_timeout)) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        logger.warning(
                            "Webhook فشل (HTTP %d) للحدث %s: %s",
                            resp.status, event, body[:200],
                        )
                    else:
                        logger.info(
                            "Webhook أُرسل بنجاح: %s → HTTP %d",
                            event, resp.status,
                        )
        except Exception as e:
            logger.error("فشل إرسال Webhook للحدث %s: %s", event, e)


# ──────────────────────────────────────────────────────────────
# عمليات الربط مع transaction_service
# ──────────────────────────────────────────────────────────────

async def complete_auction_purchase(
    session: AsyncSession,
    land_id: str,
    buyer_id: str,
    commission_pct: float = 0.5,
) -> Dict[str, Any]:
    """
    إتمام عملية شراء ارض فائزة بالمزاد.

    يُستدعى بعد close_auction() لإتمام نقل الملكية:
      1. خصم السعر النهائي من محفظة المشتري (بما فيها الضمان المجمد)
      2. تحويل المبلغ إلى البائع
      3. حساب العمولة ونقاط الولاء
      4. تحديث حالة الارض

    هذه الدالة تُغلّف transfer_ownership من core.account.store
    مع تعديل بسيط: الضمان المجمد يُخصم من الثمن.

    المعاملات:
        session:        جلسة SQLAlchemy
        land_id:        معرف الارض
        buyer_id:       معرف المستثمر الفائز
        commission_pct: نسبة عمولة المنصة (الافتراضي 0.5%)

    المخرجات:
        نتيجة نقل الملكية
    """
    from core.account.store import transfer_ownership

    # استدعاء transfer_ownership مع الرصيد المجمد
    # الضمان المجمد يبقى مجمداً — transfer_ownership ستخصمه من wallet_balance
    # ثم نلغي تجميده يدوياً
    result = await transfer_ownership(
        session=session,
        land_id=land_id,
        buyer_id=buyer_id,
        commission_pct=commission_pct,
    )

    # إلغاء تجميد الضمان (تم خصمه من الرصيد في transfer_ownership)
    auction_engine = AuctionEngine(session)
    auction = await auction_engine._get_auction_by_land(land_id, lock=True)
    if auction and auction.guarantee_deposit_egp > 0:
        await auction_engine.investor_store.unfreeze_amount(
            user_id=buyer_id,
            amount=auction.guarantee_deposit_egp,
        )

    logger.info(
        "تم إتمام شراء ارض المزاد %s للمستثمر %s",
        land_id, buyer_id,
    )

    return result


