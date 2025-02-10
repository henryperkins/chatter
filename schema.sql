-- schema.sql

-- =============================================================
-- TABLE CREATION - These must be executed in a single transaction
-- =============================================================
BEGIN;

-- Drop existing tables if they exist
DROP TABLE IF EXISTS login_attempts CASCADE;
DROP TABLE IF EXISTS uploaded_files CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS chats CASCADE;
DROP TABLE IF EXISTS model_versions CASCADE;
DROP TABLE IF EXISTS models CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS providers CASCADE;

-- PROVIDERS TABLE
CREATE TABLE providers (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    api_base_url TEXT NOT NULL,
    api_version_format TEXT NOT NULL,
    auth_type TEXT NOT NULL DEFAULT 'api-key',
    endpoint_pattern TEXT NOT NULL,
    validation_rules JSONB NOT NULL DEFAULT '{}',
    capabilities JSONB NOT NULL DEFAULT '{}',
    requires_authentication BOOLEAN NOT NULL DEFAULT TRUE,
    is_azure BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- USERS TABLE
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL CHECK (password_hash <> ''),
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reset_token_hash TEXT DEFAULT NULL,
    reset_token_expiry TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    email_verification_token TEXT DEFAULT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    otp_secret TEXT DEFAULT NULL,
    otp_required BOOLEAN DEFAULT FALSE
,
    locked_until TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    version INT NOT NULL DEFAULT 0
);

-- MODELS TABLE
CREATE TABLE models (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    deployment_name TEXT NOT NULL,
    description TEXT,
    model_type TEXT NOT NULL,
    api_endpoint TEXT NOT NULL,
    api_key TEXT NOT NULL,
    temperature FLOAT,
    max_tokens INTEGER,
    max_completion_tokens INTEGER NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    requires_o1_handling BOOLEAN NOT NULL DEFAULT FALSE,
    supports_streaming BOOLEAN NOT NULL DEFAULT FALSE,
    api_version TEXT NOT NULL,
    reasoning_effort TEXT NOT NULL DEFAULT 'medium',
    store_completion BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (provider_id, name)
);

-- MODEL VERSIONS TABLE
CREATE TABLE model_versions (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    version_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- CHATS TABLE
CREATE TABLE chats (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Chat',
    model_id INTEGER DEFAULT NULL REFERENCES models(id) ON DELETE RESTRICT,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- MESSAGES TABLE
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- UPLOADED FILES TABLE
CREATE TABLE uploaded_files (
    id SERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    mime_type TEXT DEFAULT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Login attempts tracking
CREATE TABLE login_attempts (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    attempted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    success BOOLEAN NOT NULL
);

COMMIT;

-- =============================================================
-- INDEX CREATION - Each index in its own transaction
-- =============================================================

BEGIN;
CREATE INDEX idx_login_attempts_username_time ON login_attempts(username, attempted_at);
CREATE INDEX idx_login_attempts_ip_time ON login_attempts(ip_address, attempted_at);
CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_chats_user_id ON chats (user_id);
CREATE INDEX idx_messages_chat_id ON messages (chat_id);
CREATE INDEX idx_models_is_default ON models (is_default);
CREATE INDEX idx_uploaded_files_chat_id ON uploaded_files (chat_id);
CREATE INDEX idx_messages_timestamp ON messages (timestamp);
CREATE INDEX idx_messages_metadata ON messages(((metadata->>'summarized')));
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_chats_created_at ON chats (created_at);
CREATE INDEX idx_messages_streaming ON messages(((metadata->>'streamed')));
CREATE INDEX idx_models_created_at ON models (created_at);
CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_created_at ON users (created_at);
CREATE INDEX idx_providers_name ON providers (name);
CREATE UNIQUE INDEX idx_providers_slug ON providers (slug);
CREATE INDEX idx_models_provider_id ON models (provider_id);
CREATE INDEX idx_models_version ON models (version);
CREATE INDEX idx_model_versions_model_id ON model_versions (model_id);
CREATE INDEX idx_model_versions_created_at ON model_versions (created_at);
CREATE UNIQUE INDEX unique_lower_username ON users ((LOWER(username)));
CREATE UNIQUE INDEX unique_lower_email ON users ((LOWER(email)));
COMMIT;
