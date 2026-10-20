-- Esquema inicial. Todas las cantidades de dinero en céntimos de euro (INTEGER) para evitar
-- errores de redondeo. data_kind distingue siempre: real | estimate | simulation.

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);

CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE agents (
    name        TEXT PRIMARY KEY,
    role        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'idle',   -- idle | running | error | stopped
    last_run_at TEXT,
    last_error  TEXT
);

-- policy: allow | approval | deny. Sin fila = deny.
CREATE TABLE permissions (
    agent        TEXT NOT NULL,
    tool         TEXT NOT NULL,
    action       TEXT NOT NULL,
    policy       TEXT NOT NULL CHECK (policy IN ('allow','approval','deny')),
    daily_limit  INTEGER,                        -- nº máximo de usos al día (NULL = sin límite)
    updated_at   TEXT NOT NULL,
    updated_by   TEXT NOT NULL,
    PRIMARY KEY (agent, tool, action)
);

-- Registro de auditoría encadenado por hash. No se puede modificar ni borrar.
CREATE TABLE audit_log (
    id         INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL,
    actor_kind TEXT NOT NULL CHECK (actor_kind IN ('agent','human','system','public')),
    action     TEXT NOT NULL,
    target     TEXT,
    details    TEXT NOT NULL DEFAULT '{}',
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL
);
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log es de solo inserción'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log es de solo inserción'); END;

CREATE TABLE approvals (
    id           INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL,          -- spend | experiment.start | product.publish | commerce.enable | action
    ref_table    TEXT,
    ref_id       INTEGER,
    requested_by TEXT NOT NULL,
    summary      TEXT NOT NULL,
    payload      TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','expired')),
    decided_by   TEXT,
    decided_at   TEXT,
    note         TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX approvals_status ON approvals(status);

-- Solicitudes de gasto. El importe reservado cuenta contra el presupuesto desde que se pide.
CREATE TABLE spend_requests (
    id              INTEGER PRIMARY KEY,
    agent           TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN ('api','tool','ads','service','other')),
    amount_cents    INTEGER NOT NULL CHECK (amount_cents > 0),
    actual_cents    INTEGER,
    description     TEXT NOT NULL,
    experiment_id   INTEGER,
    status          TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','executing','executed','failed','cancelled')),
    reason          TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    approval_id     INTEGER,
    authorized_by   TEXT,
    created_at      TEXT NOT NULL,
    decided_at      TEXT,
    executed_at     TEXT
);
CREATE INDEX spend_status ON spend_requests(status);

-- Libro contable. Ingresos solo desde pedidos verificados; gastos desde spend_requests.
CREATE TABLE ledger (
    id               INTEGER PRIMARY KEY,
    ts               TEXT NOT NULL,
    kind             TEXT NOT NULL CHECK (kind IN ('capital','expense','revenue','refund','fee')),
    amount_cents     INTEGER NOT NULL,
    data_kind        TEXT NOT NULL CHECK (data_kind IN ('real','estimate','simulation')),
    category         TEXT,
    source           TEXT NOT NULL,
    spend_request_id INTEGER,
    order_id         INTEGER,
    notes            TEXT
);

CREATE TABLE opportunities (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    segment     TEXT,
    product_idea TEXT,
    price_hint_cents INTEGER,
    inputs      TEXT NOT NULL DEFAULT '{}',   -- estimaciones del investigador (data_kind=estimate)
    score       REAL,
    score_breakdown TEXT,
    status      TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','evaluated','selected','testing','validated','abandoned')),
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    research_run TEXT
);

CREATE TABLE evidence (
    id             INTEGER PRIMARY KEY,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    url            TEXT NOT NULL,
    title          TEXT NOT NULL,
    publisher      TEXT,
    retrieved_at   TEXT NOT NULL,
    excerpt        TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('demand','willingness_to_pay','competition','price','pain','regulation','other')),
    reliability    TEXT NOT NULL CHECK (reliability IN ('high','medium','low')),
    verified       INTEGER NOT NULL DEFAULT 0  -- 1 = URL comprobada en resultados reales de búsqueda/descarga
);

