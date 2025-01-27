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

4. Create a `.env` file:

   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env  # For Linux/Mac
     copy .env.example .env  # For Windows
     ```
   - Fill in your Azure OpenAI credentials and other required configuration variables in the `.env` file.

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

## Security

- **Important:** Never commit your `.env` file or any file containing sensitive information like API keys or secrets.
- Regenerate any keys that might have been exposed in previous commits to ensure the security of your application.

## Cleaning Up Exposed Secrets

If you have accidentally committed sensitive information:

1. **Remove the file from Git tracking:**
   ```bash
   git rm --cached .env
   ```

2. **Clean the file from your Git history:**
   - Use the [BFG Repo-Cleaner](https://rtyley.github.io/bfg-repo-cleaner/) or the `git filter-repo` tool to remove the file from your repository's history.
   - Follow the tool's documentation carefully to ensure all traces are removed.

3. **Force push the cleaned history to GitHub:**
   ```bash
   git push origin --force --all
   ```

   > **Warning:** Force pushing can overwrite commits on the remote repository. Ensure you coordinate with any collaborators before doing this.

4. **Regenerate your API keys and secrets:**
   - Log in to your Azure portal and regenerate your Azure OpenAI Key.
   - Update your `.env` file with the new credentials.

