"""add payment tables — payment_transactions, idempotency_keys

Revision ID: 002_payment_tables
Revises: 001_initial
Create Date: 2026-06-17

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = '002_payment_tables'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ═══════ 1. جدول معاملات الدفع ═══════
    op.create_table(
        'payment_transactions',
        sa.Column('id', sa.String(36), primary_key=True, comment='UUID داخلي'),
        sa.Column('transaction_id', sa.String(40), unique=True, nullable=False, index=True,
                  comment='معرّف المعاملة العام TXN-XXXXXXXX'),
        sa.Column('land_id', sa.String(50), nullable=False, index=True,
                  comment='معرّف الأرض'),
        sa.Column('buyer_id', sa.String(100), nullable=False, index=True,
                  comment='معرّف المشتري'),
        sa.Column('seller_id', sa.String(100), nullable=False, index=True,
                  comment='معرّف البائع'),
        sa.Column('amount', sa.Float(precision=2), nullable=False,
                  comment='المبلغ الأساسي'),
        sa.Column('currency', sa.String(10), nullable=False, server_default='EGP'),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending', index=True),
        sa.Column('gateway_type', sa.String(30), nullable=False, server_default='fawry'),
        sa.Column('transaction_type', sa.String(30), nullable=False, server_default='purchase'),
        sa.Column('gateway_ref', sa.String(200), nullable=True),
        sa.Column('gateway_response', sa.Text(), nullable=True, comment='JSON'),
        sa.Column('buyer_balance_before', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('buyer_balance_after', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('seller_balance_before', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('seller_balance_after', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True, comment='JSON'),
        sa.Column('refunded_amount', sa.Float(precision=2), nullable=False, server_default='0.0'),
        sa.Column('refund_refs_json', sa.Text(), nullable=True, comment='JSON array'),
        sa.Column('loyalty_points_earned', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('amount > 0', name='ck_payment_amount_positive'),
        sa.CheckConstraint('refunded_amount >= 0', name='ck_payment_refund_non_negative'),
        sa.CheckConstraint('loyalty_points_earned >= 0', name='ck_payment_loyalty_non_negative'),
    )
    op.create_index('ix_payment_buyer_status', 'payment_transactions', ['buyer_id', 'status'])
    op.create_index('ix_payment_seller_status', 'payment_transactions', ['seller_id', 'status'])
    op.create_index('ix_payment_land', 'payment_transactions', ['land_id'])

    # ═══════ 2. جدول مفاتيح حماية التكرار ═══════
    op.create_table(
        'idempotency_keys',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('key', sa.String(200), unique=True, nullable=False, index=True,
                  comment='مفتاح idempotency الفريد'),
        sa.Column('transaction_id', sa.String(40), nullable=True,
                  comment='معرّف المعاملة المرتبطة'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_idempotency_key_lookup', 'idempotency_keys', ['key'])


def downgrade() -> None:
    op.drop_table('idempotency_keys')
    op.drop_table('payment_transactions')