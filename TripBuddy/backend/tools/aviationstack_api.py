import requests
import datetime
import os

def flight_api(origin: str, destination: str, days: int):
    departure_date = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()

    response = requests.get(
        "http://api.aviationstack.com/v1/flights",
        params={
            "access_key": os.getenv("AVIATIONSTACK_API_KEY"),
            "dep_iata": origin,
            "arr_iata": destination,
            "flight_date": departure_date,
        },
    )

    data = response.json()

    return [
        {
            "airline": flight["airline"]["name"],
            "flight_number": flight["flight"]["iata"],
            "departure_time": flight["departure"]["scheduled"],
            "arrival_time": flight["arrival"]["scheduled"],
        }
        for flight in data.get("data", [])
        if flight.get("airline")
    ]
