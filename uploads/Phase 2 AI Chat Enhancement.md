# Phase 2: AI-Powered Chat - Enhancement 

## **Overview**

Phase 2 focuses on enhancing the chat application with AI capabilities, now considering both project-based and independent conversations. The goal is to integrate an AI assistant to provide intelligent responses, real-time suggestions, and sentiment analysis. This phase builds upon the foundational components developed in Phase 1, adding a layer of intelligence to the chat experience. Key objectives include:

-   **AI Assistant Integration:** Integrate an AI service (e.g., Claude API or OpenAI API) capable of handling different language models.
-   **Contextual Responses:** Provide contextually relevant AI responses, including RAG for project-based chats and standard LLM responses for independent chats.
-   **Real-time Suggestions:** Offer real-time suggestions as users type, taking into account project context or conversation history.
-   **Sentiment Analysis:** Implement basic sentiment analysis of user messages.

By the end of Phase 2, the chat application will be able to engage in more intelligent and interactive conversations, setting the stage for advanced AI features in subsequent phases, while distinguishing between project based context and non project conversations.

---

## **Core Components Implementation Requirements**

### **1. AI Assistant Integration**

#### **Required Functionality**

-   **API Integration:**
    -   Integrate with an AI service (e.g., Claude API or OpenAI API), handling different language models.
    -   Handle API requests and responses, including error handling and rate limiting.
    -   **Error Handling:** Handle API errors gracefully, logging errors with relevant context and providing user-friendly feedback.
    -   **Security:** Securely store API keys and manage access to the AI service.
    -   **RAG and Non-RAG Support:** The AI assistant needs to be able to provide responses based on the project context (using RAG) if a `project_id` is provided, and to provide regular LLM-based responses if there is no `project_id`.
        - If a `project_id` is given, use the language model set for that project, otherwise use a default language model.

#### **Class Structure (Server-Side - Example)**

```python
class AIAssistant:
    def __init__(self, api_key):
        self.api_key = api_key
        # ... other initialization

    def get_ai_response(self, message, conversation_history, project_id = None, language_model = 'gpt-3.5-turbo') -> str:
        """Gets a response from the AI assistant, taking into account project context or providing a normal response if there is no project_id.
           If a project_id is given, the language model for the project should be used, else use the provided default
        """
        # ... logic to send API request and process response, using RAG context if project_id is not None
        pass
```

**Additional Notes:**

-   **Performance:** Optimize API calls for minimal latency. Consider caching responses where appropriate.
-   **Context Management:** Maintain conversation history to provide context for the AI assistant, differentiating project-specific conversations from unassociated conversations.
-   **Rate Limiting:** Implement strategies to handle API rate limits.

---

### **2. Real-time Suggestions**

#### **Required Functionality**

-   **Suggestion Generation:**
    -   Generate real-time suggestions based on user input, using the AI assistant, taking into account project context or conversation history.
    -   Display suggestions in the user interface.
    -   **Error Handling:** Handle cases where suggestions cannot be generated (e.g., API errors).
    -   **Performance:** Optimize suggestion generation for minimal latency.
    -   If a `project_id` is given, use the RAG context to suggest responses, otherwise use the conversation history

#### **Class Structure (Server-Side - Example)**

```python
class SuggestionEngine:
    def __init__(self, ai_assistant):
        self.ai_assistant = ai_assistant

    def get_suggestions(self, partial_message, conversation_history, project_id = None) -> list:
        """Generates suggestions based on partial message, using RAG context if a project_id is passed, otherwise based on the conversation history."""
        # ... logic to generate suggestions using the AI assistant, using RAG context if a project_id is passed
        pass
```

**Additional Notes:**

-   **User Interface Integration:** Integrate suggestions seamlessly into the chat UI.
-   **Relevance:** Ensure suggestions are contextually relevant and helpful.
-   **Filtering:** Implement filtering to avoid inappropriate or irrelevant suggestions.

---

### **3. Sentiment Analysis**

#### **Required Functionality**

-   **Message Analysis:**
    - Use a sentiment analysis library or service to analyze user messages.
    -   **Integration:** Integrate sentiment analysis into the AI response generation.
    - **Performance:** Optimize sentiment analysis to avoid excessive processing.

#### **Class Structure (Server-Side - Example)**

```python
class SentimentAnalyzer:
    def analyze_sentiment(self, message) -> float:
        """Analyzes the sentiment of the message and returns a score"""
        # ... logic to use an NLP library to determine the message's sentiment
        pass
```

---

### **Configuration System**

#### **Environment Variables**

-   `OPENAI_API_KEY`: The API key for the OpenAI API (or similar).
-   `CLAUDE_API_KEY`: The API key for the Claude API (or similar).
-   `SUGGESTION_ENGINE_ENABLED`: Flag to enable or disable the suggestion engine.
-   `MAX_SUGGESTIONS`: The maximum number of suggestions to display.

---

### **Error Handling**

*   Continue to refine error handling and logging for AI-related functionalities.

---

### **Conclusion**

Implementing Phase 2 introduces AI capabilities into the chat application, while taking into account the support for project-based and independent conversations. By integrating an AI assistant that can provide responses with RAG when it is called for, providing real-time suggestions, and performing sentiment analysis, the chat experience becomes more intelligent and engaging. This enhanced foundation prepares the application for more advanced AI features and a refined user experience in subsequent phases.

That's Phase 2. Let me know when you're ready for Phase 3!
