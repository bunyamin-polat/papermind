"""The only file that names a model provider.

Two paths, chosen by `LLM_PROVIDER`: Ollama (default, local, free) and OpenAI.
Everything above this module works the same either way — swapping is an env var,
never a code change. Ollama is the default because a stranger should be able to
clone this repo and run it without an account, and because step 5 is hours of
prompt iteration that should not be metered.
"""

import json
import urllib.error
import urllib.request

from core.config import settings


class LLMError(RuntimeError):
    pass


def _ollama(
    prompt: str,
    system: str | None,
    model: str | None = None,
    schema: dict | None = None,
) -> str:
    payload = {
        "model": model or settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": settings.llm_temperature,
            "num_predict": settings.llm_max_tokens,
        },
    }
    if system:
        payload["system"] = system
    if schema:
        # Constrained decoding: Ollama restricts sampling to tokens that can still
        # complete a document matching the schema. Asking for JSON in the prompt is
        # a request the model can ignore — and it does, with preambles and code
        # fences that only fail once something tries to parse them.
        payload["format"] = schema

    request = urllib.request.Request(
        f"{settings.ollama_host}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.llm_timeout_s) as response:
            return json.loads(response.read())["response"]
    except urllib.error.URLError as exc:
        raise LLMError(
            f"cannot reach Ollama at {settings.ollama_host} ({exc}). "
            f"Start it with `ollama serve`, then "
            f"`ollama pull {model or settings.ollama_model}`."
        ) from exc


def _openai(prompt: str, system: str | None, model: str | None = None) -> str:
    if not settings.openai_api_key:
        raise LLMError("LLM_PROVIDER=openai but OPENAI_API_KEY is empty")

    from openai import OpenAI

    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    response = OpenAI(api_key=settings.openai_api_key).chat.completions.create(
        model=model or settings.openai_model,
        messages=messages,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    return response.choices[0].message.content or ""


def complete(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    schema: dict | None = None,
) -> str:
    """`model` overrides the configured one for this call only.

    It exists so a task can deliberately use a *different* model from the one
    being measured. Generating evaluation questions with the same model that
    answers them produces questions shaped by its blind spots — easy for exactly
    the system under test, and flattering in a way nothing in the output reveals.
    """
    if settings.llm_provider == "ollama":
        return _ollama(prompt, system, model, schema)
    if settings.llm_provider == "openai":
        return _openai(prompt, system, model)
    raise LLMError(f"unknown LLM_PROVIDER: {settings.llm_provider!r}")
