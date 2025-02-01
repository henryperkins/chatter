-- Update API versions across the system
BEGIN;

-- Update provider API version format
UPDATE providers
SET api_version_format = '2024-12-01-preview'
WHERE api_version_format = '2023-07-01-preview';

-- Update provider capabilities to use new API version
UPDATE providers
SET capabilities = jsonb_set(
    capabilities,
    '{azure,api_version}',
    '"2024-12-01-preview"'
)
WHERE capabilities ? 'azure';

UPDATE providers
SET capabilities = jsonb_set(
    capabilities,
    '{o1-preview,api_version}',
    '"2024-12-01-preview"'
)
WHERE capabilities ? 'o1-preview';

-- Update models to use new API version
UPDATE models
SET api_version = '2024-12-01-preview'
WHERE api_version = '2023-07-01-preview';

COMMIT;