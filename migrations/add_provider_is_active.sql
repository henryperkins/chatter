-- Add is_active column to providers table
BEGIN;

ALTER TABLE providers 
ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;

COMMIT;
