#!/usr/bin/env python3
"""Smoke test for OpenCode Go's OpenAI-compatible chat endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_ENDPOINT = "https://opencode.ai/zen/go/v1/chat/completions"
DEFAULT_MODEL = "kimi-k2.6"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send one test request to OpenCode Go using an API key."
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENCODE_GO_MODEL", DEFAULT_MODEL),
        help="OpenCode Go model id, without the opencode-go/ prefix.",
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("OPENCODE_GO_ENDPOINT", DEFAULT_ENDPOINT),
        help="OpenCode Go chat completions endpoint.",
    )
    parser.add_argument(
        "--prompt",
        default="Return exactly: opencode-go-ok",
        help="User prompt to send.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=80,
        help="Maximum output tokens.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("OPENCODE_GO_API_KEY") or _load_auth_key()
    if not api_key:
        print(
            "Missing OpenCode Go API key. Run:\n"
            "  export OPENCODE_GO_API_KEY='your_key_here'\n"
            "or connect it in OpenCode with /connect.",
            file=sys.stderr,
        )
        return 2

    payload = {
        "model": args.model,
        "messages": [
            {
                "role": "system",
                "content": "You are a concise API smoke-test assistant.",
            },
            {
                "role": "user",
                "content": args.prompt,
            },
        ],
        "temperature": 0,
        "max_tokens": args.max_tokens,
    }

    request = urllib.request.Request(
        args.endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "storage-query-tagger/0.1",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code} from OpenCode Go", file=sys.stderr)
        print(error_body, file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    data = json.loads(response_body)
    message = data["choices"][0]["message"]["content"]
    print(message)
    return 0


def _load_auth_key() -> str:
    auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    if not auth_path.exists():
        return ""
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    provider = data.get("opencode-go")
    if not isinstance(provider, dict):
        return ""
    return str(provider.get("key") or "")


if __name__ == "__main__":
    raise SystemExit(main())
