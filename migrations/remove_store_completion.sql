-- Remove store_completion column from models table
BEGIN;
ALTER TABLE models DROP COLUMN IF EXISTS store_completion;
COMMIT;