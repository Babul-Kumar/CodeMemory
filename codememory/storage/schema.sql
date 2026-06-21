PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- ─── Files ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT UNIQUE NOT NULL,
    language     TEXT,
    hash         TEXT,
    last_indexed REAL,
    size_bytes   INTEGER,
    summary      TEXT,
    metadata     TEXT        -- JSON blob for arbitrary extra fields
);

-- ─── Symbols ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS symbols (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id   INTEGER REFERENCES files(id) ON DELETE CASCADE,
    name      TEXT    NOT NULL,
    kind      TEXT    NOT NULL,     -- class | function | method | import | variable
    signature TEXT,
    docstring TEXT,
    start_line INTEGER,
    end_line   INTEGER,
    parent_id  INTEGER REFERENCES symbols(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_symbols_file_id ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_name    ON symbols(name);

-- ─── Relationships ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS relationships (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    from_file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    to_file_id   INTEGER REFERENCES files(id) ON DELETE CASCADE,
    from_symbol  TEXT,
    to_symbol    TEXT,
    rel_type     TEXT    -- imports | calls | inherits | uses | exports
);

CREATE INDEX IF NOT EXISTS idx_rel_from ON relationships(from_file_id);
CREATE INDEX IF NOT EXISTS idx_rel_to   ON relationships(to_file_id);

-- ─── Project-level key-value metadata ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS project_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- ─── Full-text search virtual tables ─────────────────────────────────────────
CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    name,
    docstring,
    signature,
    content='symbols',
    content_rowid='id'
);

-- Trigger to keep FTS in sync with symbols table
CREATE TRIGGER IF NOT EXISTS symbols_ai AFTER INSERT ON symbols BEGIN
    INSERT INTO symbols_fts(rowid, name, docstring, signature)
    VALUES (new.id, new.name, new.docstring, new.signature);
END;

CREATE TRIGGER IF NOT EXISTS symbols_ad AFTER DELETE ON symbols BEGIN
    INSERT INTO symbols_fts(symbols_fts, rowid, name, docstring, signature)
    VALUES ('delete', old.id, old.name, old.docstring, old.signature);
END;

CREATE TRIGGER IF NOT EXISTS symbols_au AFTER UPDATE ON symbols BEGIN
    INSERT INTO symbols_fts(symbols_fts, rowid, name, docstring, signature)
    VALUES ('delete', old.id, old.name, old.docstring, old.signature);
    INSERT INTO symbols_fts(rowid, name, docstring, signature)
    VALUES (new.id, new.name, new.docstring, new.signature);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS summaries_fts USING fts5(
    content_text,
    content='files',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO summaries_fts(rowid, content_text)
    VALUES (new.id, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO summaries_fts(summaries_fts, rowid, content_text)
    VALUES ('delete', old.id, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO summaries_fts(summaries_fts, rowid, content_text)
    VALUES ('delete', old.id, old.summary);
    INSERT INTO summaries_fts(rowid, content_text)
    VALUES (new.id, new.summary);
END;
