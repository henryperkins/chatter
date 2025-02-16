chat completions:
```json
{
  "title": "Creates a completion for the provided prompt, parameters and chosen model.",
  "parameters": {
    "endpoint": "{endpoint}",
    "api-version": "2025-01-01-preview",
    "deployment-id": "<deployment-id>",
    "body": {
      "messages": [
        {
          "role": "system",
          "content": "you are a helpful assistant that talks like a pirate"
        },
        {
          "role": "user",
          "content": "can you tell me how to care for a parrot?"
        }
      ]
    }
  },
  "responses": {
    "200": {
      "body": {
        "id": "chatcmpl-7R1nGnsXO8n4oi9UPz2f3UHdgAYMn",
        "created": 1686676106,
        "choices": [
          {
            "index": 0,
            "finish_reason": "stop",
            "message": {
              "role": "assistant",
              "content": "Ahoy matey! So ye be wantin' to care for a fine squawkin' parrot, eh? Well, shiver me timbers, let ol' Cap'n Assistant share some wisdom with ye! Here be the steps to keepin' yer parrot happy 'n healthy:\n\n1. Secure a sturdy cage: Yer parrot be needin' a comfortable place to lay anchor! Be sure ye get a sturdy cage, at least double the size of the bird's wingspan, with enough space to spread their wings, yarrrr!\n\n2. Perches 'n toys: Aye, parrots need perches of different sizes, shapes, 'n textures to keep their feet healthy. Also, a few toys be helpin' to keep them entertained 'n their minds stimulated, arrrh!\n\n3. Proper grub: Feed yer feathered friend a balanced diet of high-quality pellets, fruits, 'n veggies to keep 'em strong 'n healthy. Give 'em fresh water every day, or ye’ll have a scurvy bird on yer hands!\n\n4. Cleanliness: Swab their cage deck! Clean their cage on a regular basis: fresh water 'n food daily, the floor every couple of days, 'n a thorough scrubbing ev'ry few weeks, so the bird be livin' in a tidy haven, arrhh!\n\n5. Socialize 'n train: Parrots be a sociable lot, arrr! Exercise 'n interact with 'em daily to create a bond 'n maintain their mental 'n physical health. Train 'em with positive reinforcement, treat 'em kindly, yarrr!\n\n6. Proper rest: Yer parrot be needin' ’bout 10-12 hours o' sleep each night. Cover their cage 'n let them slumber in a dim, quiet quarter for a proper night's rest, ye scallywag!\n\n7. Keep a weather eye open for illness: Birds be hidin' their ailments, arrr! Be watchful for signs of sickness, such as lethargy, loss of appetite, puffin' up, or change in droppings, and make haste to a vet if need be.\n\n8. Provide fresh air 'n avoid toxins: Parrots be sensitive to draft and pollutants. Keep yer quarters well ventilated, but no drafts, arrr! Be mindful of toxins like Teflon fumes, candles, or air fresheners.\n\nSo there ye have it, me hearty! With proper care 'n commitment, yer parrot will be squawkin' \"Yo-ho-ho\" for many years to come! Good luck, sailor, and may the wind be at yer back!"
            }
          }
        ],
        "usage": {
          "completion_tokens": 557,
          "prompt_tokens": 33,
          "total_tokens": 590
        }
      }
    }
  }
}
```

---

```python
import os  
import base64
from openai import AzureOpenAI  

endpoint = os.getenv("ENDPOINT_URL", "https://o1models.openai.azure.com/")  
deployment = os.getenv("DEPLOYMENT_NAME", "o1-east2")  
subscription_key = os.getenv("AZURE_OPENAI_API_KEY", "REPLACE_WITH_YOUR_KEY_VALUE_HERE")  

# Initialize Azure OpenAI Service client with key-based authentication    
client = AzureOpenAI(  
    azure_endpoint=endpoint,  
    api_key=subscription_key,  
    api_version="2024-12-01-preview",
)
    
    
IMAGE_PATH = "YOUR_IMAGE_PATH"
encoded_image = base64.b64encode(open(IMAGE_PATH, 'rb').read()).decode('ascii')

#Prepare the chat prompt 
chat_prompt = [
    {
        "role": "developer",
        "content": [
            {
                "type": "text",
                "text": "You are an AI assistant that helps people find information."
            }
        ]
    }
] 
    
# Include speech result if speech is enabled  
messages = chat_prompt  
    
# Generate the completion  
completion = client.chat.completions.create(  
    model=deployment,
    messages=messages,
    max_completion_tokens=40000,
    stop=None,  
    stream=False
)

print(completion.to_json())  
```


---


[Source code](https://github.com/openai/openai-node) | [Package (npm)](https://www.npmjs.com/package/openai) | [Reference](../../reference.md) |


## Azure OpenAI API version support

Feature availability in Azure OpenAI is dependent on what version of the REST API you target. For the newest features, target the latest preview API.

| Latest GA API | Latest Preview API|
|:-----|:------|
|`2024-10-21` |`2025-01-01-preview`|

## Installation

```cmd
npm install openai
```

## Authentication


# [API Key](#tab/api-key)


API keys are not recommended for production use because they are less secure than other authentication methods. 

```typescript
import { AzureKeyCredential } from "@azure/openai";
const apiKey = new AzureKeyCredential("your API key");
const endpoint = "https://your-azure-openai-resource.com";0
const apiVersion = "2024-10-21"

const client = new AzureOpenAI({ apiKey, endpoint, apiVersion });
```

`AzureOpenAI` can be authenticated with an API key by setting the `AZURE_OPENAI_API_KEY` environment variable or by setting the `apiKey` string property in the options object when creating the `AzureOpenAI` client.

[!INCLUDE [Azure key vault](~/reusable-content/ce-skilling/azure/includes/ai-services/security/azure-key-vault.md)]

---

## Audio

### Transcription

```typescript
import { createReadStream } from "fs";

const result = await client.audio.transcriptions.create({
  model: '',
  file: createReadStream(audioFilePath),
});
```

## Chat

`chat.completions.create`

```typescript
const result = await client.chat.completions.create({ messages, model: '', max_tokens: 100 });
```

### Streaming

```typescript
const stream = await client.chat.completions.create({ model: '', messages, max_tokens: 100, stream: true });
```

## Embeddings

```typescript
const embeddings = await client.embeddings.create({ input, model: '' });
```

## Image generation

```typescript
  const results = await client.images.generate({ prompt, model: '', n, size });
```

## Error handling

### Error codes

| Status Code | Error Type |
|----|---|
| 400         | `Bad Request Error`          |
| 401         | `Authentication Error`       |
| 403         | `Permission Denied Error`    |
| 404         | `Not Found Error`            |
| 422         | `Unprocessable Entity Error` |
| 429         | `Rate Limit Error`           |
| 500         | `Internal Server Error`      |
| 503         | `Service Unavailable`       |
| 504         | `Gateway Timeout` |

### Retries

The following errors are automatically retired twice by default with a brief exponential backoff:

- Connection Errors
- 408 Request Timeout
- 429 Rate Limit
- `>=`500 Internal Errors

Use `maxRetries` to set/disable the retry behavior:

```typescript
// Configure the default for all requests:
const client = new AzureOpenAI({
  maxRetries: 0, // default is 2
});

// Or, configure per-request:
await client.chat.completions.create({ messages: [{ role: 'user', content: 'How can I get the name of the current day in Node.js?' }], model: '' }, {
  maxRetries: 5,
});
```