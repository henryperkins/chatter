-- Add metadata fields to uploaded_files table if they don't exist
DO $$
BEGIN
    -- Add description if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'uploaded_files' AND column_name = 'description') THEN
        ALTER TABLE uploaded_files ADD COLUMN description TEXT;
    END IF;

    -- Add created_at if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'uploaded_files' AND column_name = 'created_at') THEN
        ALTER TABLE uploaded_files ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
    END IF;

    -- Add updated_at if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'uploaded_files' AND column_name = 'updated_at') THEN
        ALTER TABLE uploaded_files ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
    END IF;

    -- Add version if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'uploaded_files' AND column_name = 'version') THEN
        ALTER TABLE uploaded_files ADD COLUMN version INTEGER DEFAULT 1;
    END IF;
END
$$;

-- Add index on chat_id and version if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes 
                  WHERE tablename = 'uploaded_files' AND indexname = 'idx_uploaded_files_chat_version') THEN
        CREATE INDEX idx_uploaded_files_chat_version ON uploaded_files(chat_id, version);
    END IF;
END
$$;

-- Create or replace the updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Drop trigger if exists and create it
DROP TRIGGER IF EXISTS update_uploaded_files_updated_at ON uploaded_files;
CREATE TRIGGER update_uploaded_files_updated_at
    BEFORE UPDATE ON uploaded_files
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();