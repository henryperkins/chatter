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
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
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
    otp_required BOOLEAN DEFAULT FALSE,
    account_locked_until TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    failed_login_attempts INT NOT NULL DEFAULT 0,
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

-- CHATS TABLE
CREATE TABLE chats (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Chat',
    model_id INTEGER DEFAULT NULL REFERENCES models(id) ON DELETE RESTRICT,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- MODEL VERSIONS TABLE
CREATE TABLE model_versions (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    version_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
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
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INT NOT NULL DEFAULT 1,
    uuid TEXT NOT NULL,
    size BIGINT NOT NULL DEFAULT 0,
    description TEXT,
    azure_file_id TEXT,
    azure_search_id TEXT,
    indexing_status TEXT NOT NULL DEFAULT 'pending',
    last_indexed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    tokenized_text TEXT,
    text_content TEXT
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
CREATE INDEX idx_uploaded_files_version ON uploaded_files (version);
CREATE INDEX idx_uploaded_files_uuid ON uploaded_files (uuid);
COMMIT;

-- =============================================================
-- INITIAL DATA - Insert default configuration
-- =============================================================

BEGIN;
-- Insert Azure OpenAI Provider (with conflict handling)
INSERT INTO providers (
    name, slug, api_base_url, api_version_format, auth_type, 
    endpoint_pattern, is_azure, validation_rules, capabilities, 
    requires_authentication, is_active
) VALUES (
    'Azure OpenAI', 
    'azure-openai',
    'https://o1models.openai.azure.com',
    'YYYY-MM-DD',
    'api-key',
    '/openai/deployments/{deployment_name}/chat/completions',
    true,
    '{"model_id": "^[a-zA-Z0-9-]{3,64}$"}',
    '{"max_tokens": 200000, "max_completion_tokens": 100000}',
    true,
    true
) ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    api_base_url = EXCLUDED.api_base_url,
    api_version_format = EXCLUDED.api_version_format,
    auth_type = EXCLUDED.auth_type,
    endpoint_pattern = EXCLUDED.endpoint_pattern,
    is_azure = EXCLUDED.is_azure,
    validation_rules = EXCLUDED.validation_rules,
    capabilities = EXCLUDED.capabilities,
    requires_authentication = EXCLUDED.requires_authentication,
    is_active = EXCLUDED.is_active;

-- Insert O1 Model with proper provider reference
INSERT INTO models (
    provider_id,
    name,
    deployment_name,
    description,
    model_type,
    api_endpoint,
    api_key,
    temperature,
    max_tokens,
    max_completion_tokens,
    is_default,
    requires_o1_handling,
    supports_streaming,
    api_version,
    reasoning_effort
) VALUES (
    (SELECT id FROM providers WHERE slug = 'azure-openai'),
    'O1 Model',
    'o1-east2',
    'Azure OpenAI O1 Model',
    'o1',
    'https://o1models.openai.azure.com',
    'vOJIQH9dOVWO83YTXnu312o5rhgJ1a9yzrQ5goUKTZ7KPhmSX6dpJQQJ99BBACHYHv6XJ3w3AAABACOGSR1q',
    1.0,
    200000,
    100000,
    true,
    true,
    false,
    '2025-01-01-preview',
    'medium'
) ON CONFLICT (provider_id, name) DO UPDATE SET
    deployment_name = EXCLUDED.deployment_name,
    description = EXCLUDED.description,
    model_type = EXCLUDED.model_type,
    api_endpoint = EXCLUDED.api_endpoint,
    api_key = EXCLUDED.api_key,
    temperature = EXCLUDED.temperature,
    max_tokens = EXCLUDED.max_tokens,
    max_completion_tokens = EXCLUDED.max_completion_tokens,
    is_default = EXCLUDED.is_default,
    requires_o1_handling = EXCLUDED.requires_o1_handling,
    supports_streaming = EXCLUDED.supports_streaming,
    api_version = EXCLUDED.api_version,
    reasoning_effort = EXCLUDED.reasoning_effort,
    version = models.version + 1;

-- Insert Admin User
INSERT INTO users (
    username,
    email,
    password_hash,
    role,
    is_verified,
    is_active
) VALUES (
    'admin',
    'admin@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyBAHLNn0FQrYi',
    'admin',
    true,
    true
);

COMMIT;
