-- Update existing chats to ensure timestamps are in the correct format
UPDATE chats
SET created_at = datetime(created_at)
WHERE created_at NOT LIKE '%:%';

-- Add index for faster timestamp-based sorting
CREATE INDEX IF NOT EXISTS idx_chats_created_at ON chats (created_at DESC);
