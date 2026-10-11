"""Kakao-specific internal adapter; not a Canonical Contract or service capability.

Composition root supplies credentials and timeout. No environment reads, retries,
redirects, logging, provider fallback, or mutation of the input GPS observation.
"""
from dataclasses import dataclass, field
from http.client import HTTPException, HTTPSConnection
import json
import math
from typing import Literal
from urllib.parse import urlencode

from pydantic import ValidationError

from .models import GPSObservation


Failure = Literal[
    "INVALID_INPUT", "GPS_NOT_OK", "TIMEOUT", "AUTHENTICATION", "RATE_LIMIT",
    "SERVER_ERROR", "HTTP_ERROR", "TRANSPORT_ERROR", "INVALID_JSON",
    "INVALID_SCHEMA", "EMPTY_RESULT",
]


@dataclass(frozen=True)
class KakaoAddress:
    address_name: str = field(repr=False)
    # Provider address details only, not the full response. Immutable and not logged.
    details: tuple[tuple[str, str], ...] = field(repr=False)


@dataclass(frozen=True)
class KakaoGeocoderResult:
    status: Literal["OK", "SKIPPED", "FAILED"]
    failure: Failure | None = None
    address: KakaoAddress | None = field(default=None, repr=False)
    road_address: KakaoAddress | None = field(default=None, repr=False)


def _address(value: object) -> KakaoAddress | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("address_name"), str):
        raise ValueError
    if not value["address_name"].strip() or any(not isinstance(v, str) for v in value.values()):
        raise ValueError
    return KakaoAddress(value["address_name"], tuple(value.items()))


def _parse(body: bytes) -> KakaoGeocoderResult:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError, RecursionError):
        return KakaoGeocoderResult("FAILED", "INVALID_JSON")
    try:
        if not isinstance(data, dict) or not isinstance(data.get("meta"), dict):
            raise ValueError
        count = data["meta"].get("total_count")
        documents = data.get("documents")
        if type(count) is not int or count not in (0, 1) or not isinstance(documents, list) or len(documents) != count:
            raise ValueError
        if not documents:
            return KakaoGeocoderResult("FAILED", "EMPTY_RESULT")
        document = documents[0]
        if not isinstance(document, dict):
            raise ValueError
        address = _address(document.get("address"))
        road_address = _address(document.get("road_address"))
        if address is None and road_address is None:
            raise ValueError
        return KakaoGeocoderResult("OK", address=address, road_address=road_address)
    except ValueError:
        return KakaoGeocoderResult("FAILED", "INVALID_SCHEMA")


class KakaoReverseGeocoder:
    def __init__(self, *, api_key: str, timeout_sec: float):
        if (not isinstance(api_key, str) or not api_key or
                any(not 33 <= ord(c) <= 126 for c in api_key) or
                type(timeout_sec) not in (int, float) or not math.isfinite(timeout_sec) or timeout_sec <= 0):
            raise ValueError("Invalid geocoder configuration")
        self._api_key = api_key
        self._timeout_sec = timeout_sec

    def reverse_geocode(self, observation: GPSObservation) -> KakaoGeocoderResult:
        # Revalidation also rejects model_copy/model_construct bypasses. Never return
        # Pydantic errors containing the original coordinates or provenance.
        try:
            if not isinstance(observation, GPSObservation):
                return KakaoGeocoderResult("FAILED", "INVALID_INPUT")
            checked = GPSObservation.model_validate(observation)
        except ValidationError:
            return KakaoGeocoderResult("FAILED", "INVALID_INPUT")
        if checked.status != "OK":
            return KakaoGeocoderResult("SKIPPED", "GPS_NOT_OK")
        coordinate = checked.value
        query = urlencode({"x": coordinate.lon, "y": coordinate.lat, "input_coord": "WGS84"})
        connection = None
        try:
            # stdlib HTTPS verifies TLS by default; no proxy/env or redirects used.
            connection = HTTPSConnection("dapi.kakao.com", timeout=self._timeout_sec)
            connection.request("GET", "/v2/local/geo/coord2address.json?" + query,
                               headers={"Authorization": "KakaoAK " + self._api_key})
            response = connection.getresponse()
            if response.status in (401, 403):
                return KakaoGeocoderResult("FAILED", "AUTHENTICATION")
            if response.status == 429:
                return KakaoGeocoderResult("FAILED", "RATE_LIMIT")
            if 500 <= response.status <= 599:
                return KakaoGeocoderResult("FAILED", "SERVER_ERROR")
            if response.status != 200:
                return KakaoGeocoderResult("FAILED", "HTTP_ERROR")
            return _parse(response.read())
        except TimeoutError:
            return KakaoGeocoderResult("FAILED", "TIMEOUT")
        except (OSError, HTTPException):
            return KakaoGeocoderResult("FAILED", "TRANSPORT_ERROR")
        finally:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    # Cleanup must not replace the completed request's result.
                    pass
