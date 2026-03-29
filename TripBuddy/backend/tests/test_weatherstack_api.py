import os
import sys
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.weatherstack_api import weather_api


def test_weather_api_returns_fallback_when_api_key_missing():
    with patch.dict(os.environ, {}, clear=True):
        result = weather_api("Vietnam")

    assert result["source"] == "fallback"
    assert result["temperature"] == "N/A"
    assert "Vietnam" in result["forecast"]


def test_weather_api_returns_fallback_on_weatherstack_error_payload():
    response = Mock()
    response.status_code = 400
    response.text = '{"success":false,"error":{"code":615,"type":"request_failed","info":"Your API request failed."}}'
    response.json.return_value = {
        "success": False,
        "error": {"code": 615, "type": "request_failed", "info": "Your API request failed."},
    }
    response.request = Mock(
        url="http://api.weatherstack.com/current?access_key=12345678&query=vietnam&units=m",
        headers={},
    )

    with patch.dict(os.environ, {"WEATHERSTACK_API_KEY": "12345678"}, clear=True):
        with patch("tools.weatherstack_api.requests.get", return_value=response):
            result = weather_api("Vietnam")

    assert result["source"] == "fallback"
    assert result["error"] == "api error status=400: Your API request failed."


def test_weather_api_returns_fallback_on_request_exception():
    with patch.dict(os.environ, {"WEATHERSTACK_API_KEY": "12345678"}, clear=True):
        with patch("tools.weatherstack_api.requests.get", side_effect=requests.RequestException("timeout")):
            result = weather_api("Vietnam")

    assert result["source"] == "fallback"
    assert result["error"] == "request failed: timeout"
