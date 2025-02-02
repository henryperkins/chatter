-- Add azure_file_id column to uploaded_files table
ALTER TABLE uploaded_files
ADD COLUMN azure_file_id TEXT;

-- Add index for faster lookups by azure_file_id
CREATE INDEX idx_uploaded_files_azure_file_id ON uploaded_files(azure_file_id);
