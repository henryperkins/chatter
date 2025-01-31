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
    -- Capability storage
    capabilities JSONB NOT NULL DEFAULT '{}',
    validation_rules JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE models (
    -- Core fields
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL,
    -- Capability flags
    supports_streaming BOOLEAN NOT NULL DEFAULT FALSE,
    requires_o1_handling BOOLEAN NOT NULL DEFAULT FALSE,
    -- Configuration limits
    max_tokens INTEGER,
    max_completion_tokens INTEGER NOT NULL
);
```

### 2. Model Layer (models/model.py)
```python
class Model:
    # Provider-specific capabilities
    PROVIDER_CAPABILITIES = {
        'gpt-4': {
            'fixed_temperature': True,
            'streaming': True,
            'max_tokens': 8192
        },
        'gpt-4o': {
            'fixed_temperature': True,
            'streaming': True,
            'max_tokens': 16384
        }
    }

    def apply_provider_constraints(self):
        """Enforce provider capability rules"""
        provider = Provider.get_by_id(self.provider_id)
        if not provider:
            return

        provider_caps = provider.capabilities
        if provider_caps.get('fixed_temperature'):
            self.temperature = provider_caps['fixed_temperature']
```

### 3. Form Layer (forms.py)
```python
class ModelForm(FlaskForm):
    def validate_max_completion_tokens(self, field):
        provider = Provider.get_by_id(self.provider_id.data)
        provider_max = provider.capabilities.get('max_tokens', 16384)

        if self.requires_o1_handling.data:
            if not (1 <= value <= 8300):
                raise ValidationError("Must be between 1-8300 for o1-preview models")
        else:
            if not (1 <= value <= provider_max):
                raise ValidationError(f"Must be between 1-{provider_max}")
```

### 4. Chat Layer (models/chat.py)
```python
class Chat:
    def get_model(chat_id: str) -> Optional[Model]:
        """Get model with its capabilities for a chat"""
        with db_session() as db:
            query = text("SELECT model_id FROM chats WHERE id = :chat_id")
            row = db.execute(query, {"chat_id": chat_id}).mappings().first()
            if row and row["model_id"]:
                return Model.get_by_id(row["model_id"])
            return None
