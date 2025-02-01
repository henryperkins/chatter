-- Update max_completion_tokens constraint for o1-preview models
ALTER TABLE models DROP CONSTRAINT IF EXISTS models_max_completion_tokens_check;
ALTER TABLE models ADD CONSTRAINT models_max_completion_tokens_check 
    CHECK (max_completion_tokens >= 1 AND max_completion_tokens <= 25000);

-- Update any existing o1-preview models that might have been limited by the old constraint
UPDATE models
SET max_completion_tokens = LEAST(max_completion_tokens, 25000)
WHERE model_type = 'o1-preview' AND requires_o1_handling = true;