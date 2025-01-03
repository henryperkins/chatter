-- schema.sql

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chats table
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    model_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE RESTRICT
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

-- Models table
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    deployment_name TEXT UNIQUE NOT NULL,
    description TEXT,
    model_type TEXT NOT NULL DEFAULT 'azure',
    api_endpoint TEXT NOT NULL,
    temperature REAL DEFAULT 1.0,
    max_tokens INTEGER,
    max_completion_tokens INTEGER NOT NULL,
    is_default BOOLEAN DEFAULT 0,
    requires_o1_handling BOOLEAN DEFAULT 0,
    api_version TEXT DEFAULT '2024-10-01-preview',
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Model Versions table (for version history)
CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    deployment_name TEXT NOT NULL,
    description TEXT,
    model_type TEXT NOT NULL,
    api_endpoint TEXT NOT NULL,
    temperature REAL,
    max_tokens INTEGER,
    max_completion_tokens INTEGER,
    is_default BOOLEAN,
    requires_o1_handling BOOLEAN,
    api_version TEXT,
    version INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE CASCADE
);

-- Uploaded Files table
CREATE TABLE IF NOT EXISTS uploaded_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id);
CREATE INDEX IF NOT EXISTS idx_models_is_default ON models (is_default);
CREATE INDEX IF NOT EXISTS idx_model_versions_model_id ON model_versions (model_id);
