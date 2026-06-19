"""001_add_broker_and_verification

إضافة جداول نظام الوسطاء والتحقق:
- users
- investors
- landowners
- owned_lands
- brokers
- broker_assignments
- broker_transactions
- land_documents
- land_gps_logs
- wallet_transactions
- landowner_transactions
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_add_broker_and_verification"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Users ──
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(36), nullable=False, unique=True, index=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("phone_number", sa.String(20), nullable=True),
        sa.Column("role", sa.String(30), nullable=False, server_default="Seller/Owner"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_verification"),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── Investors ──
    op.create_table(
        "investors",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("wallet_balance_egp", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("frozen_balance_egp", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("loyalty_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_lands_purchased", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_spent_egp", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("investment_budget_max_egp", sa.Numeric(18, 2), nullable=True),
        sa.Column("preferred_governorates", sa.JSON, nullable=True),
        sa.Column("preferred_usages", sa.JSON, nullable=True),
        sa.Column("watchlist_land_ids", sa.JSON, nullable=True),
        sa.Column("portfolio_land_ids", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── Landowners ──
    op.create_table(
        "landowners",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("default_commission_pct", sa.Numeric(5, 2), nullable=False, server_default="2.5"),
        sa.Column("total_lands_listed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active_lands_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_sales_egp", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_commission_earned_egp", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── Owned Lands ──
    op.create_table(
        "owned_lands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("landowner_id", sa.String(36), sa.ForeignKey("landowners.user_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("land_id", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("land_name", sa.String(200), nullable=False),
        sa.Column("governorate", sa.String(100), nullable=False),
        sa.Column("region_city", sa.String(100), nullable=False),
        sa.Column("total_area_sqm", sa.Integer, nullable=False),
        sa.Column("price_per_sqm_egp", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_price_egp", sa.Numeric(18, 2), nullable=False),
        sa.Column("investment_status", sa.String(50), nullable=False, server_default="متاح"),
        sa.Column("listing_intent", sa.String(50), nullable=False, server_default="Sale"),
        sa.Column("description_ar", sa.Text, nullable=True),
        sa.Column("images", sa.JSON, nullable=True),
        sa.Column("broker_id", sa.String(36), nullable=True, index=True),
        sa.Column("commission_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("verification_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("seller_id_card", sa.String(50), nullable=True),
        sa.Column("listed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("views_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("inquiries_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("buyer_id", sa.String(36), nullable=True),
        sa.CheckConstraint("price_per_sqm_egp > 0", name="ck_land_price_positive"),
        sa.CheckConstraint("total_area_sqm > 0", name="ck_land_area_positive"),
        sa.CheckConstraint("total_price_egp > 0", name="ck_land_total_price_positive"),
    )

    # ── Brokers ──
    op.create_table(
        "brokers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(36), nullable=False, unique=True, index=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("license_number", sa.String(100), nullable=True),
        sa.Column("default_commission_rate", sa.Numeric(5, 2), nullable=False, server_default="2.5"),
        sa.Column("broker_code", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("specialization", sa.JSON, nullable=True),
        sa.Column("total_deals_closed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_commission_earned_egp", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("rating_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("rating_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="inactive"),
        sa.Column("verified_by_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint("default_commission_rate BETWEEN 1 AND 20", name="ck_broker_commission_range"),
        sa.CheckConstraint("default_commission_rate >= 0", name="ck_broker_commission_nonneg"),
        sa.CheckConstraint("total_deals_closed >= 0", name="ck_broker_deals_nonneg"),
    )

    # ── Broker Assignments ──
    op.create_table(
        "broker_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("land_id", sa.String(50), sa.ForeignKey("owned_lands.land_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("broker_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("commission_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Broker Transactions ──
    op.create_table(
        "broker_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("broker_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("transaction_id", sa.String(100), nullable=True, index=True),
        sa.Column("land_id", sa.String(50), nullable=True, index=True),
        sa.Column("sale_amount_egp", sa.Numeric(18, 2), nullable=False),
        sa.Column("commission_rate_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("commission_amount_egp", sa.Numeric(18, 2), nullable=False),
        sa.Column("platform_fee_egp", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("net_commission_egp", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint("sale_amount_egp > 0", name="ck_broker_tx_sale_positive"),
        sa.CheckConstraint("commission_rate_pct >= 0", name="ck_broker_tx_rate_nonneg"),
    )

    # ── Land Documents ──
    op.create_table(
        "land_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("land_id", sa.String(50), sa.ForeignKey("owned_lands.land_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("file_size_kb", sa.Integer, nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("id_card_number", sa.String(50), nullable=True),
        sa.Column("uploaded_by", sa.String(36), nullable=False),
        sa.Column("verified_by_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("verified_by_admin_id", sa.String(36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_notes", sa.Text, nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Land GPS Logs ──
    op.create_table(
        "land_gps_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("land_id", sa.String(50), sa.ForeignKey("owned_lands.land_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("accuracy_meters", sa.Float, nullable=True),
        sa.Column("altitude_meters", sa.Float, nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="manual_entry"),
        sa.Column("recorded_by", sa.String(36), nullable=False),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("verification_note", sa.Text, nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Wallet Transactions ──
    op.create_table(
        "wallet_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("investor_id", sa.String(36), sa.ForeignKey("investors.user_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tx_type", sa.String(50), nullable=False),
        sa.Column("amount_egp", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("reference_id", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Landowner Transactions ──
    op.create_table(
        "landowner_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("landowner_id", sa.String(36), sa.ForeignKey("landowners.user_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("transaction_type", sa.String(50), nullable=False),
        sa.Column("amount_egp", sa.Numeric(18, 2), nullable=False),
        sa.Column("land_id", sa.String(50), nullable=True),
        sa.Column("reference_id", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("landowner_transactions")
    op.drop_table("wallet_transactions")
    op.drop_table("land_gps_logs")
    op.drop_table("land_documents")
    op.drop_table("broker_transactions")
    op.drop_table("broker_assignments")
    op.drop_table("brokers")
    op.drop_table("owned_lands")
    op.drop_table("landowners")
    op.drop_table("investors")
    op.drop_table("users")