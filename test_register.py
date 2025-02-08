import requests
import json

def test_registration():
    url = 'http://localhost:5000/auth/register'
    
    # First, get the CSRF token by making a GET request
    session = requests.Session()
    response = session.get(url)
    
    # Extract CSRF token from the response HTML
    import re
    csrf_token = re.search(r'name="csrf-token" content="([^"]+)"', response.text)
    if csrf_token:
        csrf_token = csrf_token.group(1)
        print(f"Found CSRF token: {csrf_token}")
    else:
        print("CSRF token not found in response")
        return

    # Registration data
    data = {
        'csrf_token': csrf_token,
        'username': 'hperkins',
        'email': 'htperkins@gmail.com',
        'password': 'Twiohmld1!',
        'confirm_password': 'Twiohmld1!'
    }

    # Headers
    headers = {
        'X-CSRFToken': csrf_token,
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/json'
    }

    # Make the registration request
    response = session.post(url, json=data, headers=headers)
    
    # Print response details
    print(f"\nStatus Code: {response.status_code}")
    print("Response Headers:")
    for key, value in response.headers.items():
        print(f"{key}: {value}")
    print("\nResponse Body:")
    try:
        print(json.dumps(response.json(), indent=2))
    except:
        print(response.text)

if __name__ == '__main__':
    test_registration()