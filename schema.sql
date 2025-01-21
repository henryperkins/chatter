-- schema.sql

-- =============================
-- PROVIDERS TABLE
-- =============================
CREATE TABLE IF NOT EXISTS providers (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL, -- Provider name (e.g. Azure, OpenAI, Anthropic)
    slug TEXT UNIQUE NOT NULL, -- URL-friendly identifier
    api_base_url TEXT NOT NULL, -- Base URL for provider's API
    capabilities JSONB NOT NULL DEFAULT '{}', -- Provider-specific capabilities and constraints
    requires_authentication BOOLEAN DEFAULT TRUE, -- Whether API key is required
    api_version_format TEXT, -- Format string for API version (e.g. "YYYY-MM-DD")
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================
-- USERS TABLE
-- =============================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL CHECK (password_hash <> ''),
    role TEXT NOT NULL DEFAULT 'user', -- 'user' or 'admin'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reset_token TEXT DEFAULT NULL, -- Token for password reset
    email_verification_token TEXT DEFAULT NULL, -- Token for email verification
    is_verified BOOLEAN DEFAULT FALSE, -- Whether the email is verified
    reset_token_expiry TIMESTAMP DEFAULT NULL -- Expiry for the reset token
);

-- =============================
-- MODELS TABLE
-- =============================
CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    name TEXT NOT NULL, -- Display name of the model
    model_identifier TEXT NOT NULL, -- Provider's model identifier (e.g. deployment name for Azure)
    description TEXT, -- Optional description of the model
    capabilities TEXT[] DEFAULT '{}', -- Array of model capabilities (e.g. chat, completion, embedding)
    api_endpoint TEXT NOT NULL, -- URL for calling the model API
    api_key TEXT NOT NULL CHECK (api_key <> ''), -- API key for authentication
    config JSONB NOT NULL DEFAULT '{}', -- Provider-specific configuration (temperature, tokens, etc)
    is_default BOOLEAN DEFAULT FALSE, -- Whether this is the default model
    api_version TEXT, -- API version for the model
    version INTEGER DEFAULT 1, -- Version for tracking changes
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (provider_id, model_identifier) -- Ensure unique model per provider
);

-- Provider-specific model settings
CREATE TABLE IF NOT EXISTS model_settings (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    settings JSONB NOT NULL DEFAULT '{}', -- Provider-specific settings
    version INTEGER DEFAULT 1, -- Version for tracking changes
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (model_id, provider_id)
);

-- =============================
-- MODEL VERSION HISTORY
-- =============================
CREATE TABLE IF NOT EXISTS model_versions (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (model_id) REFERENCES models(id)
);

-- =============================
-- CHATS TABLE
-- =============================
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY, -- UUID for uniquely identifying chat sessions
    user_id INTEGER NOT NULL, -- Foreign key referencing users table
    title TEXT NOT NULL DEFAULT 'New Chat', -- Title of the chat (updated after first message)
    model_id INTEGER DEFAULT NULL, -- Foreign key referencing models table
    is_deleted BOOLEAN DEFAULT FALSE, -- Soft delete flag
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE RESTRICT
);

-- =============================
-- MESSAGES TABLE
-- =============================
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL, -- Foreign key referencing chats table
    role TEXT NOT NULL, -- 'user', 'assistant', or 'system'
    content TEXT NOT NULL, -- Contents of the message
    metadata JSONB, -- Metadata for the message (token count, timestamps, etc.)
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

-- =============================
-- UPLOADED FILES TABLE
-- =============================
CREATE TABLE IF NOT EXISTS uploaded_files (
    id SERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL, -- Foreign key referencing chats table
    filename TEXT NOT NULL, -- Original filename of the uploaded file
    filepath TEXT NOT NULL, -- Server path where the file is stored
    mime_type TEXT DEFAULT NULL, -- MIME type of the uploaded file
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

-- =============================
-- INDEXES FOR PERFORMANCE
-- =============================
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

-- Additional indexes for improved performance
CREATE INDEX IF NOT EXISTS idx_models_model_identifier ON models (model_identifier);
CREATE INDEX IF NOT EXISTS idx_models_created_at ON models (created_at);
CREATE INDEX IF NOT EXISTS idx_model_versions_created_at ON model_versions (created_at);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at);
CREATE INDEX IF NOT EXISTS idx_providers_name ON providers (name);
CREATE INDEX IF NOT EXISTS idx_providers_slug ON providers (slug);
CREATE INDEX IF NOT EXISTS idx_models_provider_id ON models (provider_id);
CREATE INDEX IF NOT EXISTS idx_model_settings_model_id ON model_settings (model_id);
