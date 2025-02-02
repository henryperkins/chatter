-- Update provider settings based on type
BEGIN;

-- Update Azure providers
UPDATE providers
SET endpoint_pattern = 'https://{endpoint}/openai/deployments/{deployment}/chat/completions',
    validation_rules = json_build_object(
        'model_id', '^[a-zA-Z0-9-]{3,64}$',
        'api_version', '^\d{4}-\d{2}-\d{2}(-preview)?$'
    )::jsonb
WHERE api_base_url LIKE '%openai.azure.com%';

-- Update OpenAI providers
UPDATE providers
SET endpoint_pattern = 'https://api.openai.com/v1/chat/completions',
    validation_rules = json_build_object(
        'model_id', '^(gpt-4|gpt-3.5-turbo).*$',
        'api_version', '^v[0-9]+.*$'
    )::jsonb
WHERE api_base_url NOT LIKE '%openai.azure.com%';

COMMIT;