CREATE TABLE experiments (
    id                 INTEGER PRIMARY KEY,
    opportunity_id     INTEGER NOT NULL REFERENCES opportunities(id),
    hypothesis         TEXT NOT NULL,
    design             TEXT NOT NULL,
    max_budget_cents   INTEGER NOT NULL,
    success_metric     TEXT NOT NULL,
    success_threshold  REAL NOT NULL,
    min_visits         INTEGER NOT NULL,
    duration_days      INTEGER NOT NULL,
    status             TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','running','completed','abandoned')),
    criteria_locked_at TEXT,
    started_at         TEXT,
    ends_at            TEXT,
    result             TEXT,
    verdict            TEXT,
    decision           TEXT CHECK (decision IN ('continue','modify','abandon') OR decision IS NULL),
    conclusion         TEXT,
    created_by         TEXT NOT NULL,
    created_at         TEXT NOT NULL
);
-- Los criterios de éxito no pueden cambiarse una vez fijados (evita mover la portería).
CREATE TRIGGER experiments_lock BEFORE UPDATE OF success_metric, success_threshold, min_visits, max_budget_cents ON experiments
WHEN OLD.criteria_locked_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'criterios del experimento bloqueados'); END;

CREATE TABLE products (
    id            INTEGER PRIMARY KEY,
    experiment_id INTEGER REFERENCES experiments(id),
    name          TEXT NOT NULL,
    slug          TEXT NOT NULL UNIQUE,
    kind          TEXT NOT NULL DEFAULT 'landing',
    status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','tested','failed_checks','published','retired')),
    price_cents   INTEGER,
    content       TEXT NOT NULL DEFAULT '{}',
    html          TEXT,
    checks        TEXT,
    payment_link  TEXT,
    created_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    published_at  TEXT
);

-- Analítica propia sin cookies: visitor_hash = sha256(sal diaria + IP + UA), no se guarda la IP.
CREATE TABLE events (
    id           INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    ts           TEXT NOT NULL,
    type         TEXT NOT NULL CHECK (type IN ('visit','signup','checkout_click','purchase','inquiry')),
    visitor_hash TEXT,
    source       TEXT,
    data_kind    TEXT NOT NULL CHECK (data_kind IN ('real','estimate','simulation'))
);
CREATE INDEX events_product ON events(product_id, type, ts);

CREATE TABLE signups (
    id           INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    email        TEXT NOT NULL,
    consent_text TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    data_kind    TEXT NOT NULL,
    UNIQUE (product_id, email)
);

CREATE TABLE orders (
    id           INTEGER PRIMARY KEY,
    product_id   INTEGER REFERENCES products(id),
    provider     TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'eur',
    status       TEXT NOT NULL CHECK (status IN ('paid','refunded','failed')),
    data_kind    TEXT NOT NULL CHECK (data_kind IN ('real','simulation')),
    created_at   TEXT NOT NULL,
    UNIQUE (provider, external_id)
);

CREATE TABLE inquiries (
    id         INTEGER PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    contact    TEXT,
    message    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','answered_draft','escalated','closed')),
    reply      TEXT,
    created_at TEXT NOT NULL,
    data_kind  TEXT NOT NULL
);

CREATE TABLE tasks (
    id              INTEGER PRIMARY KEY,
    type            TEXT NOT NULL,
    agent           TEXT NOT NULL,
    payload         TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','done','failed','cancelled')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    idempotency_key TEXT NOT NULL UNIQUE,
    run_after       TEXT NOT NULL,
    lease_until     TEXT,
    result          TEXT,
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX tasks_ready ON tasks(status, run_after);

CREATE TABLE schedules (
    name             TEXT PRIMARY KEY,
    task_type        TEXT NOT NULL,
    agent            TEXT NOT NULL,
    payload          TEXT NOT NULL DEFAULT '{}',
    interval_seconds INTEGER NOT NULL,
    next_run_at      TEXT NOT NULL,
    enabled          INTEGER NOT NULL DEFAULT 1
);

-- Memoria persistente revisable: lecciones, decisiones, errores, notas.
CREATE TABLE memory (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL CHECK (kind IN ('lesson','decision','error','note','research')),
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    ref        TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE alerts (
    id         INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    level      TEXT NOT NULL CHECK (level IN ('info','warning','critical')),
    message    TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE integration_status (
    name        TEXT PRIMARY KEY,
    configured  INTEGER NOT NULL,
    tested_at   TEXT,
    test_ok     INTEGER,
    message     TEXT,
    permissions TEXT NOT NULL DEFAULT ''
);

CREATE TABLE llm_usage (
    id            INTEGER PRIMARY KEY,
    ts            TEXT NOT NULL,
    agent         TEXT NOT NULL,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_cents    INTEGER NOT NULL,
    data_kind     TEXT NOT NULL
);

CREATE TABLE compliance_items (
    key         TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    required_for TEXT NOT NULL,          -- publish | commerce
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','not_applicable')),
    confirmed_by TEXT,
    confirmed_at TEXT,
    note        TEXT
);

CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
