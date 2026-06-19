-- ============================================================
-- Smart Land Management Copilot V4.0
-- نظام الدفع والحسابات المتخصصة
-- SQL Schema Migration
-- ============================================================

-- -----------------------------------------------------------
-- 1. جدول المعاملات المالية (transactions)
-- -----------------------------------------------------------
CREATE TABLE transactions (
    transaction_id   VARCHAR(36)      PRIMARY KEY DEFAULT gen_random_uuid(),
    land_id          VARCHAR(20)      NOT NULL REFERENCES lands(land_id),
    buyer_id         VARCHAR(36)      NOT NULL REFERENCES users(user_id),
    seller_id        VARCHAR(36)      NOT NULL REFERENCES users(user_id),
    amount_egp       DECIMAL(18,2)    NOT NULL CHECK (amount_egp > 0),
    platform_fee_egp DECIMAL(18,2)    DEFAULT 0,
    tax_amount_egp   DECIMAL(18,2)    DEFAULT 0,
    status           VARCHAR(20)      NOT NULL DEFAULT 'Pending'
                     CHECK (status IN
                       ('Pending','Completed','Failed','Refunded')),
    payment_method   VARCHAR(30)      NOT NULL DEFAULT 'fawry'
                     CHECK (payment_method IN
                       ('fawry','stripe','paypal')),
    gateway_ref      VARCHAR(255)     DEFAULT NULL,
    created_at       TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ      NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ      DEFAULT NULL
);

CREATE INDEX idx_transactions_buyer   ON transactions(buyer_id);
CREATE INDEX idx_transactions_seller  ON transactions(seller_id);
CREATE INDEX idx_transactions_status  ON transactions(status);
CREATE INDEX idx_transactions_created ON transactions(created_at);

-- -----------------------------------------------------------
-- 2. جدول حساب المستثمر (investors)
-- -----------------------------------------------------------
CREATE TABLE investors (
    user_id               VARCHAR(36)    PRIMARY KEY REFERENCES users(user_id),
    wallet_balance_egp    DECIMAL(18,2)  NOT NULL DEFAULT 0
                          CHECK (wallet_balance_egp >= 0),
    total_lands_purchased INTEGER       NOT NULL DEFAULT 0,
    total_invested_egp    DECIMAL(18,2)  NOT NULL DEFAULT 0,
    loyalty_points        INTEGER       NOT NULL DEFAULT 0,
    discount_rate_pct     DECIMAL(5,2)   NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- 3. سجل الاستثمار (investment_history)
-- -----------------------------------------------------------
CREATE TABLE investment_history (
    history_id       VARCHAR(36)    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          VARCHAR(36)    NOT NULL REFERENCES investors(user_id),
    land_id          VARCHAR(20)    NOT NULL REFERENCES lands(land_id),
    transaction_id   VARCHAR(36)    REFERENCES transactions(transaction_id),
    purchase_price   DECIMAL(18,2)  NOT NULL,
    points_earned    INTEGER       NOT NULL DEFAULT 0,
    discount_applied DECIMAL(5,2)   NOT NULL DEFAULT 0,
    purchased_at     TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX idx_investments_user ON investment_history(user_id);
CREATE INDEX idx_investments_land ON investment_history(land_id);

-- -----------------------------------------------------------
-- 4. جدول صاحب الأرض (landowners)
-- -----------------------------------------------------------
CREATE TABLE landowners (
    user_id           VARCHAR(36)    PRIMARY KEY REFERENCES users(user_id),
    total_sales_egp   DECIMAL(18,2)  NOT NULL DEFAULT 0,
    total_lands_listed INTEGER       NOT NULL DEFAULT 0,
    total_lands_sold  INTEGER       NOT NULL DEFAULT 0,
    default_broker_commission_pct DECIMAL(5,2) NOT NULL DEFAULT 2.5,
    bank_account_ref  VARCHAR(100)  DEFAULT NULL,
    created_at        TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- 5. جدول إعدادات العمولة لكل أرض (land_commission_settings)
-- -----------------------------------------------------------
CREATE TABLE land_commission_settings (
    setting_id       VARCHAR(36)    PRIMARY KEY DEFAULT gen_random_uuid(),
    land_id          VARCHAR(20)    UNIQUE REFERENCES lands(land_id),
    owner_id         VARCHAR(36)    REFERENCES landowners(user_id),
    broker_commission_pct DECIMAL(5,2) NOT NULL DEFAULT 2.5
                          CHECK (broker_commission_pct BETWEEN 0 AND 10),
    platform_commission_pct DECIMAL(5,2) NOT NULL DEFAULT 1.5
                          CHECK (platform_commission_pct BETWEEN 0 AND 5),
    updated_at       TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- 6. جدول سجل نقاط الولاء (loyalty_points_log)
-- -----------------------------------------------------------
CREATE TABLE loyalty_points_log (
    log_id         VARCHAR(36)    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        VARCHAR(36)    NOT NULL REFERENCES investors(user_id),
    transaction_id VARCHAR(36)    REFERENCES transactions(transaction_id),
    points_earned  INTEGER       NOT NULL DEFAULT 0,
    points_used    INTEGER       NOT NULL DEFAULT 0,
    reason         VARCHAR(100)   NOT NULL,
    created_at     TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX idx_loyalty_user ON loyalty_points_log(user_id);