-- Remove previous constraint if it exists
BEGIN;

-- First check if the constraint exists
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'check_max_completion_tokens'
    ) THEN
        ALTER TABLE models DROP CONSTRAINT check_max_completion_tokens;
    END IF;
END $$;

COMMIT;