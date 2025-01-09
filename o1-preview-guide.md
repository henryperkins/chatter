### Overview:
The `o1-preview` models from Azure OpenAI are specialized reasoning models with distinct requirements and usage patterns. This section outlines the key requirements and provides guidance for interacting with these models effectively.

---

### **Key Requirements of `o1-preview` Models:**

1. **No System Messages:**  
   - `o1-preview` models do not support system messages. Ensure that your prompts do not include a system message when making API calls.

2. **No Streaming:**  
   - These models do not support streaming. Use non-streaming methods (e.g., `client.chat.completions.create` instead of `client.chat.completions.acreate`) to receive the complete response at once.

3. **Temperature Fixed at 1:**  
   - The `temperature` parameter must always be set to `1` for `o1-preview` models.

4. **`max_completion_tokens`:**  
   - Use the `max_completion_tokens` parameter instead of `max_tokens` to specify the maximum number of tokens to generate in the completion.

5. **Specific API Version:**  
   - `o1-preview` models require a specific API version. Use `2024-12-01-preview` or newer. Always verify the correct API version in the Azure OpenAI documentation.

---

### **Example API Call for `o1-preview`:**

```python
from openai import AzureOpenAI

# Initialize the Azure OpenAI client
client = AzureOpenAI(
    api_version="2024-12-01-preview",  # Use the correct API version
    azure_endpoint="https://your-resource.openai.azure.com/",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
)

# Example API call
response = client.chat.completions.create(
    model="your-o1-preview-deployment",  # Replace with your o1-preview deployment name
    messages=[
        {"role": "user", "content": "Your prompt here"},  # No system message
    ],
    temperature=1,  # Temperature must be 1
    max_completion_tokens=500,  # Use max_completion_tokens
)

# Print the response
print(response.model_dump_json(indent=2))
```

---

### **Important Considerations:**

1. **Verify Feature Support:**  
   - Confirm which features (e.g., function calling, structured output, prompt caching) are supported by `o1-preview` models by consulting the Azure OpenAI documentation or through experimentation.

2. **Error Handling:**  
   - Implement robust error handling to catch issues specific to `o1-preview` models. For example, validate API responses and handle errors like invalid parameters or unsupported features.

3. **User Guidance:**  
   - Provide clear instructions to users on how to add and configure `o1-preview` models in your application or plugin settings, including the specific requirements for these models.

4. **Testing:**  
   - Thoroughly test your application with an actual `o1-preview` deployment to ensure all features work as expected and that the specific requirements of these models are met.

---

### **Testing Checklist:**
- Validate that prompts exclude system messages.
- Ensure the `temperature` parameter is set to `1`.
- Confirm that `max_completion_tokens` is used instead of `max_tokens`.
- Test with the correct API version (`2024-12-01-preview` or newer).
- Verify that the response adheres to expected behavior and structure.

---

### **References:**
- [Azure OpenAI o1 Series Reasoning Models Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/reasoning?tabs=python#usage)
- [Azure OpenAI API Reference](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference)
