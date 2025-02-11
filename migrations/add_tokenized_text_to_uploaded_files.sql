-- Add tokenized_text column to uploaded_files table
ALTER TABLE uploaded_files
  ADD COLUMN tokenized_text TEXT;
