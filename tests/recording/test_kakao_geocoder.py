"""No network or real credential: exercise the actual HTTP request boundary."""
import json
import logging
from urllib.parse import parse_qs, urlsplit

import pytest

from daesingo.recording import load_recording_fixture
from daesingo.recording import kakao_geocoder as module


KEY = "test-only-not-a-real-key"
ROAD = "synthetic-road-address"
LOT = "synthetic-lot-address"


def payload(road=True):
    return {"meta": {"total_count": 1}, "documents": [{
        "address": {"address_name": LOT, "main_address_no": "1"},
        "road_address": {"address_name": ROAD, "road_name": "synthetic-road"} if road else None,
    }]}


@pytest.fixture
def http(monkeypatch):
    class Connection:
        status = 200
        body = json.dumps(payload()).encode()
        error = None
        read_error = None
        close_error = None
        instances = []

        def __init__(self, host, *, timeout):
            self.host, self.timeout = host, timeout
            self.closed = False
            self.instances.append(self)

        def request(self, method, url, *, headers):
            self.method, self.url, self.headers = method, url, headers
            if self.error:
                raise self.error

        def getresponse(self):
            return self

        def read(self):
            if self.read_error:
                raise self.read_error
            return self.body

        def close(self):
            self.closed = True
            if self.close_error:
                raise self.close_error

    monkeypatch.setattr(module, "HTTPSConnection", Connection)
    return Connection


def observation():
    return load_recording_fixture("scenario_happy_001").gps_observations[0]


def adapter():
    return module.KakaoReverseGeocoder(api_key=KEY, timeout_sec=2.5)


@pytest.mark.parametrize("road", [True, False])
def test_success_and_request_mapping(http, road):
    http.body = json.dumps(payload(road)).encode()
    gps = observation()
    before = gps.model_dump()
    result = adapter().reverse_geocode(gps)
    assert result.status == "OK" and result.failure is None
    assert result.address.address_name == LOT
    assert (result.road_address.address_name if result.road_address else None) == (ROAD if road else None)
    conn = http.instances[0]
    assert conn.host == "dapi.kakao.com" and conn.method == "GET"
    assert conn.timeout == 2.5 and conn.closed
    url = urlsplit(conn.url)
    assert url.path == "/v2/local/geo/coord2address.json"
    assert parse_qs(url.query) == {"x": [str(gps.value.lon)], "y": [str(gps.value.lat)], "input_coord": ["WGS84"]}
    assert conn.headers["Authorization"] == f"KakaoAK {KEY}"
    assert gps.model_dump() == before


@pytest.mark.parametrize("status,code", [(401, "AUTHENTICATION"), (403, "AUTHENTICATION"),
    (429, "RATE_LIMIT"), (500, "SERVER_ERROR"), (503, "SERVER_ERROR"), (400, "HTTP_ERROR"), (302, "HTTP_ERROR")])
def test_http_failures_do_not_retry_or_change_gps(http, status, code):
    http.status = status
    http.body = b"sensitive-provider-error"
    gps = observation()
    before = gps.model_dump()
    result = adapter().reverse_geocode(gps)
    assert result.status == "FAILED" and result.failure == code
    assert result.address is None and result.road_address is None
    assert len(http.instances) == 1 and http.instances[0].closed
    assert gps.model_dump() == before


@pytest.mark.parametrize("error,code", [(TimeoutError("sensitive-error"), "TIMEOUT"), (OSError("sensitive-error"), "TRANSPORT_ERROR")])
def test_transport_failure(http, error, code):
    http.error = error
    assert adapter().reverse_geocode(observation()).failure == code
    assert len(http.instances) == 1 and http.instances[0].closed


def test_read_timeout_closes_connection(http):
    http.read_error = TimeoutError("sensitive-response")
    assert adapter().reverse_geocode(observation()).failure == "TIMEOUT"
    assert http.instances[0].closed


@pytest.mark.parametrize("http_status,error_type,read_error_type,status,code", [
    (200, None, None, "OK", None),
    (401, None, None, "FAILED", "AUTHENTICATION"),
    (200, TimeoutError, None, "FAILED", "TIMEOUT"),
    (200, OSError, None, "FAILED", "TRANSPORT_ERROR"),
    (200, None, TimeoutError, "FAILED", "TIMEOUT"),
    (200, None, OSError, "FAILED", "TRANSPORT_ERROR"),
])
def test_close_oserror_preserves_result_and_privacy(
    http, caplog, http_status, error_type, read_error_type, status, code,
):
    caplog.set_level(logging.DEBUG)
    gps = observation()
    message = f"{KEY} {gps.value.lat} {gps.value.lon} {ROAD} {LOT} sensitive-close-error"
    http.status = http_status
    http.error = error_type(message) if error_type else None
    http.read_error = read_error_type(message) if read_error_type else None
    http.close_error = OSError(message)
    geocoder = adapter()

    result = geocoder.reverse_geocode(gps)

    assert result.status == status and result.failure == code
    if status == "OK":
        assert result.address.address_name == LOT
        assert result.road_address.address_name == ROAD
    else:
        assert result.address is None and result.road_address is None
    assert len(http.instances) == 1 and http.instances[0].closed
    text = str(result) + repr(result) + repr(geocoder) + caplog.text
    for secret in (KEY, str(gps.value.lat), str(gps.value.lon), ROAD, LOT, "sensitive-close-error"):
        assert secret not in text
    assert not caplog.records