```

## Capability Enforcement Points

1. **Model Creation/Update**
   - Provider capabilities checked during model validation
   - Temperature constraints enforced
   - Token limits validated
   - Streaming support verified

2. **Chat Operations**
   - Model capabilities checked when setting chat model
   - Default model selection respects capabilities
   - Message handling considers model constraints

3. **Form Validation**
   - Real-time capability validation in forms
   - Special handling for o1-preview models
   - Provider-specific constraints enforced

## Configuration and Feature Types

### Provider Configuration Types
1. **API Configuration**
   - Base URL and version format
   - Endpoint patterns
   - Authentication methods

2. **Validation Configuration**
   - Endpoint format rules
   - Model identifier patterns
   - API version formats

3. **Security Configuration**
   - Authentication requirements
   - API key handling
   - Access control rules

### Model Feature Types
1. **Core Features**
   - Temperature control
   - Token management
   - Streaming capabilities

2. **Special Features**
   - o1-preview handling
   - Model-specific optimizations
   - Custom tokenization

3. **Operational Features**
   - Version tracking
   - State management
   - Performance settings

## Current Implementation Benefits

1. **Separation of Concerns**
   - Clear layering from database to UI
   - Consistent validation across layers
   - Modular capability management

2. **Flexibility**
   - Provider-specific overrides
   - Model-specific handling
   - Extensible capability system

3. **Reliability**
   - Comprehensive validation
   - Consistent constraint enforcement
   - Clear error handling

## Future Considerations

1. **Dynamic Capability Discovery**
   - Runtime capability detection
   - API-driven capability updates
   - Automatic constraint adjustment

2. **Enhanced Validation**
   - More granular capability checks
   - Better error reporting
   - Capability dependency management

3. **Monitoring and Analytics**
   - Capability usage tracking
   - Constraint violation monitoring
   - Performance impact analysis

### 2. Capability Interaction Patterns

#### Vertical Interactions
- **Inheritance Flow**: Base capabilities → Provider overrides → Model settings
- **Validation Chain**: Model config → Provider rules → Base requirements
- **Feature Resolution**: Check provider extensions → Fall back to base features

#### Horizontal Interactions
- **Feature Dependencies**: Some capabilities may require others to be present
- **Conflict Resolution**: Provider settings take precedence over defaults
- **Capability Composition**: Multiple features may combine to enable new functionality

### 3. State Management

#### Configuration Time
- Provider capabilities are defined during provider registration
- Base capabilities provide default values and validation rules
- Provider-specific overrides are validated against base requirements

#### Runtime
- Capability checks occur before feature usage
- Dynamic capability adjustments based on runtime conditions
- Caching of capability states for performance

### 4. Cross-Cutting Concerns

#### Security
- Capability-based access control
- Validation of security-sensitive settings
- Audit logging of capability usage

#### Performance
- Capability check optimization
- Caching strategies
- Lazy loading of extended features

#### Monitoring
- Capability usage tracking
- Performance impact analysis
- Error rate monitoring by capability

## Core Concepts

### 1. Provider Configuration Space

#### Provider Identity
- **Name and Slug**: Unique identifiers for the provider
- **API Base URL**: Root endpoint for provider services
- **API Version Format**: Provider-specific version formatting
- **Authentication Type**: Support for different auth methods (API key, OAuth, etc.)

#### Endpoint Configuration
- **Endpoint Pattern**: Template for constructing model endpoints
- **Validation Rules**: Regex patterns for validating model IDs and versions
- **Authentication Requirements**: Whether provider requires authentication

### 2. Capability Space

#### Default Capabilities
```python
DEFAULT_CAPABILITIES = {
    "temperature_range": {"min": 0.0, "max": 2.0, "default": 1.0},
    "max_tokens": 2048,
    "streaming": False,
    "endpoint_pattern": "https://{region}.api.{domain}/{version}",
    "supported_api_versions": [],
    "supported_models": [],
    "features": [],
    "validation_rules": {
        "endpoint": r"^https://[a-zA-Z0-9-]+\.api\.[a-zA-Z0-9-]+\.[a-zA-Z0-9-]+/[a-zA-Z0-9-]+$",
        "model_identifier": r"^[a-zA-Z0-9-]+$"
    }
}
```

#### Provider-Specific Capabilities
- **Temperature Control**: Provider-specific temperature ranges and defaults
- **Token Limits**: Maximum token counts for context and completion
- **Streaming Support**: Whether provider supports streaming responses
- **API Versions**: Supported API versions for the provider
- **Model Support**: List of supported model identifiers
- **Special Features**: Provider-specific capabilities (e.g., function calling)

### 3. Validation Space

#### Model Configuration Validation
- Validate temperature settings against provider ranges
- Enforce token limits based on provider capabilities
- Verify model identifier format
- Check API version compatibility

#### Endpoint Validation
- Validate endpoint URL format
- Ensure proper model deployment naming
- Verify API version format

#### Feature Validation
- Check for feature support before usage
- Validate feature-specific parameters
- Handle graceful fallbacks for unsupported features

## Architecture Principles

### 1. Capability Inheritance
- Default capabilities provide baseline functionality
- Provider-specific capabilities override defaults
- Model-specific settings must respect provider capabilities

### 2. Strict Validation
- All provider configurations must be validated at creation
- Model configurations must be validated against provider capabilities
- Runtime validation for all API interactions

### 3. Feature Discovery
- Providers declare supported features explicitly
- System checks feature support before attempting usage
- Graceful degradation for unsupported features

### 4. Extensibility
- New capabilities can be added without breaking existing ones
- Provider-specific features can be added through capability extension
- Validation rules can be extended for new requirements

## Implementation Strategy

### 1. Configuration Management
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

### 2. Feature Implementation
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

### 3. Integration Layer
```python
class Model:
    """Combines provider configuration with model features"""
    def __init__(self, provider_id: int):
        self.provider = Provider.get_by_id(provider_id)
        self.config = ProviderConfig.from_provider(self.provider)
        self.features = ModelFeatures()

    def initialize(self):
        """Set up model with provider configuration"""
        self.features.apply_provider_config(self.config)
        self.validate_features()

    def validate_features(self) -> List[str]:
        """Validate features against provider config"""
        errors = []
        if self.features.temperature < self.config.min_temperature:
            errors.append("Temperature below provider minimum")
        return errors
