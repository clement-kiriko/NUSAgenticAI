import os
import sys
from unittest.mock import Mock, patch

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.geoapify_tools import maps_api


def _geocode_response(lon: float, lat: float):
    response = Mock()
    response.status_code = 200
    response.text = '{"features":[{"geometry":{"coordinates":[0,0]}}]}'
    response.json.return_value = {"features": [{"geometry": {"coordinates": [lon, lat]}}]}
    response.request = Mock(url="https://api.geoapify.com/v1/geocode/search?apiKey=12345678")
    return response


def test_maps_api_returns_straight_line_fallback_for_over_limit_route():
    origin_response = _geocode_response(24.7572724, 59.4372342)
    destination_response = _geocode_response(115.1919203, -8.2271303)

    with patch.dict(os.environ, {"GEOAPIFY_API_KEY": "12345678"}, clear=True):
        with patch(
            "tools.geoapify_tools._geoapify_get",
            side_effect=[origin_response, destination_response],
        ):
            result = maps_api("city_center", "Bali, Indonesia")

    assert result["source"] == "geoapify_distance_fallback"
    assert result["typical_taxi_minutes"] is None
    assert result["distance_km"] == 10819.1
    assert "distance limit" in result["note"]


def test_maps_api_returns_straight_line_fallback_when_routing_api_rejects_limit():
    origin_response = _geocode_response(0, 0)
    destination_response = _geocode_response(1, 1)
    route_response = Mock(status_code=400, text='{"message":"Distance should not exceed 10000000 meters. Estimated distance is 10819091 meter(s)."}')
    route_response.json.return_value = {
        "message": "Distance should not exceed 10000000 meters. Estimated distance is 10819091 meter(s)."
    }
    route_response.request = httpx.Request("GET", "https://api.geoapify.com/v1/routing")
    route_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Client error '400 Bad Request' for url 'https://api.geoapify.com/v1/routing'",
        request=route_response.request,
        response=route_response,
    )

    with patch.dict(os.environ, {"GEOAPIFY_API_KEY": "12345678"}, clear=True):
        with patch(
            "tools.geoapify_tools._geoapify_get",
            side_effect=[origin_response, destination_response, route_response.raise_for_status.side_effect],
        ):
            result = maps_api("A", "B")

    assert result["source"] == "geoapify_distance_fallback"
    assert result["typical_taxi_minutes"] is None
    assert result["distance_km"] == 157.2


def test_maps_api_returns_mock_fallback_on_unexpected_error():
    with patch.dict(os.environ, {"GEOAPIFY_API_KEY": "12345678"}, clear=True):
        with patch("tools.geoapify_tools._geoapify_get", side_effect=RuntimeError("boom")):
            result = maps_api("A", "B")

    assert result["source"] == "mock_maps"
    assert result["typical_taxi_minutes"] == 20
