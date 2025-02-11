-- Add uuid column to uploaded_files table
ALTER TABLE uploaded_files
    ADD COLUMN uuid TEXT NOT NULL DEFAULT gen_random_uuid()::text;

-- Create index for uuid column
CREATE INDEX idx_uploaded_files_uuid ON uploaded_files (uuid);
