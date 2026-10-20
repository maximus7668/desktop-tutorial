-- Borradores de contenido para redes. El sistema nunca publica en redes: una persona aprueba,
-- publica a mano y lo marca como publicado. link_path incluye utm_source para medir cada canal.
CREATE TABLE content_drafts (
    id           INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    channel      TEXT NOT NULL CHECK (channel IN ('tiktok','instagram','x','linkedin','grupo')),
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    link_path    TEXT NOT NULL,
    generator    TEXT NOT NULL,                 -- plantilla | llm:<modelo>
    checks       TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','rejected','published')),
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    decided_by   TEXT,
    decided_at   TEXT,
    published_url TEXT,
    published_at TEXT
);
CREATE INDEX content_product ON content_drafts(product_id, status);
