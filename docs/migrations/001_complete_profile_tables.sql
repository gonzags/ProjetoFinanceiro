-- =============================================================================
-- Ledger Horizon — Migration 001: Complete Financial Profile Tables
-- Rodar manualmente no Postgres ANTES do próximo deploy
-- Comando: psql -U usr_pedro -d main_db -f 001_complete_profile_tables.sql
-- =============================================================================

-- Cartões de Crédito
CREATE TABLE IF NOT EXISTS credit_cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    bank            TEXT,
    closing_day     INT NOT NULL CHECK (closing_day BETWEEN 1 AND 31),
    due_day         INT NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    credit_limit    NUMERIC(12,2) DEFAULT 0,
    current_balance NUMERIC(12,2) DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_credit_cards_user ON credit_cards(user_id);

-- Contas Bancárias
CREATE TABLE IF NOT EXISTS bank_accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bank_name       TEXT NOT NULL,
    account_type    TEXT NOT NULL DEFAULT 'corrente',
    balance_approx  NUMERIC(12,2) DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bank_accounts_user ON bank_accounts(user_id);

-- Dívidas Ativas
CREATE TABLE IF NOT EXISTS user_debts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    description             TEXT NOT NULL,
    debt_type               TEXT NOT NULL,
    total_amount            NUMERIC(12,2) NOT NULL,
    monthly_payment         NUMERIC(12,2) NOT NULL,
    installments_remaining  INT,
    interest_rate_monthly   NUMERIC(6,4),
    credit_score_approx     TEXT,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_user_debts_user ON user_debts(user_id);

-- Patrimônio & Bens
CREATE TABLE IF NOT EXISTS user_assets (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_type             TEXT NOT NULL,
    description            TEXT,
    estimated_value        NUMERIC(12,2),
    financed_value         NUMERIC(12,2),
    monthly_payment        NUMERIC(12,2),
    installments_remaining INT,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_user_assets_user ON user_assets(user_id);

-- Médias de Despesas Variáveis (por categoria, 1 linha por user_id+category)
CREATE TABLE IF NOT EXISTS variable_expense_averages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    monthly_avg NUMERIC(12,2) NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, category)
);
CREATE INDEX IF NOT EXISTS ix_var_exp_avg_user ON variable_expense_averages(user_id);

-- Dados PJ (1 linha por usuário)
CREATE TABLE IF NOT EXISTS pj_profiles (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    cnpj                 TEXT,
    regime_tributario    TEXT,
    business_type        TEXT,
    monthly_revenue_avg  NUMERIC(12,2),
    prolabore            NUMERIC(12,2),
    payroll_total        NUMERIC(12,2),
    tax_monthly          NUMERIC(12,2),
    operational_costs    NUMERIC(12,2),
    partner_count        INT DEFAULT 1,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Colunas extras na tabela users (se ainda não existirem)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS user_type        TEXT NOT NULL DEFAULT 'pf',
    ADD COLUMN IF NOT EXISTS marital_status   TEXT,
    ADD COLUMN IF NOT EXISTS dependents       INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS work_regime      TEXT;
