-- =============================================================================
-- Ledger Horizon — Migration 001: Schema Completo (self-contained)
-- Cria TODAS as tabelas do zero, na ordem correta de dependências.
-- Idempotente: seguro rodar múltiplas vezes (IF NOT EXISTS em tudo).
--
-- Comando: psql -U usr_pedro -d main_db -f 001_complete_profile_tables.sql
-- Ou via Docker: docker exec -i postgres_db psql -U usr_pedro -d main_db < 001_complete_profile_tables.sql
-- =============================================================================

-- Habilitar extensão UUID (necessária para gen_random_uuid())
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- BLOCO 1 — Tabela base: users
-- (criada automaticamente pelo app no boot, mas incluída aqui para
--  garantir existência antes das foreign keys)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    email                VARCHAR(255) UNIQUE NOT NULL,
    password_hash        TEXT,
    name                 VARCHAR(255) NOT NULL,
    auth_provider        VARCHAR(50)  DEFAULT 'local',
    google_sub           VARCHAR(255) UNIQUE,
    onboarding_completed BOOLEAN      DEFAULT FALSE,
    created_at           TIMESTAMPTZ  DEFAULT NOW(),
    last_login_at        TIMESTAMPTZ,
    -- colunas adicionadas pela migration
    user_type            TEXT         NOT NULL DEFAULT 'pf',
    marital_status       TEXT,
    dependents           INT          DEFAULT 0,
    work_regime          TEXT
);

-- Garantir colunas extras em users (caso a tabela já existia sem elas)
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at   TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS user_type        TEXT NOT NULL DEFAULT 'pf';
ALTER TABLE users ADD COLUMN IF NOT EXISTS marital_status   TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS dependents       INT DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS work_regime      TEXT;

-- =============================================================================
-- BLOCO 2 — Perfil financeiro (JSONB + colunas tipadas)
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_financial_profiles (
    id                   SERIAL PRIMARY KEY,
    user_id              INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    payload              JSONB NOT NULL,
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    -- colunas tipadas
    full_name            VARCHAR(255),
    age                  INTEGER,
    occupation           VARCHAR(255),
    city                 VARCHAR(255),
    monthly_income_net   NUMERIC(12,2) DEFAULT 0,
    monthly_income_gross NUMERIC(12,2) DEFAULT 0,
    extra_income         NUMERIC(12,2) DEFAULT 0,
    benefits_vr          NUMERIC(12,2) DEFAULT 0,
    saved_amount         NUMERIC(12,2) DEFAULT 0,
    saved_destination    VARCHAR(255),
    invests              VARCHAR(30),
    investment_types     TEXT[],
    risk_tolerance       VARCHAR(20),
    data_consent_given   BOOLEAN NOT NULL DEFAULT FALSE,
    data_consent_at      TIMESTAMPTZ
);

-- Garantir colunas tipadas em user_financial_profiles (caso tabela já existia)
ALTER TABLE user_financial_profiles
    ADD COLUMN IF NOT EXISTS full_name            VARCHAR(255),
    ADD COLUMN IF NOT EXISTS age                  INTEGER,
    ADD COLUMN IF NOT EXISTS occupation           VARCHAR(255),
    ADD COLUMN IF NOT EXISTS city                 VARCHAR(255),
    ADD COLUMN IF NOT EXISTS monthly_income_net   NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS monthly_income_gross NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS extra_income         NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS benefits_vr          NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS saved_amount         NUMERIC(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS saved_destination    VARCHAR(255),
    ADD COLUMN IF NOT EXISTS invests              VARCHAR(30),
    ADD COLUMN IF NOT EXISTS investment_types     TEXT[],
    ADD COLUMN IF NOT EXISTS risk_tolerance       VARCHAR(20),
    ADD COLUMN IF NOT EXISTS data_consent_given   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS data_consent_at      TIMESTAMPTZ;

-- =============================================================================
-- BLOCO 3 — Cache de consenso LLM
-- =============================================================================
CREATE TABLE IF NOT EXISTS llm_consensus_cache (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    allocation        JSONB NOT NULL,
    confidence_score  NUMERIC(5, 2) NOT NULL,
    risk_flags        JSONB NOT NULL,
    reasoning_summary TEXT NOT NULL,
    consensus_status  VARCHAR(50) NOT NULL,
    provider_metadata JSONB DEFAULT '{}'::jsonb,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE
);
ALTER TABLE llm_consensus_cache
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

-- =============================================================================
-- BLOCO 4 — Objetivos financeiros
-- =============================================================================
CREATE TABLE IF NOT EXISTS financial_goals (
    id                   SERIAL PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title                VARCHAR(255) NOT NULL,
    goal_type            VARCHAR(30)  NOT NULL,
    target_amount        NUMERIC(12,2),
    target_date          DATE,
    current_amount       NUMERIC(12,2) NOT NULL DEFAULT 0,
    monthly_contribution NUMERIC(12,2) NOT NULL DEFAULT 0,
    priority             INTEGER       NOT NULL DEFAULT 1,
    is_active            BOOLEAN       NOT NULL DEFAULT TRUE,
    notes                TEXT,
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_financial_goals_user ON financial_goals(user_id);

-- =============================================================================
-- BLOCO 5 — Categorias de despesa
-- =============================================================================
CREATE TABLE IF NOT EXISTS expense_categories (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       VARCHAR(100) NOT NULL,
    category   VARCHAR(50)  NOT NULL,
    icon       VARCHAR(10),
    color      VARCHAR(7),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, name)
);

-- =============================================================================
-- BLOCO 6 — Períodos mensais (budget_months)
-- =============================================================================
CREATE TABLE IF NOT EXISTS budget_months (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    year       INTEGER NOT NULL,
    month      INTEGER NOT NULL,
    label      VARCHAR(20),
    is_closed  BOOLEAN NOT NULL DEFAULT FALSE,
    notes      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, year, month)
);

