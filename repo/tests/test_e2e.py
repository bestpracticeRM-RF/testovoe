"""End-to-end tests against the RUNNING stand (skipped if stand is down).

Business contract: products list, checkout happy path, business rejections.
"""
import json
import os
import urllib.error
import urllib.request

import pytest

BASE = os.environ.get("E2E_URL", "http://127.0.0.1:8080")


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            raw = resp.read()
            return resp.status, _maybe_json(raw)
    except urllib.error.HTTPError as e:
        return e.code, _maybe_json(e.read())


def _maybe_json(raw: bytes):
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return raw.decode(errors="replace")  # /metrics is plain text


@pytest.fixture(scope="module", autouse=True)
def stand_up():
    try:
        code, _ = _req("GET", "/products")
        assert code == 200
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"stand not reachable at {BASE}: {e}")


def test_products_catalog():
    code, body = _req("GET", "/products")
    assert code == 200 and isinstance(body, list) and len(body) == 9
    assert {"sku", "name", "price", "stock"} <= set(body[0])


def test_checkout_happy_path():
    code, body = _req("POST", "/checkout", {"sku": "SKU-9538", "qty": 1})
    assert code == 201 and "order_id" in body and body["total"] == 1950


def test_checkout_invalid_coupon():
    code, body = _req("POST", "/checkout", {"sku": "SKU-9538", "qty": 1, "coupon": "JULY20"})
    assert code == 400 and "invalid coupon" in body["error"]


def test_checkout_unknown_sku():
    code, _ = _req("POST", "/checkout", {"sku": "SKU-000000", "qty": 1})
    assert code == 404


def test_checkout_out_of_stock():
    code, _ = _req("POST", "/checkout", {"sku": "SKU-9239", "qty": 1})  # термокружка, stock=0
    assert code == 409


def test_metrics_exposed():
    code, body = _req("GET", "/metrics")
    assert code == 200
    assert "shop_pool_idle" in body
