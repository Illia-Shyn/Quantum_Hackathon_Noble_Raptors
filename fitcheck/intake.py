"""Plain-language front door. A language model only turns a sentence into a structured problem
type and size. It never produces any number in the report; Qiskit does all of that."""
from __future__ import annotations

import json
import os
import re

from .core import SHAPES, SIZABLE
from .device import _secret
from .problems import assignment_problem, maxcut_problem, random_graph, synthetic_costs

DEFAULT_MODEL = "gemini-3.5-flash-lite"
TYPES = list(SHAPES)

_PROMPT = """You classify a task for a quantum-computing fit check. Reply with JSON only:
{{"problem_type": one of {types},
  "size": integer (number of items: graph nodes for maxcut, patients/workers/jobs for assignment; 0 if unknown),
  "understood": one plain sentence restating the task as that problem type}}

Types:
- maxcut: splitting a network or graph into two groups, clustering links, partitioning.
- assignment: matching n things to n slots one-to-one at lowest cost (patients to beds, workers to shifts, drivers to routes).
- qubo: other yes/no optimisation (portfolio selection, knapsack, scheduling with conflicts).
- molecule_energy: chemistry or materials simulation, molecule energies, drug binding.
- factoring: breaking RSA, factoring large numbers.
- search: finding an item in unsorted data, database lookup.
- other: anything else (web apps, spreadsheets, training neural networks, arithmetic).

Task: {text}"""

_KEYWORDS = [
    ("molecule_energy", r"molecul|chemi|drug|protein|material|energy level|binding"),
    ("factoring", r"factor|rsa|encrypt|decrypt|prime"),
    ("assignment", r"assign|match|bed|shift|roster|allocat|patient|nurse|driver"),
    ("maxcut", r"graph|network|cut|partition|cluster|split|communit"),
    ("qubo", r"portfolio|knapsack|schedul|optimi[sz]|route|routing|select"),
    ("search", r"search|find|look ?up|database"),
]


def _keyword_parse(text: str) -> dict:
    low = text.lower()
    kind = next((k for k, pattern in _KEYWORDS if re.search(pattern, low)), "other")
    numbers = [int(n) for n in re.findall(r"\b\d{1,4}\b", low)]
    return {"problem_type": kind, "size": numbers[0] if numbers else 0,
            "understood": f"Read as a '{kind.replace('_', ' ')}' task by keyword matching.",
            "source": "keywords"}


def _clean(spec: dict, source: str) -> dict:
    kind = spec.get("problem_type")
    if kind not in SHAPES:
        kind = "other"
    try:
        size = max(0, int(spec.get("size") or 0))
    except (TypeError, ValueError):
        size = 0
    return {"problem_type": kind, "size": size,
            "understood": str(spec.get("understood") or "").strip(), "source": source}


def parse_request(text: str, api_key: str | None = None, model: str | None = None) -> dict:
    """Sentence in, {"problem_type", "size", "understood", "source"} out.
    Uses Gemini when a key is available (GEMINI_API_KEY or GOOGLE_API_KEY, env var or Colab
    Secret); otherwise, or if the call fails, falls back to keyword matching."""
    api_key = api_key or _secret("GEMINI_API_KEY") or _secret("GOOGLE_API_KEY")
    if not api_key:
        return _keyword_parse(text)
    model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model, contents=_PROMPT.format(types=TYPES, text=text),
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        return _clean(json.loads(raw), f"gemini:{model}")
    except Exception as exc:                       # no network, bad key, retired model...
        spec = _keyword_parse(text)
        spec["source"] = f"keywords (Gemini call failed: {type(exc).__name__})"
        return spec


def spec_to_problem(spec: dict, seed: int = 7):
    """Build a concrete problem from the parsed request, or None if the type cannot be sized.
    Graphs and cost tables are generated (synthetic), sized to match the request."""
    kind, size = spec["problem_type"], spec.get("size") or 0
    if kind not in SIZABLE:
        return None
    if kind == "assignment":
        return assignment_problem(synthetic_costs(max(2, size or 3), seed))
    return maxcut_problem(random_graph(max(2, size or 10), 3, seed))   # maxcut, and qubo as a stand-in
