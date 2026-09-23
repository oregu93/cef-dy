from __future__ import annotations

import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class OllamaDisabled(RuntimeError):
    pass


class OllamaHelper:
    """Optional local semantic helper; its output is never executable authority."""

    def __init__(self, config):
        self.config = config
        parsed = urlparse(config["base_url"])
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise OllamaDisabled("Ollama endpoint must be loopback")

    def generate(self, prompt: str) -> str:
        if not self.config.get("enabled") or not self.config.get("model"):
            raise OllamaDisabled("Ollama helper is disabled or model is unset")
        payload = json.dumps({"model": self.config["model"], "prompt": prompt, "stream": False}).encode()
        request = Request(self.config["base_url"].rstrip("/") + "/api/generate", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=int(self.config["timeout_seconds"])) as response:
            return str(json.load(response)["response"])
