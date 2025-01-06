-- Migration to make temperature nullable and update existing o1-preview models
BEGIN TRANSACTION;

-- Step 1: Make temperature column nullable
ALTER TABLE models RENAME TO models_old;

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    deployment_name TEXT UNIQUE NOT NULL,
    description TEXT,
    model_type TEXT NOT NULL DEFAULT 'azure',
    api_endpoint TEXT NOT NULL,
    temperature REAL, -- Now nullable
    max_tokens INTEGER,
    max_completion_tokens INTEGER NOT NULL DEFAULT 500,
    is_default BOOLEAN DEFAULT 0,
    requires_o1_handling BOOLEAN DEFAULT 0,
    api_version TEXT DEFAULT '2024-10-01-preview',
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Copy data from old table
INSERT INTO models SELECT * FROM models_old;

-- Step 2: Update existing o1-preview models to have NULL temperature
UPDATE models SET temperature = NULL WHERE requires_o1_handling = 1;

-- Clean up
DROP TABLE models_old;

COMMIT;
