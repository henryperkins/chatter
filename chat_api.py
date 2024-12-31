from azure_config import get_azure_client, initialize_client_from_model
from models import Model
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def get_azure_response(messages, deployment_name, selected_model_id=None):
    try:
        client, deployment_name = get_azure_client()
        if selected_model_id:
            model = Model.get_by_id(selected_model_id)
            if model:
                client, deployment_name, temperature, max_tokens = initialize_client_from_model(model.__dict__)
            else:
                raise ValueError("Selected model not found")

        api_messages = [{"role": msg["role"], "content": msg["content"]} for msg in messages if msg["role"] in ["user", "assistant"]]

        response = client.chat.completions.create(
            model=deployment_name,
            messages=api_messages,
            temperature=1 if "o1-preview" in deployment_name else 0.7,
            max_tokens=None if "o1-preview" in deployment_name else 500,
            max_completion_tokens=500 if "o1-preview" in deployment_name else None,
            api_version="2024-12-01-preview" if "o1-preview" in deployment_name else None
        )

        model_response = response.choices[0].message.content if response.choices[0].message else "The assistant was unable to generate a response. Please try again or rephrase your input."
        logger.info(f"Response received from the model: {model_response}")
        return model_response

    except Exception as e:
        logger.error(f"Error in get_azure_response: {str(e)}")
        raise

def scrape_data(query):
    if query.startswith("what's the weather in"):
        location = query.split("what's the weather in")[1].strip()
        return scrape_weather(location)
    elif query.startswith("search for"):
        search_term = query.split("search for")[1].strip()
        return scrape_search(search_term)
    else:
        raise ValueError("Invalid query type")

def scrape_weather(location):
    url = f"https://www.google.com/search?q=weather+{location}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    weather = soup.find("div", class_="BNeawe").text
    return f"The weather in {location} is: {weather}"

def scrape_search(search_term):
    url = f"https://www.google.com/search?q={search_term}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    results = soup.find_all("div", class_="BNeawe s3v9rd AP7Wnd")
    search_results = [result.text for result in results[:3]]
    return "Search results:\n" + "\n".join(search_results)
