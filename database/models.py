SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE NOT NULL,
    username    TEXT,
    role        TEXT DEFAULT 'member',
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS partners (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tag         TEXT UNIQUE NOT NULL,
    notes       TEXT,
    created_by  INTEGER REFERENCES users(telegram_id),
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id  INTEGER NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(telegram_id),
    entry_type  TEXT NOT NULL,
    title       TEXT,
    description TEXT,
    link        TEXT,
    file_path   TEXT,
    file_id     TEXT,
    tags        TEXT,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_entries_partner ON entries(partner_id);
CREATE INDEX IF NOT EXISTS idx_entries_link    ON entries(link);
CREATE INDEX IF NOT EXISTS idx_entries_type    ON entries(entry_type);
CREATE INDEX IF NOT EXISTS idx_entries_date    ON entries(created_at);
"""
