from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .publishing import (
    AmbiguousDelivery, CommentPage, RemoteComment, TransportResponse,
)


class SourceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    labels: tuple[str, ...]
    updated_at: str
    state: str = "open"
    comments: int = 0
    state_reason: str | None = None

    @property
    def snapshot_hash(self) -> str:
        value = {
            "number": self.number, "title": self.title, "body": self.body,
            "labels": sorted(self.labels), "updated_at": self.updated_at,
            "state": self.state, "comments": self.comments,
            "state_reason": self.state_reason,
        }
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()


class IssueSource(Protocol):
    def fetch(self, etag: str | None = None) -> tuple[list[Issue], str | None, bool]: ...


class GitHubIssueSource:
    """Read-only GitHub Issues adapter. It intentionally has no mutation method."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fetch(self, etag: str | None = None) -> tuple[list[Issue], str | None, bool]:
        repository = self.config["repository"]
        query_values = {"state": "all", "sort": "updated", "direction": "desc", "per_page": 100}
        if not self.config.get("track_manual_edits", True):
            query_values.update({"state": "open", "labels": self.config["task_label"]})
        query = urlencode(query_values)
        url = f"{self.config['api_base'].rstrip('/')}/repos/{repository}/issues?{query}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "cef-dy-local-orchestrator/1"}
        token = os.environ.get(self.config.get("token_env", "GITHUB_TOKEN"), "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if etag:
            headers["If-None-Match"] = etag
        data: list[Any] = []
        response_etag = etag
        for page in range(1, int(self.config.get("max_pages", 10)) + 1):
            page_url = url + f"&page={page}"
            page_headers = dict(headers)
            if page > 1:
                page_headers.pop("If-None-Match", None)
            request = Request(page_url, headers=page_headers, method="GET")
            try:
                with urlopen(request, timeout=int(self.config["timeout_seconds"])) as response:
                    page_data = json.load(response)
                    if page == 1:
                        response_etag = response.headers.get("ETag")
            except HTTPError as exc:
                if exc.code == 304 and page == 1:
                    return [], etag, True
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                raise SourceUnavailable(f"GitHub HTTP {exc.code}; retry_after={retry_after or 'unspecified'}") from exc
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise SourceUnavailable(f"GitHub unavailable: {exc}") from exc
            if not isinstance(page_data, list):
                raise SourceUnavailable("GitHub returned a non-list response")
            data.extend(page_data)
            if len(page_data) < 100:
                break
        else:
            raise SourceUnavailable("GitHub pagination exceeds configured max_pages")
        issues = []
        for item in data:
            if "pull_request" in item:
                continue
            labels = tuple(sorted(label.get("name", "") for label in item.get("labels", []) if isinstance(label, dict)))
            issues.append(Issue(
                int(item["number"]), str(item.get("title", "")),
                str(item.get("body") or ""), labels,
                str(item.get("updated_at", "")),
                str(item.get("state", "open")), int(item.get("comments", 0)),
                str(item["state_reason"]) if item.get("state_reason") is not None else None,
            ))
        return issues, response_etag, False


class GitHubCommentTransport:
    """Exact-marker GitHub Issue comment transport for the durable outbox."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "cef-dy-local-orchestrator/2",
        }
        token = os.environ.get(self.config.get("token_env", "GITHUB_TOKEN"), "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _issue_number(self, target: str) -> int:
        if not target.startswith("issue:") or not target[6:].isdigit() or int(target[6:]) < 1:
            raise ValueError("invalid GitHub publication target")
        return int(target[6:])

    def send_comment(self, target: str, body: str) -> TransportResponse:
        if "Authorization" not in self._headers():
            return TransportResponse(401)
        number = self._issue_number(target)
        url = f"{self.config['api_base'].rstrip('/')}/repos/{self.config['repository']}/issues/{number}/comments"
        request = Request(url, data=json.dumps({"body": body}).encode(), headers=self._headers(), method="POST")
        try:
            with urlopen(request, timeout=int(self.config["timeout_seconds"])) as response:
                payload = json.load(response)
                return TransportResponse(int(response.status), str(payload.get("id")) if payload.get("id") is not None else None)
        except HTTPError as exc:
            retry = exc.headers.get("Retry-After") if exc.headers else None
            return TransportResponse(exc.code, retry_after_seconds=int(retry) if retry and retry.isdigit() else None)
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise AmbiguousDelivery(str(exc)) from exc

    def list_comments(self, target: str) -> CommentPage:
        number = self._issue_number(target)
        base = f"{self.config['api_base'].rstrip('/')}/repos/{self.config['repository']}/issues/{number}/comments?per_page=100"
        comments: list[RemoteComment] = []
        for page in range(1, int(self.config.get("max_pages", 10)) + 1):
            request = Request(base + f"&page={page}", headers=self._headers(), method="GET")
            try:
                with urlopen(request, timeout=int(self.config["timeout_seconds"])) as response:
                    payload = json.load(response)
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise AmbiguousDelivery(str(exc)) from exc
            if not isinstance(payload, list):
                raise AmbiguousDelivery("GitHub comments response is not a list")
            for item in payload:
                user = item.get("user") or {}
                comments.append(RemoteComment(str(item.get("body") or ""), user.get("login"), str(item.get("id"))))
            if len(payload) < 100:
                return CommentPage(tuple(comments), True)
        return CommentPage(tuple(comments), False)


def backoff_seconds(failures: int, initial: int, maximum: int) -> int:
    return min(maximum, initial * (2 ** max(0, failures - 1)))