```

## Benefits

1. **Clear Boundaries**: Well-defined spaces for configuration, capabilities, and validation
2. **Type Safety**: Strong typing for provider and capability configurations
3. **Extensibility**: Easy addition of new providers and capabilities
4. **Consistency**: Unified handling of provider-specific features
5. **Reliability**: Comprehensive validation at all levels

## Future Considerations

1. **Dynamic Capabilities**: Support for runtime capability discovery
2. **Capability Negotiation**: Smart handling of capability differences
3. **Version Management**: Better handling of API version compatibility
4. **Feature Composition**: Support for combining provider capabilities
5. **Monitoring**: Capability usage tracking and analytics

## Capability Versioning and Migration

### 1. Version Control
- Capabilities are versioned alongside models (models.version field)
- Changes to capabilities trigger version increments
- Version history stored in model_versions table

### 2. Migration Patterns
```python
# Example migration handling in Model class
def update(model_id: int, data: Dict[str, Any]) -> None:
    # Get current version
    current_version = db.execute(
        text("SELECT version FROM models WHERE id = :model_id"),
        {"model_id": model_id}
    ).scalar()

    # Add version increment to update data
    update_data['version'] = current_version + 1

    # Optimistic locking for concurrent updates
    query = text(f"""
        UPDATE models
        SET {set_clause}
        WHERE id = :model_id AND version = :current_version
        RETURNING version
    """)
```

### 3. Backward Compatibility
- Default capabilities provide fallback values
- Version-specific validation rules
- Graceful degradation for removed capabilities

### 4. Migration Strategy
1. **Preparation**
   - Document capability changes
   - Update validation rules
   - Prepare migration scripts

2. **Execution**
   - Apply database updates
   - Update model versions
   - Validate existing configurations

3. **Verification**
   - Test migrated capabilities
   - Verify constraint enforcement
   - Check backward compatibility

### 5. Rollback Plan
- Version history enables capability rollback
- Stored procedures for reverting changes
- Audit trail of capability modifications

## Testing and Verification

### 1. Capability Testing Layers

#### Database Layer
```sql
-- Test capability storage
SELECT jsonb_typeof(capabilities) as cap_type,
       jsonb_typeof(validation_rules) as rule_type
FROM providers
WHERE id = :provider_id;

-- Test version tracking
SELECT COUNT(DISTINCT version) as version_count
FROM model_versions
WHERE model_id = :model_id;
```

#### Model Layer
```python
def test_provider_capabilities():
    """Test provider capability enforcement"""
    provider = Provider.get_by_id(provider_id)
    caps = ProviderCapabilities(provider.capabilities)

    # Test temperature constraints
    assert caps.validate_model_config({
        'temperature': 1.5,
        'max_tokens': 1000
    }) == []

    # Test invalid settings
    errors = caps.validate_model_config({
        'temperature': 3.0  # Outside valid range
    })
    assert len(errors) > 0
```

#### Form Layer
```python
def test_model_form_validation():
    """Test form-level capability validation"""
    form = ModelForm(data={
        'temperature': 1.0,
        'max_completion_tokens': 9000  # Exceeds o1-preview limit
    })
    assert not form.validate()
    assert 'max_completion_tokens' in form.errors
```

### 2. Verification Scenarios

1. **Capability Inheritance**
   - Test default capability application
   - Verify provider override behavior
   - Check model-specific constraints

2. **Validation Chain**
   - Database constraint validation
   - Provider capability validation
   - Model configuration validation
   - Form input validation

3. **Feature Support**
   - Test feature detection
   - Verify graceful degradation
   - Check feature dependencies

### 3. Test Categories

#### Unit Tests
- Individual capability validation
- Feature support checking
- Version management

#### Integration Tests
- Capability inheritance chain
- Form validation with DB
- Chat-model capability interaction

#### System Tests
- End-to-end capability enforcement
- Migration scenarios
- Rollback procedures

### 4. Monitoring Tests

1. **Performance Impact**
   - Capability check latency
   - Validation overhead
   - Cache effectiveness

2. **Error Rates**
   - Validation failures
   - Capability mismatches
   - Version conflicts

3. **Usage Patterns**
   - Feature utilization
   - Capability distribution
   - Version adoption

### 5. Test Automation

1. **Continuous Integration**
   - Automated capability tests
   - Migration verification
   - Backward compatibility checks

2. **Test Data Generation**
   - Capability permutations
   - Edge case scenarios
   - Migration test cases

3. **Test Environment**
   - Isolated capability testing
   - Version control testing
   - Performance benchmarking
