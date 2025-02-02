-- Add Azure Search fields to uploaded_file table
ALTER TABLE uploaded_file
ADD COLUMN IF NOT EXISTS azure_search_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS last_indexed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS indexing_status VARCHAR(50) DEFAULT 'pending';

-- Add index for Azure Search ID
CREATE INDEX IF NOT EXISTS idx_uploaded_file_azure_search_id ON uploaded_file(azure_search_id);

-- Add index for indexing status
CREATE INDEX IF NOT EXISTS idx_uploaded_file_indexing_status ON uploaded_file(indexing_status);

-- Add index for last indexed timestamp
CREATE INDEX IF NOT EXISTS idx_uploaded_file_last_indexed_at ON uploaded_file(last_indexed_at);

COMMENT ON COLUMN uploaded_file.azure_search_id IS 'The document ID in Azure AI Search';
COMMENT ON COLUMN uploaded_file.last_indexed_at IS 'Timestamp when the file was last indexed in Azure AI Search';
COMMENT ON COLUMN uploaded_file.indexing_status IS 'Status of file indexing in Azure AI Search (pending, indexed, failed)';
