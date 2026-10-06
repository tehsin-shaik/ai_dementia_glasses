"""Run the deterministic scenarios in tests/evaluation/scenarios.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .test_api import client, seed, user_headers  # noqa: F401 - client is a pytest fixture


SCENARIOS_PATH = Path(__file__).resolve().parents[3] / "tests" / "evaluation" / "scenarios.json"
SCENARIOS = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
REQUIRED_FIELDS = {
    "name",
    "profile",
    "language",
    "question",
    "expected_intent",
    "expected_sources",
    "must_include",
    "must_not_claim",
}


def test_scenarios_are_well_formed() -> None:
    names = [scenario["name"] for scenario in SCENARIOS]
    assert len(names) == len(set(names))
    for scenario in SCENARIOS:
        assert REQUIRED_FIELDS <= scenario.keys(), scenario["name"]
        if scenario["expected_intent"] == "unknown":
            assert scenario["expected_sources"] == [], scenario["name"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[scenario["name"] for scenario in SCENARIOS])
def test_scenario(client: TestClient, scenario: dict) -> None:
    seed(client)
    response = client.post(
        "/api/query",
        json={"question": scenario["question"], "language": scenario["language"]},
        headers=user_headers(scenario["profile"]),
    )
    assert response.status_code == 200
    body = response.json()
    answer = body["answer"].casefold()

    assert body["intent"] == scenario["expected_intent"]
    for source_id in scenario["expected_sources"]:
        assert source_id in body["source_ids"], source_id
    for phrase in scenario["must_include"]:
        assert phrase.casefold() in answer, phrase
    for phrase in scenario["must_not_claim"]:
        assert phrase.casefold() not in answer, phrase
    if body["intent"] == "unknown":
        assert body["source_ids"] == []
        assert body["evidence"] == []
