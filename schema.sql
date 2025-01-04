-- schema.sql

-- Enable Foreign Key Constraints
PRAGMA foreign_keys = ON;

-- =============================
-- USERS TABLE
-- =============================
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user', -- 'user' or 'admin'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================
-- MODELS TABLE
-- =============================
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL, -- Display name of the model
    deployment_name TEXT UNIQUE NOT NULL, -- Deployment identifier from Azure
    description TEXT, -- Optional description of the model
    model_type TEXT NOT NULL DEFAULT 'azure', -- 'azure', 'openai', or 'o1-preview'
    api_endpoint TEXT NOT NULL, -- URL for calling the model API
    temperature REAL DEFAULT 1.0, -- Creativity parameter (0: deterministic, 2: high randomness)
    max_tokens INTEGER, -- Maximum input tokens for the model
    max_completion_tokens INTEGER NOT NULL DEFAULT 500, -- Max tokens the model can generate in completion
    is_default BOOLEAN DEFAULT 0, -- Whether this is the default model
    requires_o1_handling BOOLEAN DEFAULT 0, -- Special handling for o1-preview (e.g., no system messages)
    api_version TEXT DEFAULT '2024-10-01-preview', -- API version for the model
    version INTEGER DEFAULT 1, -- Version for tracking changes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================
-- MODEL VERSION HISTORY
-- =============================
CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL, -- Foreign key referencing models table
    name TEXT NOT NULL,
    deployment_name TEXT NOT NULL,
    description TEXT,
    model_type TEXT NOT NULL,
    api_endpoint TEXT NOT NULL,
    temperature REAL DEFAULT 1.0,
    max_tokens INTEGER,
    max_completion_tokens INTEGER NOT NULL,
    is_default BOOLEAN DEFAULT 0,
    requires_o1_handling BOOLEAN DEFAULT 0,
    api_version TEXT,
    version INTEGER, -- Model version number
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE CASCADE
);

-- =============================
-- CHATS TABLE
-- =============================
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY, -- UUID for uniquely identifying chat sessions
    user_id INTEGER NOT NULL, -- Foreign key referencing users table
    title TEXT NOT NULL DEFAULT 'New Chat', -- Title of the chat (updated after first message)
    model_id INTEGER DEFAULT NULL, -- Foreign key referencing chosen model for the chat
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE RESTRICT
);

-- =============================
-- MESSAGES TABLE
-- =============================
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL, -- Foreign key referencing chats table
    role TEXT NOT NULL, -- 'user', 'assistant', or 'system'
    content TEXT NOT NULL, -- Contents of the message
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

-- =============================
-- UPLOADED FILES TABLE
-- =============================
CREATE TABLE IF NOT EXISTS uploaded_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username); -- Speeds up username lookups
CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats (user_id); -- Speeds up fetching chats by user
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id); -- Speeds up fetching messages by chat
CREATE INDEX IF NOT EXISTS idx_models_is_default ON models (is_default); -- Ensures fast lookup of default model
CREATE INDEX IF NOT EXISTS idx_uploaded_files_chat_id ON uploaded_files (chat_id); -- Speeds up file lookups by chat
CREATE INDEX IF NOT EXISTS idx_model_versions_model_id ON model_versions (model_id); -- Speeds up version history lookups