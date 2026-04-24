from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_OPENCODE_GO_ENDPOINT = "https://opencode.ai/zen/go/v1/chat/completions"
DEFAULT_OPENCODE_GO_MODEL = "kimi-k2.6"


class OpenCodeGoError(RuntimeError):
    pass


def normalize_opencode_go_model(model: str) -> str:
    if model.startswith("opencode-go/"):
        return model.split("/", 1)[1]
    return model


def load_opencode_go_api_key() -> str:
    env_value = os.environ.get("OPENCODE_GO_API_KEY")
    if env_value:
        return env_value

    auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    if not auth_path.exists():
        return ""

    try:
        auth_data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    provider = auth_data.get("opencode-go")
    if not isinstance(provider, dict):
        return ""
    key = provider.get("key")
    return str(key) if key else ""


class OpenCodeGoChatClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_OPENCODE_GO_MODEL,
        endpoint: str = DEFAULT_OPENCODE_GO_ENDPOINT,
        timeout_seconds: int = 90,
    ):
        if not api_key:
            raise OpenCodeGoError(
                "Missing OpenCode Go API key. Set OPENCODE_GO_API_KEY or run /connect in OpenCode."
            )
        self.api_key = api_key
        self.model = normalize_opencode_go_model(model)
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload_text = json.dumps(payload, ensure_ascii=False)
        curl_command = [
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            str(self.timeout_seconds),
            "-H",
            f"Authorization: Bearer {self.api_key}",
            "-H",
            "Content-Type: application/json",
            "-H",
            "Accept: application/json",
            "-H",
            "User-Agent: storage-query-tagger/0.1",
            "-d",
            payload_text,
            self.endpoint,
        ]
        request = urllib.request.Request(
            self.endpoint,
            data=payload_text.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "storage-query-tagger/0.1",
            },
            method="POST",
        )
        try:
            completed = subprocess.run(
                curl_command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds + 5,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                response_body = completed.stdout
            else:
                raise OpenCodeGoError(
                    f"curl failed with code {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    response_body = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                raise OpenCodeGoError(f"HTTP {exc.code} from OpenCode Go: {error_body}") from exc
            except urllib.error.URLError as exc:
                raise OpenCodeGoError(f"OpenCode Go request failed: {exc}") from exc

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise OpenCodeGoError(f"OpenCode Go returned non-JSON response: {response_body[:500]}") from exc

    @staticmethod
    def message_content(response: dict[str, Any]) -> str:
        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenCodeGoError(f"Unexpected OpenCode Go response shape: {response}") from exc
        content = message.get("content")
        if content is not None and str(content).strip():
            return str(content)
        reasoning = message.get("reasoning")
        return str(reasoning or "")
