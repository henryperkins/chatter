# Azure OpenAI Chat Application

A real-time chat application built with Flask and Azure OpenAI's o1-preview model. This application features a web interface for chat interactions, supports web scraping for weather and search queries, and maintains conversation history.

## Features

- Real-time chat interface with Azure OpenAI's o1-preview model
- Web scraping capabilities for weather and search queries
- Multiple chat sessions support
- Markdown-formatted responses
- Modern, responsive web UI

## Prerequisites

- Python 3.8 or higher
- Azure OpenAI account with o1-preview model deployment
- Azure OpenAI API credentials

## Setup

1. Clone the repository and navigate to the project directory

2. Create and activate a virtual environment:
```bash
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a .env file:
   - Copy .env.template to .env
   - Fill in your Azure OpenAI credentials:
     - AZURE_OPENAI_ENDPOINT
     - AZURE_OPENAI_KEY
     - AZURE_OPENAI_API_VERSION
     - AZURE_OPENAI_DEPLOYMENT_NAME

## Running the Application

1. Ensure your virtual environment is activated
2. Run the Flask application:
```bash
python app.py
```
3. Open your web browser and navigate to `http://127.0.0.1:5000`

## Usage

- Enter messages in the chat input field
- Press Enter or click Send to submit
- Use "what's the weather in [location]" or "search for [query]" to trigger web scraping
- Each browser session maintains its own chat history

## Notes

- The o1-preview model requires specific parameters:
  - Temperature is fixed at 1
  - Only user messages are supported (no system messages)
  - Streaming is not supported
  - Uses API version 2024-12-01-preview