def test_close_non_oserror_is_not_suppressed(http):
    http.close_error = RuntimeError("synthetic-close-error")
    with pytest.raises(RuntimeError, match="synthetic-close-error"):
        adapter().reverse_geocode(observation())


def test_json_recursion_error_is_invalid_json(http, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    gps = observation()
    geocoder = adapter()
    message = f"{KEY} {gps.value.lat} {gps.value.lon} {ROAD} {LOT} sensitive-parser-error"

    def fail_parse(body):
        raise RecursionError(message)

    monkeypatch.setattr(module.json, "loads", fail_parse)
    result = geocoder.reverse_geocode(gps)
    assert result.status == "FAILED" and result.failure == "INVALID_JSON"
    assert result.address is None and result.road_address is None
    assert len(http.instances) == 1 and http.instances[0].closed
    text = str(result) + repr(result) + repr(geocoder) + caplog.text
    for secret in (KEY, str(gps.value.lat), str(gps.value.lon), ROAD, LOT, "sensitive-parser-error"):
        assert secret not in text
    assert not caplog.records


@pytest.mark.parametrize("error_type", [MemoryError, KeyboardInterrupt])
def test_json_parser_other_exceptions_are_not_suppressed(http, monkeypatch, error_type):
    def fail_parse(body):
        raise error_type("synthetic-parser-error")

    monkeypatch.setattr(module.json, "loads", fail_parse)
    with pytest.raises(error_type, match="synthetic-parser-error"):
        adapter().reverse_geocode(observation())
    assert http.instances[0].closed


@pytest.mark.parametrize("body,code", [
    (b"not-json", "INVALID_JSON"), (b"\xff", "INVALID_JSON"),
    (b"null", "INVALID_SCHEMA"), (b"{}", "INVALID_SCHEMA"),
    (b'{"meta":{"total_count":0},"documents":[]}', "EMPTY_RESULT"),
    (b'{"meta":{"total_count":1},"documents":[]}', "INVALID_SCHEMA"),
    (b'{"meta":{"total_count":1},"documents":[{}]}', "INVALID_SCHEMA"),
    (b'{"meta":{"total_count":1},"documents":[{"address":{"address_name":42}}]}', "INVALID_SCHEMA"),
    (b'{"meta":{"total_count":true},"documents":[{}]}', "INVALID_SCHEMA"),
    (b'{"meta":{"total_count":1},"documents":[{"address":{"address_name":""}}]}', "INVALID_SCHEMA"),
])
def test_response_failures(http, body, code):
    http.body = body
    assert adapter().reverse_geocode(observation()).failure == code
    assert http.instances[0].closed


@pytest.mark.parametrize("status", ["UNKNOWN", "ERROR", "NEEDS_REVIEW", "NOT_APPLICABLE"])
def test_non_ok_never_calls_provider(http, status):
    gps = observation().model_copy(update={"status": status, "value": None})
    result = adapter().reverse_geocode(gps)
    assert result.status == "SKIPPED" and result.failure == "GPS_NOT_OK"
    assert not http.instances


def test_tentative_coordinates_are_not_sent(http):
    gps = observation().model_copy(update={"status": "NEEDS_REVIEW"})
    assert adapter().reverse_geocode(gps).status == "SKIPPED"
    assert not http.instances


def test_road_only_is_preserved_without_selecting_display_address(http):
    data = payload()
    data["documents"][0]["address"] = None
    http.body = json.dumps(data).encode()
    result = adapter().reverse_geocode(observation())
    assert result.status == "OK" and result.address is None
    assert result.road_address.address_name == ROAD


def test_does_not_read_environment(http, monkeypatch):
    import os
    gps = observation()
    def forbidden(*args, **kwargs):
        raise AssertionError("environment read")
    monkeypatch.setattr(os, "getenv", forbidden)
    assert adapter().reverse_geocode(gps).status == "OK"


@pytest.mark.parametrize("field,value", [("lat", 91.), ("lon", -181.), ("lat", float("nan")), ("lon", float("inf"))])
def test_tampered_coordinates_rejected_before_http(http, field, value):
    gps = observation()
    gps = gps.model_copy(update={"value": gps.value.model_copy(update={field: value})})
    assert adapter().reverse_geocode(gps).failure == "INVALID_INPUT"
    assert not http.instances


def test_sensitive_data_not_in_logs_or_reprs(http, caplog):
    caplog.set_level(logging.DEBUG)
    geocoder = adapter()
    gps = observation()
    success = geocoder.reverse_geocode(gps)
    http.error = TimeoutError(f"{KEY} {gps.value.lon} {ROAD}")
    failure = geocoder.reverse_geocode(gps)
    text = caplog.text + repr(geocoder) + repr(success) + repr(failure)
    for secret in (KEY, str(gps.value.lat), str(gps.value.lon), ROAD, LOT):
        assert secret not in text


@pytest.mark.parametrize("key,timeout", [("", 1.), ("bad\nkey", 1.), (KEY, 0.), (KEY, float("inf"))])
def test_invalid_config_has_safe_error(http, key, timeout):
    with pytest.raises(ValueError, match="Invalid geocoder configuration"):
        module.KakaoReverseGeocoder(api_key=key, timeout_sec=timeout)
    assert not http.instances
