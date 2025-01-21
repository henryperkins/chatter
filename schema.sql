-- schema.sql

-- =============================================================
-- TABLE CREATION - These must be executed in a single transaction
-- =============================================================
BEGIN;

-- PROVIDERS TABLE
CREATE TABLE IF NOT EXISTS providers (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    api_base_url TEXT NOT NULL,
    capabilities JSONB NOT NULL DEFAULT '{}',
    requires_authentication BOOLEAN DEFAULT TRUE,
    api_version_format TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL CHECK (password_hash <> ''),
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reset_token TEXT DEFAULT NULL,
    email_verification_token TEXT DEFAULT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    reset_token_expiry TIMESTAMP DEFAULT NULL
);

-- MODELS TABLE
CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    model_identifier TEXT NOT NULL,
    description TEXT,
    capabilities TEXT[] DEFAULT '{}',
    api_endpoint TEXT NOT NULL,
    api_key TEXT NOT NULL CHECK (api_key <> ''),
    config JSONB NOT NULL DEFAULT '{}',
    is_default BOOLEAN DEFAULT FALSE,
    api_version TEXT,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (provider_id, model_identifier)
);

-- Provider-specific model settings
CREATE TABLE IF NOT EXISTS model_settings (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    settings JSONB NOT NULL DEFAULT '{}',
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (model_id, provider_id)
);

-- MODEL VERSION HISTORY
CREATE TABLE IF NOT EXISTS model_versions (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (model_id) REFERENCES models(id)
);

-- CHATS TABLE
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT 'New Chat',
    model_id INTEGER DEFAULT NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE RESTRICT
);

-- MESSAGES TABLE
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

-- UPLOADED FILES TABLE
CREATE TABLE IF NOT EXISTS uploaded_files (
    id SERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    mime_type TEXT DEFAULT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

COMMIT;

-- =============================================================
-- INDEX CREATION - Each index in its own transaction
-- =============================================================

CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);
CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id);
CREATE INDEX IF NOT EXISTS idx_models_is_default ON models (is_default);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_chat_id ON uploaded_files (chat_id);
CREATE INDEX IF NOT EXISTS idx_model_versions_model_id ON model_versions (model_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages (timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_metadata ON messages(((metadata->>'summarized')));
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_chats_created_at ON chats (created_at);
CREATE INDEX IF NOT EXISTS idx_messages_streaming ON messages(((metadata->>'streamed')));
CREATE INDEX IF NOT EXISTS idx_models_created_at ON models (created_at);
CREATE INDEX IF NOT EXISTS idx_model_versions_created_at ON model_versions (created_at);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at);
CREATE INDEX IF NOT EXISTS idx_providers_name ON providers (name);
CREATE INDEX IF NOT EXISTS idx_providers_slug ON providers (slug);
CREATE INDEX IF NOT EXISTS idx_models_provider_id ON models (provider_id);
CREATE INDEX IF NOT EXISTS idx_model_settings_model_id ON model_settings (model_id);