-- =============================================================================
-- BLOCO 7 — Despesas
-- =============================================================================
CREATE TABLE IF NOT EXISTS expense_entries (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    budget_month_id     INTEGER NOT NULL REFERENCES budget_months(id) ON DELETE CASCADE,
    category_id         INTEGER REFERENCES expense_categories(id) ON DELETE SET NULL,
    description         VARCHAR(255) NOT NULL,
    amount              NUMERIC(12,2) NOT NULL,
    expense_type        VARCHAR(20) NOT NULL DEFAULT 'fixed',
    due_date            DATE,
    is_paid             BOOLEAN NOT NULL DEFAULT FALSE,
    paid_at             DATE,
    installment_current INTEGER,
    installment_total   INTEGER,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- BLOCO 8 — Receitas
-- =============================================================================
CREATE TABLE IF NOT EXISTS income_entries (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    budget_month_id INTEGER NOT NULL REFERENCES budget_months(id) ON DELETE CASCADE,
    description     VARCHAR(255) NOT NULL,
    amount          NUMERIC(12,2) NOT NULL,
    income_type     VARCHAR(20) NOT NULL DEFAULT 'salary',
    is_received     BOOLEAN NOT NULL DEFAULT FALSE,
    received_at     DATE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- BLOCO 9 — Portfólio de investimentos
-- =============================================================================
CREATE TABLE IF NOT EXISTS investment_portfolios (
    id                        SERIAL PRIMARY KEY,
    user_id                   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consensus_record_id       INTEGER REFERENCES llm_consensus_cache(id) ON DELETE SET NULL,
    generated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active                 BOOLEAN NOT NULL DEFAULT TRUE,
    pct_renda_fixa            NUMERIC(5,2) NOT NULL DEFAULT 0,
    pct_tesouro               NUMERIC(5,2) NOT NULL DEFAULT 0,
    pct_fiis                  NUMERIC(5,2) NOT NULL DEFAULT 0,
    pct_acoes                 NUMERIC(5,2) NOT NULL DEFAULT 0,
    pct_reserva_liquida       NUMERIC(5,2) NOT NULL DEFAULT 0,
    pct_cripto                NUMERIC(5,2) NOT NULL DEFAULT 0,
    monthly_investment_target NUMERIC(12,2) DEFAULT 0,
    emergency_reserve_target  NUMERIC(12,2) DEFAULT 0,
    months_to_goal            INTEGER,
    projection_json           JSONB,
    rationale                 TEXT
);

-- =============================================================================
-- BLOCO 10 — Respostas individuais de LLM
-- =============================================================================
CREATE TABLE IF NOT EXISTS llm_individual_responses (
    id           SERIAL PRIMARY KEY,
    consensus_id INTEGER NOT NULL REFERENCES llm_consensus_cache(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_name VARCHAR(50) NOT NULL,
    round_number  INTEGER NOT NULL DEFAULT 1,
    raw_response  JSONB NOT NULL,
    allocation    JSONB,
    confidence    NUMERIC(4,3),
    risk_flags    TEXT[],
    reasoning     TEXT,
    responded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- BLOCO 11 — Cartões de crédito (NOVO)
-- =============================================================================
CREATE TABLE IF NOT EXISTS credit_cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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

-- =============================================================================
-- BLOCO 12 — Contas bancárias (NOVO)
-- =============================================================================
CREATE TABLE IF NOT EXISTS bank_accounts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bank_name      TEXT NOT NULL,
    account_type   TEXT NOT NULL DEFAULT 'corrente',
    balance_approx NUMERIC(12,2) DEFAULT 0,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bank_accounts_user ON bank_accounts(user_id);

-- =============================================================================
-- BLOCO 13 — Dívidas ativas (NOVO)
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_debts (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    description            TEXT NOT NULL,
    debt_type              TEXT NOT NULL,
    total_amount           NUMERIC(12,2) NOT NULL,
    monthly_payment        NUMERIC(12,2) NOT NULL,
    installments_remaining INT,
    interest_rate_monthly  NUMERIC(6,4),
    credit_score_approx    TEXT,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_user_debts_user ON user_debts(user_id);

-- =============================================================================
-- BLOCO 14 — Patrimônio & bens (NOVO)
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_assets (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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

-- =============================================================================
-- BLOCO 15 — Despesas variáveis médias (NOVO)
-- =============================================================================
CREATE TABLE IF NOT EXISTS variable_expense_averages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    monthly_avg NUMERIC(12,2) NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, category)
);
CREATE INDEX IF NOT EXISTS ix_var_exp_avg_user ON variable_expense_averages(user_id);

-- =============================================================================
-- BLOCO 16 — Perfil PJ (NOVO)
-- =============================================================================
CREATE TABLE IF NOT EXISTS pj_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    cnpj                TEXT,
    regime_tributario   TEXT,
    business_type       TEXT,
    monthly_revenue_avg NUMERIC(12,2),
    prolabore           NUMERIC(12,2),
    payroll_total       NUMERIC(12,2),
    tax_monthly         NUMERIC(12,2),
    operational_costs   NUMERIC(12,2),
    partner_count       INT DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- FIM
-- Execute e verifique: SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;
-- Deve listar todas as tabelas acima.
-- =============================================================================
