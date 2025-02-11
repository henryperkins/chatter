-- Add missing columns to uploaded_files table
ALTER TABLE uploaded_files
  ADD COLUMN size BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN description TEXT,
  ADD COLUMN azure_file_id TEXT,
  ADD COLUMN azure_search_id TEXT,
  ADD COLUMN indexing_status TEXT NOT NULL DEFAULT 'pending',
  ADD COLUMN last_indexed_at TIMESTAMP WITH TIME ZONE,
  ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
