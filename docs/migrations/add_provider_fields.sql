-- Add new fields to providers table
BEGIN;

-- Add API key field (encrypted, like in models table)
ALTER TABLE providers
ADD COLUMN api_key TEXT;

-- Add model name field
ALTER TABLE providers
ADD COLUMN model_name TEXT;

-- Add deployment name field (for Azure OpenAI)
ALTER TABLE providers
ADD COLUMN deployment_name TEXT;

-- Add is_azure field to distinguish Azure providers
ALTER TABLE providers
ADD COLUMN is_azure BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;