import os
import requests

def weather_api(city: str):
    response = requests.get(
        "http://api.weatherstack.com/current",
        params={
            "access_key": os.getenv("WEATHERSTACK_API_KEY"),
            "query": city,
            "units": "m",
        },
    )

    data = response.json()

    # Optional: handle API errors
    if "current" not in data:
        raise ValueError(f"Weatherstack error: {data}")

    return {
        "forecast": data["current"]["weather_descriptions"][0],
        "temperature": f"{data['current']['temperature']}°C",
    }