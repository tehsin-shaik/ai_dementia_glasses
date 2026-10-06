# Deterministic evaluation scenarios

`scenarios.json` lists questions asked against the seeded demo data (Alex is
profile `1`, Jordan is profile `2`). `apps/api/tests/test_evaluation.py`
runs every scenario through `POST /api/query` and checks it without an LLM:

- `expected_intent` must match exactly.
- Every id in `expected_sources` must appear in the answer's `source_ids`.
- Every phrase in `must_include` must appear in the answer (case-insensitive).
- No phrase in `must_not_claim` may appear in the answer (case-insensitive).
- An `unknown` answer must have no sources and no evidence.

Run with the backend test suite:

```bash
cd apps/api
.venv/bin/python -m pytest -q tests/test_evaluation.py
```

The seeded moments are stored at 10:00–10:32 AM today, so scenarios assume no
newer memories exist.
