from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REMOTE_BASE_URL = "https://mcp.sorftime.com"
OPENCODE_CONFIG_PATH = Path.home() / ".config" / "opencode" / "opencode.json"


@dataclass(slots=True)
class SorftimeConfig:
    endpoint_url: str
    timeout_seconds: int = 30

    @property
    def redacted_endpoint_url(self) -> str:
        if "?key=" not in self.endpoint_url:
            return self.endpoint_url
        prefix, _ = self.endpoint_url.split("?key=", 1)
        return f"{prefix}?key=***"


@dataclass(slots=True)
class MCPResponse:
    request_payload: dict[str, Any]
    raw_text: str
    messages: list[dict[str, Any]]
    http_status: int
    headers: dict[str, str]
    received_at: str

    @property
    def first_result(self) -> Any:
        for message in self.messages:
            if "result" in message:
                return message["result"]
        return None


class SorftimeMCPClient:
    def __init__(self, config: SorftimeConfig):
        self.config = config
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _post(self, payload: dict[str, Any]) -> MCPResponse:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.config.endpoint_url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw_text = response.read().decode("utf-8", errors="replace")
                return MCPResponse(
                    request_payload=payload,
                    raw_text=raw_text,
                    messages=_parse_sse_messages(raw_text),
                    http_status=response.status,
                    headers=dict(response.headers),
                    received_at=datetime.now(timezone.utc).isoformat(),
                )
        except urllib.error.HTTPError as exc:
            raw_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Sorftime MCP request failed, HTTP {exc.code}: {raw_text}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Sorftime MCP network error: {exc}") from exc

    def initialize(self) -> MCPResponse:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "storage-taxonomy-sorftime-client",
                    "version": "1.0.0",
                },
            },
        }
        return self._post(payload)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPResponse:
        self.initialize()
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }
        return self._post(payload)


def load_sorftime_config(timeout_seconds: int = 30) -> SorftimeConfig:
    endpoint_url = _build_url_from_env() or _load_url_from_opencode()
    if not endpoint_url:
        raise RuntimeError(
            "Sorftime MCP config not found. Set SORFTIME_MCP_URL or SORFTIME_API_KEY, "
            "or add mcp.Sorftime.url to ~/.config/opencode/opencode.json."
        )
    return SorftimeConfig(endpoint_url=endpoint_url, timeout_seconds=timeout_seconds)


def _build_url_from_env() -> str | None:
    direct_url = os.getenv("SORFTIME_MCP_URL", "").strip()
    if direct_url:
        return direct_url

    api_key = os.getenv("SORFTIME_API_KEY", "").strip()
    if api_key:
        return f"{DEFAULT_REMOTE_BASE_URL}?key={api_key}"
    return None


def _load_url_from_opencode() -> str | None:
    if not OPENCODE_CONFIG_PATH.exists():
        return None
    data = json.loads(OPENCODE_CONFIG_PATH.read_text(encoding="utf-8"))
    return data.get("mcp", {}).get("Sorftime", {}).get("url")


def _parse_sse_messages(raw_text: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    data_lines: list[str] = []

    for line in raw_text.splitlines():
        if line.startswith("data: "):
            data_lines.append(line[6:])
        elif not line.strip() and data_lines:
            messages.append(_safe_json_loads("\n".join(data_lines)))
            data_lines = []

    if data_lines:
        messages.append(_safe_json_loads("\n".join(data_lines)))

    return messages


def _safe_json_loads(value: str) -> dict[str, Any]:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}
