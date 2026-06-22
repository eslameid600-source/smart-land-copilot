"""create account tables — investors, landowners, owned_lands, wallet_transactions

Revision ID: 001_initial
Revises: None
Create Date: 2026-06-16

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ═══════ 1. جدول المستثمرين ═══════
    op.create_table(
        'investors',
        sa.Column('id', sa.String(36), primary_key=True, comment='UUID فريد'),
        sa.Column('user_id', sa.String(100), unique=True, nullable=False, index=True,
                  comment='معرّف المستخدم من خدمة المصادقة'),
        sa.Column('full_name_ar', sa.String(200), nullable=True),
        sa.Column('wallet_balance_egp', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('frozen_balance_egp', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('total_spent_egp', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('loyalty_points', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_lands_purchased', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('wallet_balance_egp >= 0', name='ck_investor_wallet_non_negative'),
        sa.CheckConstraint('frozen_balance_egp >= 0', name='ck_investor_frozen_non_negative'),
        sa.CheckConstraint('loyalty_points >= 0', name='ck_investor_loyalty_non_negative'),
        sa.CheckConstraint('total_lands_purchased >= 0', name='ck_investor_purchased_non_negative'),
    )
    op.create_index('ix_investor_wallet', 'investors', ['wallet_balance_egp'])

    # ═══════ 2. جدول ملاك الأراضي ═══════
    op.create_table(
        'landowners',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('full_name_ar', sa.String(200), nullable=True),
        sa.Column('total_sales_egp', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('total_lands_listed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active_lands_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('default_commission_pct', sa.Float(precision=2), nullable=False, server_default='2.5'),
        sa.Column('total_commission_earned_egp', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            'default_commission_pct >= 0 AND default_commission_pct <= 50',
            name='ck_landowner_commission_range',
        ),
        sa.CheckConstraint('total_sales_egp >= 0', name='ck_landowner_sales_non_negative'),
        sa.CheckConstraint('active_lands_count >= 0', name='ck_landowner_active_non_negative'),
    )

    # ═══════ 3. جدول الأراضي المملوكة ═══════
    op.create_table(
        'owned_lands',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('landowner_id', sa.String(100), sa.ForeignKey('landowners.user_id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('land_id', sa.String(50), nullable=False, index=True),
        sa.Column('land_name', sa.String(300), nullable=True),
        sa.Column('governorate', sa.String(100), nullable=True),
        sa.Column('investment_status', sa.String(50), nullable=True, server_default='متاح'),
        sa.Column('views_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('inquiries_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sold_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('buyer_id', sa.String(100), nullable=True),
        sa.Column('sale_price_egp', sa.Float(precision=2), nullable=True),
        sa.Column('listed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('landowner_id', 'land_id', name='uq_owned_land_unique'),
    )
    op.create_index('ix_owned_lands_status', 'owned_lands', ['investment_status'])

    # ═══════ 4. جدول معاملات المحفظة ═══════
    op.create_table(
        'wallet_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tx_id', sa.String(40), unique=True, nullable=False, index=True),
        sa.Column('investor_id', sa.String(100), sa.ForeignKey('investors.user_id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('tx_type', sa.String(30), nullable=False, index=True),
        sa.Column('amount_egp', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('balance_after_egp', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('description_ar', sa.Text(), nullable=False, server_default=''),
        sa.Column('reference_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
                  index=True),
    )
    op.create_index('ix_wallet_tx_investor_type', 'wallet_transactions',
                     ['investor_id', 'tx_type'])


def downgrade() -> None:
    op.drop_table('wallet_transactions')
    op.drop_table('owned_lands')
    op.drop_table('landowners')
    op.drop_table('investors')