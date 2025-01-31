# Provider Configuration and Model Features Architecture

## Overview

This document defines how provider configuration is inherited by models and how model features are managed in our system. The architecture enables:
1. Consistent provider configuration inheritance
2. Model-specific feature management
3. Feature validation and enforcement

## Provider Configuration

### Base Configuration
Provider configuration defines the foundational settings that all models from that provider inherit. These settings establish the boundaries within which model features can operate:

```python
@dataclass
class Provider:
    # Core identity
    id: int
    name: str
    slug: str

    # Base configuration
    api_base_url: str
    api_version_format: str
    auth_type: str = "api-key"
    endpoint_pattern: str = "https://{endpoint}/openai/deployments/{deployment}/chat/completions"

    # Inherited settings
    validation_rules: Dict[str, str]
    requires_authentication: bool
```

### Configuration Inheritance
1. Models inherit their base configuration from their provider
2. Provider settings establish boundaries for model features
3. Provider configuration changes affect all associated models

## Model Features

### Feature Types
1. **Inherited Features** (from provider configuration)
   - API endpoints and patterns
   - Authentication requirements
   - Base validation rules

2. **Model-Specific Features**
   - Temperature control
   - Token limits
   - Streaming support
   - Special handling (e.g., o1-preview)

### Feature Management
```python
class Model:
    # Model-specific features
    PROVIDER_CAPABILITIES = {
        'gpt-4': {
            'fixed_temperature': True,
            'streaming': True,
            'max_tokens': 8192
        }
    }

    def apply_provider_constraints(self):
        """Apply inherited provider configuration"""
        provider = Provider.get_by_id(self.provider_id)
        if not provider:
            return

        # Provider configuration overrides model features
        provider_config = provider.capabilities
        if provider_config.get('fixed_temperature'):
            self.temperature = provider_config['fixed_temperature']
```

## Implementation Structure

### 1. Database Layer (schema.sql)
```sql
CREATE TABLE providers (
    -- Core fields
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    -- Configuration storage
    validation_rules JSONB NOT NULL DEFAULT '{}',
    -- Feature constraints
    feature_constraints JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE models (
    -- Core fields
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL,
    -- Feature settings
    temperature FLOAT,
    max_tokens INTEGER,
    supports_streaming BOOLEAN NOT NULL DEFAULT FALSE,
    requires_o1_handling BOOLEAN NOT NULL DEFAULT FALSE
);
```

### 2. Configuration Management
```python
@dataclass
class ProviderConfig:
    """Base configuration that models inherit"""
    # Core settings
    api_base_url: str
    api_version_format: str
    endpoint_pattern: str

    # Security settings
    auth_type: str
    requires_authentication: bool

    # Validation settings
    validation_rules: Dict[str, str]

    def validate_endpoint(self, endpoint: str) -> bool:
        """Validate endpoint against provider rules"""
        pattern = self.validation_rules.get('endpoint')
        return bool(re.match(pattern, endpoint))
```

### 3. Feature Implementation
```python
@dataclass
class ModelFeatures:
    """Model-specific feature management"""
    # Core features
    temperature: float
    max_tokens: int
    streaming: bool

    # Special features
    requires_o1_handling: bool
    custom_tokenization: bool

    def apply_provider_config(self, config: ProviderConfig):
        """Apply inherited provider configuration"""
        if config.validation_rules.get('fixed_temperature'):
            self.temperature = 1.0

        if not config.supports_streaming:
            self.streaming = False
```

## Benefits

1. **Clear Separation**
   - Provider configuration defines boundaries
   - Model features operate within those boundaries
   - Clear inheritance chain

2. **Type Safety**
   - Strong typing for configurations
   - Validated feature settings
   - Safe inheritance handling

3. **Flexibility**
   - Provider-specific constraints
   - Model-specific optimizations
   - Feature toggles and overrides

## Future Considerations

1. **Dynamic Configuration**
   - Runtime provider updates
   - Feature flag system
   - A/B testing support

2. **Enhanced Validation**
   - Deep configuration validation
   - Feature dependency checking
   - Constraint verification

3. **Monitoring**
   - Configuration usage tracking
   - Feature utilization metrics
   - Performance impact analysis
