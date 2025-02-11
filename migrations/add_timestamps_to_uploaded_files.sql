-- Add created_at column to uploaded_files table
ALTER TABLE uploaded_files
  ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
