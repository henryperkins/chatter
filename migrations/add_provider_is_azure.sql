-- Add is_azure column to providers table
BEGIN;

-- Add the column
ALTER TABLE providers ADD COLUMN IF NOT EXISTS is_azure BOOLEAN NOT NULL DEFAULT FALSE;

-- Update existing providers based on their api_base_url
UPDATE providers 
SET is_azure = TRUE 
WHERE api_base_url LIKE '%openai.azure.com%';

COMMIT;