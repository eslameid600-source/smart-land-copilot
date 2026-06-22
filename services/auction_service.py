"""services.auction_service — facade re-exporting from core.auction.engine.

Also exposes:
    - AuctionEngine, engine (from core.auction.engine)
    - CommissionCalculator (stub class with compute_for_direct_sale class-method)
"""

from typing import Any, Dict

from core.auction.engine import AuctionEngine, engine  # noqa: F401


class CommissionCalculator:
    """Stub commission calculator for land sales.

    Real implementation should integrate with the broker_delegation_service
    and the actual commission rules.
    """

    @classmethod
    def compute_for_direct_sale(
        cls,
        land: Dict[str, Any],
        scout_name: str = "",
        scout_eligible: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Compute commission breakdown for a direct (non-auction) sale.

        Returns a dict with:
            - sale_price_egp
            - broker_commission_egp
            - platform_fee_egp
            - scout_fee_egp
            - net_to_seller_egp
        """
        sale_price = float(land.get("total_price_egp", 0) or 0)
        commission_pct = float(land.get("commission_pct", 2.5) or 2.5)
        platform_pct = 0.5  # 0.5% platform fee
        scout_pct = 1.0 if scout_eligible else 0.0

        broker_commission = round(sale_price * commission_pct / 100, 2)
        platform_fee = round(sale_price * platform_pct / 100, 2)
        scout_fee = round(sale_price * scout_pct / 100, 2)
        net_to_seller = round(sale_price - broker_commission - platform_fee - scout_fee, 2)

        return {
            "sale_price_egp": sale_price,
            "broker_commission_egp": broker_commission,
            "platform_fee_egp": platform_fee,
            "scout_fee_egp": scout_fee,
            "scout_name": scout_name,
            "net_to_seller_egp": net_to_seller,
            "breakdown": [
                {"label": "سعر البيع", "amount": sale_price, "type": "credit"},
                {"label": "عمولة الوسيط", "amount": -broker_commission, "type": "debit"},
                {"label": "رسوم المنصة", "amount": -platform_fee, "type": "debit"},
                {"label": "رسوم الكشاف", "amount": -scout_fee, "type": "debit"},
                {"label": "صافي البائع", "amount": net_to_seller, "type": "net"},
            ],
        }


__all__ = ["AuctionEngine", "engine", "CommissionCalculator"]
