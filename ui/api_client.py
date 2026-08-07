"""The only thing the UI is allowed to know about the backend: its URL.

This module exists to keep a boundary that is easy to erase by accident. Importing
`retrieval.answer` from the UI would work — same repo, same interpreter — and would
quietly make the API decorative: untested by anything a user touches, and at step 9
a container with two entrypoints pretending to be one. The UI is an HTTP client,
including when both processes are on the same machine.
"""

import os
from typing import Any

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")
TIMEOUT_S = 180  # generous: a cold local model can take a while to answer


class ApiError(RuntimeError):
    """Something the user needs told about, phrased for a user."""


def _request(method: str, path: str, **kwargs: Any) -> dict:
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=TIMEOUT_S, **kwargs)
    except requests.exceptions.ConnectionError as exc:
        raise ApiError(
            f"Cannot reach the API at {API_URL}.\n\n"
            "Start it with `uv run uvicorn app.main:app`."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise ApiError(f"The API did not respond within {TIMEOUT_S}s.") from exc

    if response.status_code == 503:
        # The API distinguishes "dependency down" from "misconfigured"; passing that
        # distinction through is the point of having made it.
        raise ApiError(f"A service the API depends on is unavailable.\n\n{_detail(response)}")
    if response.status_code >= 400:
        raise ApiError(_detail(response))

    return response.json()


def _detail(response: requests.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text


def ask(question: str, k: int = 5) -> dict:
    return _request("POST", "/ask", json={"question": question, "k": k})


def health() -> dict:
    return _request("GET", "/health")
