# Azure AI Search Configuration Guide

## 1. Environment Setup

Add the following variables to your `.env` file:

```bash
AZURE_SEARCH_ENDPOINT=https://searchforme.search.windows.net
AZURE_SEARCH_KEY=<your-admin-key>
AZURE_SEARCH_INDEX_NAME=chatterindex
AZURE_SEARCH_API_VERSION=2023-11-01
AZURE_SEARCH_REPLICA_COUNT=2
AZURE_SEARCH_PARTITION_COUNT=1
AZURE_SEARCH_HOSTING_MODE=default
AZURE_SEARCH_SEMANTIC_SEARCH=free
```

## 2. Create Search Index

The search index will be automatically created when the application starts. The index includes:

- Document content (searchable text)
- Metadata (title, filepath, etc.)
- Semantic search configuration for improved results

## 3. Using Search Features

### 3.1 Index Documents

Documents are automatically indexed when uploaded through the file upload interface. The system:
- Extracts text content
- Generates metadata
- Indexes in Azure Search
- Supports semantic search queries

### 3.2 Search Documents

Use the search functionality through:

1. Chat Interface:
   - Reference uploaded documents in conversations
   - Get relevant content from your documents

2. API Endpoints:
   ```http
   POST /api/search
   Content-Type: application/json

   {
     "query": "your search query",
     "filter": "optional OData filter"
   }
   ```

## 4. Features Available

With the current configuration (standard tier):

- Semantic Search (free tier)
  * Improved natural language understanding
  * Better search relevance
  * Semantic captions and answers

- Scale Settings
  * 2 replicas for high availability
  * 1 partition for data storage
  * Default hosting mode

- Security
  * API key authentication
  * Network rules can be configured
  * Encryption with customer-managed keys (optional)

## 5. Monitoring

Monitor your search service through:
- Azure Portal metrics
- Application logs (search-related events are logged)
- Query statistics in the Azure Portal

## 6. Best Practices

1. Document Indexing:
   - Keep documents under 32KB for optimal performance
   - Use appropriate field mappings
   - Include relevant metadata

2. Querying:
   - Use semantic search for natural language queries
   - Implement filters for better performance
   - Use facets for result categorization

3. Security:
   - Rotate API keys periodically
   - Use separate query and admin keys
   - Monitor access logs

## 7. Troubleshooting

Common issues and solutions:

1. Index Creation Fails:
   - Verify endpoint and API key
   - Check field definitions
   - Review service limits

2. Search Returns No Results:
   - Verify documents are indexed
   - Check query syntax
   - Review field mappings

3. Performance Issues:
   - Monitor replica usage
   - Check partition data size
   - Review query patterns

## 8. Scaling

Current configuration supports:
- Up to 2 replicas for query load
- 1 partition for data storage
- Can be adjusted based on needs

Contact Azure support to modify:
- Storage limits
- Replica counts
- Partition counts
