---
title: Azure OpenAI On Your Data Python & REST API reference
titleSuffix: Azure OpenAI
description: Learn how to use Azure OpenAI On Your Data Python & REST API.
manager: nitinme
ms.service: azure-ai-openai
ms.topic: conceptual
ms.date: 07/18/2024
author: aahill
ms.author: aahi
recommendations: false
ms.custom: devx-track-python
---

# Azure OpenAI On Your Data API Reference

This article provides reference documentation for Python and REST for the new Azure OpenAI On Your Data API. The latest API version is `2024-05-01-preview` [Swagger spec](https://github.com/Azure/azure-rest-api-specs/tree/main/specification/cognitiveservices/data-plane/AzureOpenAI/inference/preview/2024-05-01-preview).

> [!NOTE]
> Since API version `2024-02-15-preview` we introduced the following breaking changes comparing to earlier API versions:
> * The API path is changed from `/extensions/chat/completions` to `/chat/completions`.
> * The naming convention of property keys and enum values is changed from camel casing to snake casing. Example: `deploymentName` is changed to `deployment_name`.
> * The data source type `AzureCognitiveSearch` is changed to `azure_search`.
> * The citations and intent is moved from assistant message's context tool messages to assistant message's context root level with explicit [schema defined](#context).

```http
POST {endpoint}/openai/deployments/{deployment-id}/chat/completions?api-version={api-version}
```

**Supported versions**
* `2024-02-15-preview` [Swagger spec](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/cognitiveservices/data-plane/AzureOpenAI/inference/preview/2024-02-15-preview/inference.json).
* `2024-02-01` [Swagger spec](https://github.com/Azure/azure-rest-api-specs/tree/main/specification/cognitiveservices/data-plane/AzureOpenAI/inference/stable/2024-02-01).
* `2024-05-01-preview` [Swagger spec](https://github.com/Azure/azure-rest-api-specs/tree/main/specification/cognitiveservices/data-plane/AzureOpenAI/inference/preview/2024-05-01-preview)

> [!NOTE]
> [Pinecone](./pinecone.md), and [Elasticsearch](./elasticsearch.md) are supported as a preview.

## URI parameters

|Name               | In   | Type     | Required | Description                                                                           |
|---                |---   |---       |---       |---                                                                                    |
|```deployment-id```|path  |string    |True      |Specifies the chat completions model deployment name to use for this request.          |
|```endpoint```     |path  |string    |True      |Azure OpenAI endpoints. For example: `https://{YOUR_RESOURCE_NAME}.openai.azure.com`   |
|```api-version```  |query |string    |True      |The API version to use for this operation.                                             |

## Request body

The request body inherits the same schema of chat completions API request. This table shows the parameters unique for Azure OpenAI On Your Data.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `data_sources` | [DataSource](#data-source)[] | True | The configuration entries for Azure OpenAI On Your Data. There must be exactly one element in the array. If `data_sources` is not provided, the service uses chat completions model directly, and does not use Azure OpenAI On Your Data. When you specify the `data_sources` parameter, you won't be able to to use the `logprobs` or `top_logprobs` parameters. |

## Response body

The response body inherits the same schema of chat completions API response. The [response chat message](#chat-message) has a `context` property, which is added for Azure OpenAI On Your Data.

## Chat message

The response assistant message schema inherits from the chat completions assistant [chat message](../reference.md#chatmessage), and is extended with the property `context`.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `context` | [Context](#context) | False | Represents the incremental steps performed by the Azure OpenAI On Your Data while processing the request, including the retrieved documents. |

## Context
|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `citations` | [Citation](#citation)[] | False | The data source retrieval result, used to generate the assistant message in the response. Clients can render references from the citations. |
| `intent` | string | False | The detected intent from the chat history. Passing back the previous intent is no longer needed. Ignore this property. |
| `all_retrieved_documents` | [Retrieved documents](#retrieved-documents)[] | False | All the retrieved documents. |


## Citation

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `content` | string | True | The content of the citation.|
| `title` | string | False | The title of the citation.|
| `url` | string | False | The URL of the citation.|
| `filepath` | string | False | The file path of the citation.|
| `chunk_id` | string | False | The chunk ID of the citation.|

## Retrieved documents

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `search_queries` | string[] | True | The search queries used to retrieve the document. |
| `data_source_index` | integer | True | The index of the data source. |
| `original_search_score` | double | True | The original search score of the retrieved document. |
| `rerank_score` | double | False | The rerank score of the retrieved document. |
| `filter_reason` | string | False | Represents the rationale for filtering the document. If the document does not undergo filtering, this field will remain unset. Will be `score` if the document is filtered by original search score threshold defined by `strictness`. Will be `rerank` if the document is not filtered by original search score threshold, but is filtered by rerank score and `top_n_documents`. |

## Data source

This list shows the supported data sources.

* [Azure AI Search](./azure-search.md)
* [Azure Cosmos DB for MongoDB vCore](./cosmos-db.md)
* [Elasticsearch (preview)](./elasticsearch.md)
* [Pinecone (preview)](./pinecone.md)

## Examples

This example shows how to pass conversation history for better results.

Prerequisites:
* Configure the role assignments from Azure OpenAI system assigned managed identity to Azure search service. Required roles: `Search Index Data Reader`, `Search Service Contributor`.
* Configure the role assignments from the user to the Azure OpenAI resource. Required role: `Cognitive Services OpenAI User`.
* Install [Az CLI](/cli/azure/install-azure-cli), and run `az login`.
* Define the following environment variables: `AzureOpenAIEndpoint`, `ChatCompletionsDeploymentName`,`SearchEndpoint`, `SearchIndex`.
```bash
export AzureOpenAIEndpoint=https://example.openai.azure.com/
export ChatCompletionsDeploymentName=turbo
export SearchEndpoint=https://example.search.windows.net
export SearchIndex=example-index
```


# [Python 1.x](#tab/python)

Install the latest pip packages `openai`, `azure-identity`.

```python
import os
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

endpoint = os.environ.get("AzureOpenAIEndpoint")
deployment = os.environ.get("ChatCompletionsDeploymentName")
search_endpoint = os.environ.get("SearchEndpoint")
search_index = os.environ.get("SearchIndex")

token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

client = AzureOpenAI(
    azure_endpoint=endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2024-05-01-preview",
)

completion = client.chat.completions.create(
    model=deployment,
    messages=[
        {
            "role": "user",
            "content": "Who is DRI?",
        },
        {
            "role": "assistant",
            "content": "DRI stands for Directly Responsible Individual of a service. Which service are you asking about?"
        },
        {
            "role": "user",
            "content": "Opinion mining service"
        }
    ],
    extra_body={
        "data_sources": [
            {
                "type": "azure_search",
                "parameters": {
                    "endpoint": search_endpoint,
                    "index_name": search_index,
                    "authentication": {
                        "type": "system_assigned_managed_identity"
                    }
                }
            }
        ]
    }
)

print(completion.model_dump_json(indent=2))

# render the citations

content = completion.choices[0].message.content
context = completion.choices[0].message.context
for citation_index, citation in enumerate(context["citations"]):
    citation_reference = f"[doc{citation_index + 1}]"
    url = "https://example.com/?redirect=" + citation["url"] # replace with actual host and encode the URL
    filepath = citation["filepath"]
    title = citation["title"]
    snippet = citation["content"]
    chunk_id = citation["chunk_id"]
    replaced_html = f"<a href='{url}' title='{title}\n{snippet}''>(See from file {filepath}, Part {chunk_id})</a>"
    content = content.replace(citation_reference, replaced_html)
print(content)
```

# [REST](#tab/rest)

```bash
az rest --method POST \
 --uri $AzureOpenAIEndpoint/openai/deployments/$ChatCompletionsDeploymentName/chat/completions?api-version=2024-05-01-preview \
 --resource https://cognitiveservices.azure.com/ \
 --body \
'
{
    "data_sources": [
        {
            "type": "azure_search",
            "parameters": {
                "endpoint": "'$SearchEndpoint'",
                "index_name": "'$SearchIndex'",
                "authentication": {
                    "type": "system_assigned_managed_identity"
                }
            }
        }
    ],
    "messages": [
        {
            "role": "user",
            "content": "Who is DRI?"
        },
        {
            "role": "assistant",
            "content": "DRI stands for Directly Responsible Individual of a service. Which service are you asking about?"
        },
        {
            "role": "user",
            "content": "Opinion mining service"
        }
    ]
}
'
```

---

---
title: Azure OpenAI on your Azure Search data Python & REST API reference
titleSuffix: Azure OpenAI
description: Learn how to use Azure OpenAI on your Azure Search data Python & REST API.
manager: nitinme
ms.service: azure-ai-openai
ms.topic: conceptual
ms.date: 09/20/2024
author: aahill
ms.author: aahi
recommendations: false
ms.custom: devx-track-python
---

# Data source - Azure AI Search

The configurable options of Azure AI Search when using Azure OpenAI On Your Data. This data source is supported in API version `2024-02-01`.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
|`parameters`| [Parameters](#parameters)| True| The parameters to use when configuring Azure Search.|
| `type`| string| True | Must be `azure_search`. |

## Parameters

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `endpoint` | string | True | The absolute endpoint path for the Azure Search resource to use.|
| `index_name` | string | True | The name of the index to use in the referenced Azure Search resource.|
| `authentication`| One of [ApiKeyAuthenticationOptions](#api-key-authentication-options), [SystemAssignedManagedIdentityAuthenticationOptions](#system-assigned-managed-identity-authentication-options), [UserAssignedManagedIdentityAuthenticationOptions](#user-assigned-managed-identity-authentication-options), [onYourDataAccessTokenAuthenticationOptions](#access-token-authentication-options) | True | The authentication method to use when accessing the defined data source. |
| `embedding_dependency` | One of [DeploymentNameVectorizationSource](#deployment-name-vectorization-source), [EndpointVectorizationSource](#endpoint-vectorization-source) | False | The embedding dependency for vector search. Required when `query_type` is `vector`, `vector_simple_hybrid`, or `vector_semantic_hybrid`.|
| `fields_mapping` | [FieldsMappingOptions](#fields-mapping-options) | False | Customized field mapping behavior to use when interacting with the search index.|
| `filter`| string | False | Search filter. |
| `in_scope` | boolean | False | Whether queries should be restricted to use of indexed data. Default is `True`.| 
| `query_type` | [QueryType](#query-type) | False | The query type to use with Azure Search. Default is `simple` |
| `role_information`| string | False | Give the model instructions about how it should behave and any context it should reference when generating a response. You can describe the assistant's personality and tell it how to format responses.|
| `semantic_configuration` | string | False | The semantic configuration for the query. Required when `query_type` is `semantic` or `vector_semantic_hybrid`.| 
| `strictness` | integer | False | The configured strictness of the search relevance filtering. The higher of strictness, the higher of the precision but lower recall of the answer. Default is `3`.| 
| `top_n_documents` | integer | False | The configured top number of documents to feature for the configured query. Default is `5`. |
| `max_search_queries` | integer | False | The max number of rewritten queries should be send to search provider for one user message. If not specified, the system will decide the number of queries to send. |
| `allow_partial_result` | integer | False | If specified as true, the system will allow partial search results to be used and the request fails if all the queries fail. If not specified, or specified as false, the request will fail if any search query fails. |
| `include_contexts` | array | False | The included properties of the output context. If not specified, the default value is `citations` and `intent`. Values can be `citations`,`intent`, `all_retrieved_documents`.|

## API key authentication options

The authentication options for Azure OpenAI On Your Data when using an API key.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `key`|string|True|The API key to use for authentication.|
| `type`|string|True| Must be `api_key`.|

## System assigned managed identity authentication options

The authentication options for Azure OpenAI On Your Data when using a system-assigned managed identity.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `type`|string|True| Must be `system_assigned_managed_identity`.|

## User assigned managed identity authentication options

The authentication options for Azure OpenAI On Your Data when using a user-assigned managed identity.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `managed_identity_resource_id`|string|True|The resource ID of the user-assigned managed identity to use for authentication.|
| `type`|string|True| Must be `user_assigned_managed_identity`.|

## Access token authentication options

The authentication options for Azure OpenAI On Your Data when using access token.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `access_token`|string|True|The access token to use for authentication.|
| `type` | string | True | Must be `access_token`. |

## Deployment name vectorization source

The details of the vectorization source, used by Azure OpenAI On Your Data when applying vector search. This vectorization source is based on an internal embeddings model deployment name in the same Azure OpenAI resource. This vectorization source enables you to use vector search without Azure OpenAI api-key and without Azure OpenAI public network access.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `deployment_name`|string|True|The embedding model deployment name within the same Azure OpenAI resource. |
| `type`|string|True| Must be `deployment_name`.|
| `dimensions`|integer|False| The number of dimensions the embeddings should have. Only supported in `text-embedding-3` and later models. |

## Endpoint vectorization source

The details of the vectorization source, used by Azure OpenAI On Your Data when applying vector search. This vectorization source is based on the Azure OpenAI embedding API endpoint.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `endpoint`|string|True|Specifies the resource endpoint URL from which embeddings should be retrieved. It should be in the format of `https://{YOUR_RESOURCE_NAME}.openai.azure.com/openai/deployments/YOUR_DEPLOYMENT_NAME/embeddings`. The api-version query parameter isn't allowed.|
| `authentication`| [ApiKeyAuthenticationOptions](#api-key-authentication-options)|True | Specifies the authentication options to use when retrieving embeddings from the specified endpoint.|
| `type`|string|True| Must be `endpoint`.|
| `dimensions`|integer|False| The number of dimensions the embeddings should have. Only supported in `text-embedding-3` and later models. |


## Fields mapping options

Optional settings to control how fields are processed when using a configured Azure Search resource.

|Name | Type | Required | Description |
|--- | --- | --- | --- |
| `content_fields` | string[] | False | The names of index fields that should be treated as content. |
| `vector_fields` | string[] | False | The names of fields that represent vector data.|
| `content_fields_separator` | string | False | The separator pattern that content fields should use. Default is `\n`.|
| `filepath_field` | string | False | The name of the index field to use as a filepath. |
| `title_field` | string | False | The name of the index field to use as a title. |
| `url_field` | string | False | The name of the index field to use as a URL.|

## Query type

The type of Azure Search retrieval query that should be executed when using it as an Azure OpenAI On Your Data.

|Enum Value | Description |
|---|---|
|`simple`	|Represents the default, simple query parser.|
|`semantic`| Represents the semantic query parser for advanced semantic modeling.|
|`vector`	|Represents vector search over computed data.|
|`vector_simple_hybrid`	|Represents a combination of the simple query strategy with vector data.|
|`vector_semantic_hybrid`	|Represents a combination of semantic search and vector data querying.|

## Examples

Prerequisites:
* Configure the role assignments from Azure OpenAI system assigned managed identity to Azure search service. Required roles: `Search Index Data Reader`, `Search Service Contributor`.
* Configure the role assignments from the user to the Azure OpenAI resource. Required role: `Cognitive Services OpenAI User`.
* Install [Az CLI](/cli/azure/install-azure-cli), and run `az login`.
* Define the following environment variables: `AzureOpenAIEndpoint`, `ChatCompletionsDeploymentName`,`SearchEndpoint`, `SearchIndex`.
```bash
export AzureOpenAIEndpoint=https://example.openai.azure.com/
export ChatCompletionsDeploymentName=turbo
export SearchEndpoint=https://example.search.windows.net
export SearchIndex=example-index
```

# [Python 1.x](#tab/python)

Install the latest pip packages `openai`, `azure-identity`.

```python
import os
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

endpoint = os.environ.get("AzureOpenAIEndpoint")
deployment = os.environ.get("ChatCompletionsDeploymentName")
search_endpoint = os.environ.get("SearchEndpoint")
search_index = os.environ.get("SearchIndex")

token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

client = AzureOpenAI(
    azure_endpoint=endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2024-02-01",
)

completion = client.chat.completions.create(
    model=deployment,
    messages=[
        {
            "role": "user",
            "content": "Who is DRI?",
        },
    ],
    extra_body={
        "data_sources": [
            {
                "type": "azure_search",
                "parameters": {
                    "endpoint": search_endpoint,
                    "index_name": search_index,
                    "authentication": {
                        "type": "system_assigned_managed_identity"
                    }
                }
            }
        ]
    }
)

print(completion.model_dump_json(indent=2))

```

# [REST](#tab/rest)

```bash
az rest --method POST \
 --uri $AzureOpenAIEndpoint/openai/deployments/$ChatCompletionsDeploymentName/chat/completions?api-version=2024-02-01 \
 --resource https://cognitiveservices.azure.com/ \
 --body \
'
{
    "data_sources": [
        {
            "type": "azure_search",
            "parameters": {
                "endpoint": "'$SearchEndpoint'",
                "index_name": "'$SearchIndex'",
                "authentication": {
                    "type": "system_assigned_managed_identity"
                }
            }
        }
    ],
    "messages": [
        {
            "role": "user",
            "content": "Who is DRI?",
        }
    ]
}
'
```

---