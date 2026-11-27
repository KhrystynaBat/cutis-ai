from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class ExplainError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class ImagePart:
    mime_type: str
    data: bytes


class ExplainClient(Protocol):
    model: str

    def generate_json(self, system: str, parts: list[str | ImagePart], schema: dict[str, Any]) -> dict[str, Any]: ...


class GeminiClient:
    """generateContent over REST; the key goes only into the request header."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 60,
        transport: httpx.BaseTransport | None = None,
        fallback_models: tuple[str, ...] = (),
    ):
        self._key = api_key
        self.model = model  # after a call: the model that answered
        self._models = (model, *(m for m in fallback_models if m and m != model))
        self._timeout = timeout
        self._transport = transport

    def generate_json(self, system: str, parts: list[str | ImagePart], schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [_part(p) for p in parts]}],
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema},
        }
        for i, model in enumerate(self._models):
            try:
                data = self._call(model, body)
            except ExplainError as e:
                # overloaded model: try the next one
                if e.code != "EXPLAIN_UNAVAILABLE" or i == len(self._models) - 1:
                    raise
                continue
            self.model = model
            return data
        raise ExplainError("EXPLAIN_UNAVAILABLE", "no model")

    def _call(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as http:
                r = http.post(
                    API_URL.format(model=model),
                    headers={"x-goog-api-key": self._key, "Content-Type": "application/json"},
                    json=body,
                )
        except httpx.TimeoutException as e:
            raise ExplainError("EXPLAIN_TIMEOUT", e.__class__.__name__) from None
        except httpx.HTTPError as e:
            raise ExplainError("EXPLAIN_UNAVAILABLE", e.__class__.__name__) from None
        if r.status_code == 429:
            raise ExplainError("EXPLAIN_RATE_LIMIT", "429")
        if r.status_code in (401, 403):
            raise ExplainError("EXPLAIN_AUTH", str(r.status_code))
        if r.status_code >= 500:
            raise ExplainError("EXPLAIN_UNAVAILABLE", str(r.status_code))
        if r.status_code != 200:
            raise ExplainError("EXPLAIN_REJECTED", str(r.status_code))
        try:
            parts_out = r.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts_out if not p.get("thought"))
            data = json.loads(text)
        except (KeyError, IndexError, TypeError, ValueError):
            raise ExplainError("EXPLAIN_BAD_RESPONSE", "unparseable response") from None
        if not isinstance(data, dict):
            raise ExplainError("EXPLAIN_BAD_RESPONSE", "not an object")
        return data


def _part(p: str | ImagePart) -> dict[str, Any]:
    if isinstance(p, str):
        return {"text": p}
    return {"inlineData": {"mimeType": p.mime_type, "data": base64.b64encode(p.data).decode("ascii")}}
