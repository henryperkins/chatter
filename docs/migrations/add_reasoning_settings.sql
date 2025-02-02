BEGIN;

-- Add reasoning_effort column with check constraint for valid values
ALTER TABLE models
ADD COLUMN reasoning_effort TEXT CHECK (reasoning_effort IN ('low', 'medium', 'high')) DEFAULT 'medium';

-- Add store column for completion storage
ALTER TABLE models
ADD COLUMN store_completion BOOLEAN NOT NULL DEFAULT FALSE;

-- Update existing o1/o3 models to have default reasoning settings
UPDATE models
SET reasoning_effort = 'medium'
WHERE model_type IN ('o1-preview', 'o3-mini');

COMMIT;