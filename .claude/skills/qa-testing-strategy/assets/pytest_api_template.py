"""
pytest API test template — parametrized from the QA contract cases.

This is a starting point the automation-engineer adapts to the project. It reads a
cases file produced by testcase_generator.py and turns the field-rule cases into
parametrized API tests, so adding a field to the data dictionary automatically
extends coverage.

Replace `api_client` and the endpoint paths with the project's real client and
routes. Default stack: pytest + httpx (or requests / Django test client).

Run:
    pytest test_api_contract.py -v
"""

import json
import os
import pytest


CASES_FILE = os.environ.get("QA_CASES_FILE", "cases.json")


def load_cases():
    if not os.path.exists(CASES_FILE):
        return []
    with open(CASES_FILE, encoding="utf-8") as fh:
        return json.load(fh)


ALL_CASES = load_cases()


def cases_by_technique(prefix):
    return [c for c in ALL_CASES if c["technique"].startswith(prefix)]


# ---- Replace with the project's real API client fixture ---------------------
@pytest.fixture
def api_client():
    """Return an object exposing .post(path, json=...) and .get(path).

    Example with httpx:
        import httpx
        return httpx.Client(base_url=os.environ["API_BASE_URL"])
    """
    pytest.skip("Wire up api_client for the project (httpx / requests / Django test client).")


def _endpoint(table):
    # Adapt to the project's routing convention.
    return f"/api/{table}s"


def _valid_payload(table):
    """Build a minimal valid create payload for the table.

    The automation-engineer fills this from the contract's create fields with
    valid sample values. Kept as a stub here.
    """
    return {}


# ---- required: missing a required field must fail ---------------------------
@pytest.mark.parametrize(
    "case",
    cases_by_technique("negative/required"),
    ids=lambda c: c["id"],
)
def test_required_field_missing_is_rejected(api_client, case):
    payload = _valid_payload(case["table"])
    payload.pop(case["attribute"], None)
    resp = api_client.post(_endpoint(case["table"]), json=payload)
    assert resp.status_code in (400, 422), (
        f"{case['id']}: expected validation error, got {resp.status_code}"
    )


# ---- unique: a duplicate value must be rejected -----------------------------
@pytest.mark.parametrize(
    "case",
    cases_by_technique("negative/unique"),
    ids=lambda c: c["id"],
)
def test_unique_field_duplicate_is_rejected(api_client, case):
    payload = _valid_payload(case["table"])
    first = api_client.post(_endpoint(case["table"]), json=payload)
    assert first.status_code in (200, 201), f"setup create failed for {case['id']}"
    second = api_client.post(_endpoint(case["table"]), json=payload)
    assert second.status_code in (400, 409, 422), (
        f"{case['id']}: expected duplicate rejection, got {second.status_code}"
    )


# ---- choice: invalid enum value must be rejected ----------------------------
@pytest.mark.parametrize(
    "case",
    cases_by_technique("negative/equivalence"),
    ids=lambda c: c["id"],
)
def test_invalid_choice_is_rejected(api_client, case):
    payload = _valid_payload(case["table"])
    payload[case["attribute"]] = "__definitely_not_a_valid_choice__"
    resp = api_client.post(_endpoint(case["table"]), json=payload)
    assert resp.status_code in (400, 422), (
        f"{case['id']}: expected invalid-choice rejection, got {resp.status_code}"
    )


# ---- type: invalid type/format must be rejected -----------------------------
@pytest.mark.parametrize(
    "case",
    cases_by_technique("negative/type"),
    ids=lambda c: c["id"],
)
def test_invalid_type_is_rejected(api_client, case):
    payload = _valid_payload(case["table"])
    payload[case["attribute"]] = {"unexpected": "object"}  # clearly wrong type
    resp = api_client.post(_endpoint(case["table"]), json=payload)
    assert resp.status_code in (400, 422), (
        f"{case['id']}: expected type/format rejection, got {resp.status_code}"
    )


# ---- exposure: list endpoint returns the get_index fields -------------------
@pytest.mark.parametrize(
    "case",
    cases_by_technique("contract/exposure"),
    ids=lambda c: c["id"],
)
def test_list_exposes_field(api_client, case):
    resp = api_client.get(_endpoint(case["table"]))
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("results", data) if isinstance(data, dict) else data
    if items:
        assert case["attribute"] in items[0], (
            f"{case['id']}: list item missing '{case['attribute']}'"
        )
