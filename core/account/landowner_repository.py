"""
مخزن ملاك الأراضي — LandownerStore
=====================================
CRUD كامل لملاك الأراضي مع AsyncSession + PostgreSQL.

هذا الملف فئة مستقلة (ليس Mix-in) ويحتوي على:
    - إنشاء واسترجاع بيانات مالك أرض
    - إدارة الأراضي المملوكة (إعلان، استرجاع، حذف)
    - تحديث إحصائيات البيع والعمولات
    - نقل ملكية الأراضي بين الملاك

التزامن يُدار عبر row-level locks كما في InvestorStore.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.account.models import Landowner, OwnedLand

logger = logging.getLogger(__name__)


class LandownerStore:
    """
    مخزن ملاك الأراضي — يعمل مباشرة مع PostgreSQL عبر AsyncSession.

    التزامن يُدار عبر row-level locks كما في InvestorStore.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ─── إنشاء حساب مالك أرض ───

    async def create(
        self,
        user_id: str,
        full_name_ar: str = "",
        default_commission_pct: float = 2.5,
    ) -> Dict[str, Any]:
        """إنشاء حساب مالك أرض جديد."""
        if not (0 <= default_commission_pct <= 50):
            raise ValueError("نسبة العمولة يجب أن تكون بين 0% و 50%")

        # التحقق من عدم التكرار
        existing = await self.get(user_id)
        if existing:
            raise ValueError(f"مالك الأرض {user_id} مسجل مسبقاً")

        landowner = Landowner(
            user_id=user_id,
            default_commission_pct=float(default_commission_pct),
        )
        self.session.add(landowner)
        await self.session.flush()
        await self.session.refresh(landowner)

        logger.info(f"تم إنشاء حساب مالك أرض: {user_id} (عمولة: {default_commission_pct}%)")
        return landowner.to_dict()

    # ─── استرجاع بيانات ───

    async def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع بيانات مالك أرض."""
        stmt = select(Landowner).where(Landowner.user_id == user_id)
        result = await self.session.execute(stmt)
        lo = result.scalar_one_or_none()
        return lo.to_dict() if lo else None

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """استرجاع جميع ملاك الأراضي."""
        stmt = (
            select(Landowner)
            .order_by(Landowner.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [lo.to_dict() for lo in result.scalars().all()]

    async def exists(self, user_id: str) -> bool:
        """التحقق من وجود مالك."""
        stmt = select(func.count()).select_from(Landowner).where(Landowner.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar() > 0

    async def count(self) -> int:
        """عدد ملاك الأراضي المسجلين."""
        stmt = select(func.count()).select_from(Landowner)
        result = await self.session.execute(stmt)
        return result.scalar()

    # ─── إدارة الأراضي المملوكة ───

    async def list_land(self, user_id: str, land_data: Dict[str, Any]) -> Dict[str, Any]:
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

        # التحقق من المالك
        stmt = (
            select(Landowner)
            .where(Landowner.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        lo = result.scalar_one_or_none()
        if not lo:
            raise ValueError(f"مالك الأرض {user_id} غير موجود")

        # منع التكرار
        existing_stmt = (
            select(func.count())
            .select_from(OwnedLand)
            .where(
                OwnedLand.landowner_id == user_id,
                OwnedLand.land_id == land_id,
            )
        )
        existing_result = await self.session.execute(existing_stmt)
        if existing_result.scalar() > 0:
            raise ValueError(f"الأرض {land_id} مسجلة مسبقاً لدى هذا المالك")

        owned_land = OwnedLand(
            landowner_id=user_id,
            land_id=land_id,
            land_name=land_data.get("name", land_data.get("land_name", "")),
            governorate=land_data.get("governorate", ""),
            region_city=land_data.get("region_city", land_data.get("city", "")),
            total_area_sqm=int(land_data.get("total_area_sqm", land_data.get("area_sqm", 0)) or 0),
            price_per_sqm_egp=float(land_data.get("price_per_sqm_egp", 0) or 0),
            total_price_egp=float(land_data.get("total_price_egp", 0) or 0),
            investment_status=land_data.get("investment_status", "متاح"),
        )
        self.session.add(owned_land)

        # تحديث إحصائيات المالك
        lo.total_lands_listed += 1
        lo.active_lands_count += 1
        lo.updated_at = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(owned_land)

        logger.info(f"إعلان أرض {land_id} بواسطة المالك {user_id}")
        return owned_land.to_dict()

    async def get_lands(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """استرجاع أراضي المالك مع فلتر اختياري للحالة."""
        stmt = select(OwnedLand).where(OwnedLand.landowner_id == user_id)
        if status:
            stmt = stmt.where(OwnedLand.investment_status == status)
        stmt = stmt.order_by(OwnedLand.listed_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return [land.to_dict() for land in result.scalars().all()]

    async def get_land_by_id(self, user_id: str, land_id: str) -> Optional[Dict[str, Any]]:
        """استرجاع أرض محددة لمالك محدد."""
        stmt = (
            select(OwnedLand)
            .where(
                OwnedLand.landowner_id == user_id,
                OwnedLand.land_id == land_id,
            )
        )
        result = await self.session.execute(stmt)
        land = result.scalar_one_or_none()
        return land.to_dict() if land else None

    async def remove_land(self, user_id: str, land_id: str) -> bool:
        """حذف أرض من قائمة المالك (إلغاء الإعلان)."""
        stmt = (
            select(OwnedLand)
            .where(
                OwnedLand.landowner_id == user_id,
                OwnedLand.land_id == land_id,
            )
        )
        result = await self.session.execute(stmt)
        land = result.scalar_one_or_none()
        if not land:
            return False

        await self.session.delete(land)

        # تحديث العداد
        update_stmt = (
            update(Landowner)
            .where(Landowner.user_id == user_id)
            .values(
                active_lands_count=func.greatest(Landowner.active_lands_count - 1, 0),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(update_stmt)

        logger.info(f"حذف أرض {land_id} من قائمة المالك {user_id}")
        return True

    async def increment_views(self, user_id: str, land_id: str) -> None:
        """زيادة عداد المشاهدات لأرض محددة."""
        stmt = (
            update(OwnedLand)
            .where(
                OwnedLand.landowner_id == user_id,
                OwnedLand.land_id == land_id,
            )
            .values(views_count=OwnedLand.views_count + 1)
        )
        await self.session.execute(stmt)

    async def increment_inquiries(self, user_id: str, land_id: str) -> None:
        """زيادة عداد الاستفسارات لأرض محددة."""
        stmt = (
            update(OwnedLand)
            .where(
                OwnedLand.landowner_id == user_id,
                OwnedLand.land_id == land_id,
            )
            .values(inquiries_count=OwnedLand.inquiries_count + 1)
        )
        await self.session.execute(stmt)

    # ─── تحديث إحصائيات البيع ───

    async def record_sale(
        self,
        user_id: str,
        sale_amount: float,
        commission_pct: float,
    ) -> float:
        """تسجيل عملية بيع وتحديث إحصائيات المالك."""
        commission = sale_amount * (commission_pct / 100.0)

        stmt = (
            update(Landowner)
            .where(Landowner.user_id == user_id)
            .values(
                total_sales_egp=Landowner.total_sales_egp + sale_amount,
                total_commission_earned_egp=Landowner.total_commission_earned_egp + commission,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)

        logger.info(
            f"تسجيل بيع للمالك {user_id}: {sale_amount:,.2f} ج.م (عمولة: {commission:,.2f} ج.م)"
        )
        return commission

    async def update_commission(self, user_id: str, new_pct: float) -> Dict[str, Any]:
        """تحديث نسبة العمولة الافتراضية للمالك."""
        if not (0 <= new_pct <= 50):
            raise ValueError("نسبة العمولة يجب أن تكون بين 0% و 50%")

        stmt = (
            select(Landowner)
            .where(Landowner.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        lo = result.scalar_one_or_none()
        if not lo:
            raise ValueError(f"مالك الأرض {user_id} غير موجود")

        old_pct = lo.default_commission_pct
        lo.default_commission_pct = float(new_pct)
        lo.updated_at = datetime.now(timezone.utc)

        logger.info(f"تحديث عمولة المالك {user_id}: {old_pct}% → {new_pct}%")
        return lo.to_dict()

    # ─── نقل ملكية (داخلي) ───

    async def transfer_land_ownership(
        self,
        seller_id: str,
        land_id: str,
        buyer_id: str,
    ) -> bool:
        """
        نقل أرض من مالك لآخر (يُستدعى من transfer_ownership).

        يُحدث حالة الأرض إلى "مباع" ويُنقص عداد الأراضي النشطة للبائع.
        """
        # تحديث حالة الأرض
        stmt = (
            update(OwnedLand)
            .where(
                OwnedLand.landowner_id == seller_id,
                OwnedLand.land_id == land_id,
            )
            .values(
                investment_status="مباع",
                sold_at=datetime.now(timezone.utc),
                buyer_id=buyer_id,
            )
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            logger.warning(f"لم يُعثر على الأرض {land_id} لدى المالك {seller_id}")
            return False

        # إنقاص عداد الأراضي النشطة للبائع
        update_owner_stmt = (
            update(Landowner)
            .where(Landowner.user_id == seller_id)
            .values(
                active_lands_count=func.greatest(Landowner.active_lands_count - 1, 0),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(update_owner_stmt)

        return True
