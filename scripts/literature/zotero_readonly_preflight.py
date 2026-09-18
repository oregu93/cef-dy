#!/usr/bin/env python3
"""Bounded GET-only Zotero Web API v3 preflight client.

The live ``preflight`` command is intentionally narrow.  It verifies one
explicit user or group library candidate, resolves exactly one ``CEF Dy``
collection, and proves that the collection's top-level item endpoint is
readable.  It never mutates Zotero or tracked project state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol, Sequence


API_ORIGIN = "https://api.zotero.org"
API_VERSION = 3
CANONICAL_LIBRARY_ALIAS = "project-main"
CANONICAL_COLLECTION_NAME = "CEF Dy"
COLLECTION_PAGE_SIZE = 100
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_COLLECTION_RECORDS = 1_000_000

NUMERIC_ID_RE = re.compile(r"[1-9][0-9]*")
COLLECTION_KEY_RE = re.compile(r"[A-Za-z0-9]{1,64}")

FAILURE_CODES = frozenset(
    {
        "CREDENTIAL_NOT_CONFIGURED",
        "CREDENTIAL_REJECTED",
        "READ_ACCESS_DENIED",
        "UNEXPECTED_WRITE_CAPABILITY",
        "API_VERSION_MISMATCH",
        "LIBRARY_NOT_FOUND",
        "LIBRARY_IDENTITY_AMBIGUOUS",
        "COLLECTION_NOT_FOUND",
        "COLLECTION_AMBIGUOUS",
        "NETWORK_ERROR",
        "RATE_LIMITED",
        "RESPONSE_INVALID",
        "NEEDS_REVIEW",
        "REDIRECT_FORBIDDEN",
        "ENDPOINT_FORBIDDEN",
    }
)

SAFE_FAILURE_MESSAGES = {
    "CREDENTIAL_NOT_CONFIGURED": "runtime credential is not configured",
    "CREDENTIAL_REJECTED": "runtime credential was rejected",
    "READ_ACCESS_DENIED": "required read access is unavailable",
    "UNEXPECTED_WRITE_CAPABILITY": "credential has forbidden write capability",
    "API_VERSION_MISMATCH": "response API version is not version 3",
    "LIBRARY_NOT_FOUND": "explicit library candidate was not found",
    "LIBRARY_IDENTITY_AMBIGUOUS": "library identity could not be resolved uniquely",
    "COLLECTION_NOT_FOUND": "canonical collection was not found",
    "COLLECTION_AMBIGUOUS": "canonical collection has multiple exact matches",
    "NETWORK_ERROR": "network request failed",
    "RATE_LIMITED": "remote service rate limited the request",
    "RESPONSE_INVALID": "remote response did not satisfy the preflight contract",
    "NEEDS_REVIEW": "preflight requires review",
    "REDIRECT_FORBIDDEN": "redirect response is forbidden",
    "ENDPOINT_FORBIDDEN": "request endpoint is outside the allowlist",
}


class PreflightError(RuntimeError):
    """Failure with a bounded code and non-sensitive message."""

    def __init__(self, code: str) -> None:
        if code not in FAILURE_CODES:
            code = "NEEDS_REVIEW"
        self.code = code
        super().__init__(SAFE_FAILURE_MESSAGES[code])


def fail(code: str) -> None:
    raise PreflightError(code)


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class _Endpoint:
    """Internal path/query value; it intentionally contains no HTTP method."""

    path: str
    query: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class LibraryCandidate:
    library_alias: str
    library_type: str
    library_id: str
    principal_relation_verified: bool


@dataclass(frozen=True)
class CollectionCandidate:
    collection_key: str
    exact_match_count: int


@dataclass(frozen=True)
class PreflightResult:
    schema_version: str
    status: str
    transport: str
    api_version: int
    library_alias: str
    candidate_library_type: str
    candidate_library_id: str
    read_access_verified: bool
    write_access_verified_false: bool
    principal_relation_verified: bool
    collection_exact_match_count: int
    candidate_collection_key: str
    generic_item_read_verified: bool
    http_status_class: str

    def serializable(self) -> dict[str, Any]:
        return asdict(self)


class ReadOnlyTransport(Protocol):
    """The only transport operation exposed to orchestration is GET."""

    def get(self, endpoint: _Endpoint) -> TransportResponse:
        ...


def _numeric_id(value: Any) -> str:
    if isinstance(value, bool):
        fail("LIBRARY_IDENTITY_AMBIGUOUS")
    text = str(value)
    if NUMERIC_ID_RE.fullmatch(text) is None:
        fail("LIBRARY_IDENTITY_AMBIGUOUS")
    return text


def _collection_key(value: Any) -> str:
    if not isinstance(value, str) or COLLECTION_KEY_RE.fullmatch(value) is None:
        fail("RESPONSE_INVALID")
    return value


def keys_current_endpoint() -> _Endpoint:
    return _Endpoint("/keys/current")


def user_collections_endpoint(user_id: Any, start: int) -> _Endpoint:
    user = _numeric_id(user_id)
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        fail("ENDPOINT_FORBIDDEN")
    return _Endpoint(
        f"/users/{user}/collections",
        (("format", "json"), ("limit", "100"), ("start", str(start))),
    )


def user_collection_items_endpoint(user_id: Any, collection_key: str) -> _Endpoint:
    user = _numeric_id(user_id)
    key = _collection_key(collection_key)
    return _Endpoint(
        f"/users/{user}/collections/{key}/items/top",
        (("format", "json"), ("limit", "1")),
    )


def user_groups_endpoint(user_id: Any) -> _Endpoint:
    user = _numeric_id(user_id)
    return _Endpoint(f"/users/{user}/groups", (("format", "versions"),))


def group_metadata_endpoint(group_id: Any) -> _Endpoint:
    group = _numeric_id(group_id)
    return _Endpoint(f"/groups/{group}")


def group_collections_endpoint(group_id: Any, start: int) -> _Endpoint:
    group = _numeric_id(group_id)
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        fail("ENDPOINT_FORBIDDEN")
    return _Endpoint(
        f"/groups/{group}/collections",
        (("format", "json"), ("limit", "100"), ("start", str(start))),
    )


def group_collection_items_endpoint(group_id: Any, collection_key: str) -> _Endpoint:
    group = _numeric_id(group_id)
    key = _collection_key(collection_key)
    return _Endpoint(
        f"/groups/{group}/collections/{key}/items/top",
        (("format", "json"), ("limit", "1")),
    )


def _query_mapping(endpoint: _Endpoint) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in endpoint.query:
        if key in result or not isinstance(key, str) or not isinstance(value, str):
            fail("ENDPOINT_FORBIDDEN")
        result[key] = value
    return result


def _validate_endpoint(endpoint: _Endpoint) -> None:
    if not isinstance(endpoint, _Endpoint):
        fail("ENDPOINT_FORBIDDEN")
    if not isinstance(endpoint.path, str) or not endpoint.path.startswith("/"):
        fail("ENDPOINT_FORBIDDEN")
    parsed_path = urllib.parse.urlsplit(endpoint.path)
    if parsed_path.scheme or parsed_path.netloc or parsed_path.query or parsed_path.fragment:
        fail("ENDPOINT_FORBIDDEN")

    query = _query_mapping(endpoint)
    path = endpoint.path
    numeric = r"[1-9][0-9]*"
    key = r"[A-Za-z0-9]{1,64}"

    if path == "/keys/current":
        valid = not query
    elif re.fullmatch(rf"/users/{numeric}/groups", path):
        valid = query == {"format": "versions"}
    elif re.fullmatch(rf"/groups/{numeric}", path):
        valid = not query
    elif re.fullmatch(rf"/(?:users|groups)/{numeric}/collections", path):
        valid = (
            query.get("format") == "json"
            and query.get("limit") == str(COLLECTION_PAGE_SIZE)
            and set(query) == {"format", "limit", "start"}
            and re.fullmatch(r"[0-9]+", query.get("start", "")) is not None
        )
    elif re.fullmatch(
        rf"/(?:users|groups)/{numeric}/collections/{key}/items/top", path
    ):
        valid = query == {"format": "json", "limit": "1"}
    else:
        valid = False

    if not valid:
        fail("ENDPOINT_FORBIDDEN")


def _validate_origin_url(url: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        fail("ENDPOINT_FORBIDDEN")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.zotero.org"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
    ):
        fail("ENDPOINT_FORBIDDEN")


def endpoint_url(endpoint: _Endpoint) -> str:
    _validate_endpoint(endpoint)
    url = urllib.parse.urlunsplit(
        ("https", "api.zotero.org", endpoint.path, urllib.parse.urlencode(endpoint.query), "")
    )
    _validate_origin_url(url)
    return url


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject every redirect before a credential can be forwarded."""

    @staticmethod
    def _reject(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        fail("REDIRECT_FORBIDDEN")

    redirect_request = _reject
    http_error_301 = _reject
    http_error_302 = _reject
    http_error_303 = _reject
    http_error_307 = _reject
    http_error_308 = _reject


class UrllibReadOnlyTransport:
    """Future live transport with a fixed GET request constructor."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        opener: Any | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key or "\r" in api_key or "\n" in api_key:
            fail("CREDENTIAL_NOT_CONFIGURED")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._opener = opener or urllib.request.build_opener(_RejectRedirectHandler())

    def get(self, endpoint: _Endpoint) -> TransportResponse:
        url = endpoint_url(endpoint)
        request = urllib.request.Request(
            url=url,
            headers={
                "Zotero-API-Version": str(API_VERSION),
                "Zotero-API-Key": self._api_key,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    fail("RESPONSE_INVALID")
                status = int(getattr(response, "status", response.getcode()))
                headers = {str(k): str(v) for k, v in response.headers.items()}
                return TransportResponse(status, headers, body)
        except PreflightError:
            raise
        except urllib.error.HTTPError as exc:
            if 300 <= int(exc.code) < 400:
                fail("REDIRECT_FORBIDDEN")
            headers = {str(k): str(v) for k, v in (exc.headers.items() if exc.headers else [])}
            return TransportResponse(int(exc.code), headers, b"")
        except (urllib.error.URLError, TimeoutError, OSError):
            fail("NETWORK_ERROR")


class FixtureTransport:
    """Ordered in-memory transport for synthetic tests and self-test."""

    def __init__(
        self,
        script: Sequence[tuple[_Endpoint, TransportResponse | BaseException]],
    ) -> None:
        self._script = [(endpoint_url(endpoint), result) for endpoint, result in script]
        self.calls: list[str] = []

    def get(self, endpoint: _Endpoint) -> TransportResponse:
        url = endpoint_url(endpoint)
        self.calls.append(url)
        if not self._script:
            fail("RESPONSE_INVALID")
        expected, result = self._script.pop(0)
        if expected != url:
            fail("RESPONSE_INVALID")
        if isinstance(result, BaseException):
            if isinstance(result, PreflightError):
                raise result
            if isinstance(result, (TimeoutError, OSError)):
                fail("NETWORK_ERROR")
            raise result
        return result

    @property
    def remaining(self) -> int:
        return len(self._script)


def read_api_key() -> str:
    """Read the future live credential only at live command execution time."""

    value = os.environ.get("ZOTERO_API_KEY")
    if not isinstance(value, str) or not value or "\r" in value or "\n" in value:
        fail("CREDENTIAL_NOT_CONFIGURED")
    return value


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == wanted:
            return str(value)
    return None


def _json_response(
    transport: ReadOnlyTransport,
    endpoint: _Endpoint,
    *,
    context: str,
) -> tuple[Any, TransportResponse]:
    try:
        response = transport.get(endpoint)
    except PreflightError:
        raise
    except (TimeoutError, OSError):
        fail("NETWORK_ERROR")

    response_version = _header(response.headers, "Zotero-API-Version")
    if response_version != str(API_VERSION):
        fail("API_VERSION_MISMATCH")

    if 300 <= response.status < 400:
        fail("REDIRECT_FORBIDDEN")
    if response.status == 429:
        fail("RATE_LIMITED")
    if response.status == 401:
        fail("CREDENTIAL_REJECTED")
    if response.status == 403:
        fail("CREDENTIAL_REJECTED" if context == "authentication" else "READ_ACCESS_DENIED")
    if response.status == 404:
        if context in {"collection", "item_read"}:
            fail("COLLECTION_NOT_FOUND")
        fail("LIBRARY_NOT_FOUND")
    if not 200 <= response.status < 300:
        fail("NEEDS_REVIEW")

    try:
        text = response.body.decode("utf-8")
        document = json.loads(text)
    except (UnicodeError, json.JSONDecodeError):
        fail("RESPONSE_INVALID")
    return document, response


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("RESPONSE_INVALID")
    return value


def _parse_principal(document: Any) -> tuple[str, dict[str, Any]]:
    root = _mapping(document)
    if "userID" not in root:
        fail("RESPONSE_INVALID")
    user_id = _numeric_id(root["userID"])
    access = _mapping(root.get("access"))
    return user_id, access


def _permission_values(permission: Any) -> tuple[bool, bool]:
    """Return explicit read access and effective write grant.

    Zotero read-only key records may omit the ``write`` field entirely.
    Absence therefore means that no write grant is present.  If ``write`` is
    present, it must still be an explicit boolean so malformed responses fail
    closed.
    """

    record = _mapping(permission)

    read_value = record.get("library")
    if not isinstance(read_value, bool):
        fail("RESPONSE_INVALID")

    if "write" not in record:
        write_value = False
    else:
        write_value = record["write"]
        if not isinstance(write_value, bool):
            fail("RESPONSE_INVALID")

    return read_value, write_value


def _require_read_only(permission: Any) -> None:
    read_value, write_value = _permission_values(permission)

    if write_value:
        fail("UNEXPECTED_WRITE_CAPABILITY")
    if not read_value:
        fail("READ_ACCESS_DENIED")


def _require_user_permission(access: Mapping[str, Any]) -> None:
    if "user" not in access:
        fail("READ_ACCESS_DENIED")
    _require_read_only(access["user"])


def _require_group_permission(access: Mapping[str, Any], group_id: str) -> None:
    groups = _mapping(access.get("groups"))
    applicable = [groups[key] for key in ("all", group_id) if key in groups]
    if not applicable:
        fail("READ_ACCESS_DENIED")

    parsed = [_permission_values(permission) for permission in applicable]
    if any(write for _, write in parsed):
        fail("UNEXPECTED_WRITE_CAPABILITY")

    selected = groups.get(group_id, groups.get("all"))
    _require_read_only(selected)


def _verify_group_relation(document: Any, group_id: str) -> None:
    versions = _mapping(document)
    matching = 0
    for raw_id, version in versions.items():
        if not isinstance(raw_id, str) or NUMERIC_ID_RE.fullmatch(raw_id) is None:
            fail("RESPONSE_INVALID")
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            fail("RESPONSE_INVALID")
        if int(raw_id) == int(group_id):
            matching += 1
    if matching == 0:
        fail("LIBRARY_NOT_FOUND")
    if matching > 1:
        fail("LIBRARY_IDENTITY_AMBIGUOUS")


def _verify_group_metadata(document: Any, group_id: str) -> None:
    root = _mapping(document)
    identities: list[str] = []
    for field in ("id", "groupID"):
        if field in root:
            identities.append(_numeric_id(root[field]))
    data = root.get("data")
    if data is not None:
        data_map = _mapping(data)
        for field in ("id", "groupID"):
            if field in data_map:
                identities.append(_numeric_id(data_map[field]))
    if not identities:
        fail("RESPONSE_INVALID")
    if len(set(identities)) != 1:
        fail("LIBRARY_IDENTITY_AMBIGUOUS")
    if identities[0] != group_id:
        fail("LIBRARY_NOT_FOUND")


def resolve_library(
    transport: ReadOnlyTransport,
    *,
    library_alias: str,
    library_type: str,
    library_id: str | None,
) -> LibraryCandidate:
    if library_alias != CANONICAL_LIBRARY_ALIAS or library_type not in {"user", "group"}:
        fail("LIBRARY_IDENTITY_AMBIGUOUS")
    if library_type == "user" and library_id is not None:
        fail("LIBRARY_IDENTITY_AMBIGUOUS")
    if library_type == "group" and library_id is None:
        fail("LIBRARY_IDENTITY_AMBIGUOUS")

    key_document, _ = _json_response(
        transport, keys_current_endpoint(), context="authentication"
    )
    principal_user_id, access = _parse_principal(key_document)

    if library_type == "user":
        _require_user_permission(access)
        return LibraryCandidate(
            library_alias,
            "user",
            principal_user_id,
            principal_relation_verified=True,
        )

    group_id = _numeric_id(library_id)
    _require_group_permission(access, group_id)
    relation_document, _ = _json_response(
        transport,
        user_groups_endpoint(principal_user_id),
        context="library",
    )
    _verify_group_relation(relation_document, group_id)
    metadata_document, _ = _json_response(
        transport,
        group_metadata_endpoint(group_id),
        context="library",
    )
    _verify_group_metadata(metadata_document, group_id)
    return LibraryCandidate(
        library_alias,
        "group",
        group_id,
        principal_relation_verified=True,
    )


def _collections_endpoint(candidate: LibraryCandidate, start: int) -> _Endpoint:
    if candidate.library_type == "user":
        return user_collections_endpoint(candidate.library_id, start)
    return group_collections_endpoint(candidate.library_id, start)


def _items_endpoint(candidate: LibraryCandidate, collection_key: str) -> _Endpoint:
    if candidate.library_type == "user":
        return user_collection_items_endpoint(candidate.library_id, collection_key)
    return group_collection_items_endpoint(candidate.library_id, collection_key)


def resolve_collection(
    transport: ReadOnlyTransport,
    candidate: LibraryCandidate,
    collection_name: str,
) -> CollectionCandidate:
    if collection_name != CANONICAL_COLLECTION_NAME:
        fail("COLLECTION_NOT_FOUND")
    start = 0
    exact_keys: list[str] = []
    total_hint: int | None = None

    while True:
        document, response = _json_response(
            transport,
            _collections_endpoint(candidate, start),
            context="collection",
        )
        if not isinstance(document, list) or len(document) > COLLECTION_PAGE_SIZE:
            fail("RESPONSE_INVALID")

        for raw_record in document:
            record = _mapping(raw_record)
            data = _mapping(record.get("data"))
            name = data.get("name")
            if not isinstance(name, str):
                fail("RESPONSE_INVALID")
            if name == collection_name:
                raw_key = record.get("key", data.get("key"))
                exact_keys.append(_collection_key(raw_key))
                if len(exact_keys) > 1:
                    fail("COLLECTION_AMBIGUOUS")

        total_header = _header(response.headers, "Total-Results")
        if total_header is not None:
            if re.fullmatch(r"[0-9]+", total_header) is None:
                fail("RESPONSE_INVALID")
            observed_total = int(total_header)
            if total_hint is not None and observed_total != total_hint:
                fail("RESPONSE_INVALID")
            total_hint = observed_total

        retrieved_count = start + len(document)
        if retrieved_count > MAX_COLLECTION_RECORDS:
            fail("NEEDS_REVIEW")
        if total_hint is not None:
            if retrieved_count > total_hint:
                fail("RESPONSE_INVALID")
            if retrieved_count == total_hint:
                break
            if not document:
                fail("RESPONSE_INVALID")
            start = retrieved_count
            continue
        if not document or len(document) < COLLECTION_PAGE_SIZE:
            break
        start = retrieved_count

    if not exact_keys:
        fail("COLLECTION_NOT_FOUND")
    return CollectionCandidate(exact_keys[0], exact_match_count=1)


def prove_item_read(
    transport: ReadOnlyTransport,
    candidate: LibraryCandidate,
    collection: CollectionCandidate,
) -> None:
    document, _ = _json_response(
        transport,
        _items_endpoint(candidate, collection.collection_key),
        context="item_read",
    )
    if not isinstance(document, list):
        fail("RESPONSE_INVALID")
    # Deliberately do not parse, retain, or serialize sampled bibliographic data.


def run_preflight(
    transport: ReadOnlyTransport,
    *,
    library_alias: str,
    library_type: str,
    library_id: str | None,
    collection_name: str,
) -> PreflightResult:
    candidate = resolve_library(
        transport,
        library_alias=library_alias,
        library_type=library_type,
        library_id=library_id,
    )
    collection = resolve_collection(transport, candidate, collection_name)
    prove_item_read(transport, candidate, collection)
    return PreflightResult(
        schema_version="1.0",
        status="PASS",
        transport="web_api",
        api_version=API_VERSION,
        library_alias=candidate.library_alias,
        candidate_library_type=candidate.library_type,
        candidate_library_id=candidate.library_id,
        read_access_verified=True,
        write_access_verified_false=True,
        principal_relation_verified=candidate.principal_relation_verified,
        collection_exact_match_count=collection.exact_match_count,
        candidate_collection_key=collection.collection_key,
        generic_item_read_verified=True,
        http_status_class="2xx",
    )


def _synthetic_response(value: Any, **headers: str) -> TransportResponse:
    safe_headers = {"Zotero-API-Version": "3", **headers}
    return TransportResponse(
        200,
        safe_headers,
        json.dumps(value, ensure_ascii=False).encode("utf-8"),
    )


def self_test() -> int:
    script = [
        (
            keys_current_endpoint(),
            _synthetic_response(
                {
                    "userID": 101,
                    "access": {"user": {"library": True, "write": False}},
                }
            ),
        ),
        (
            user_collections_endpoint("101", 0),
            _synthetic_response(
                [{"key": "COLL0001", "data": {"name": CANONICAL_COLLECTION_NAME}}]
            ),
        ),
        (user_collection_items_endpoint("101", "COLL0001"), _synthetic_response([])),
    ]
    transport = FixtureTransport(script)
    checks: list[bool] = []
    try:
        result = run_preflight(
            transport,
            library_alias=CANONICAL_LIBRARY_ALIAS,
            library_type="user",
            library_id=None,
            collection_name=CANONICAL_COLLECTION_NAME,
        )
        checks.extend(
            [
                result.status == "PASS",
                result.transport == "web_api",
                result.api_version == 3,
                result.write_access_verified_false,
                result.generic_item_read_verified,
                transport.remaining == 0,
            ]
        )
    except PreflightError:
        checks.append(False)

    output = {
        "status": "PASS" if checks and all(checks) else "FAIL",
        "mode": "self-test",
        "network_used": False,
        "credential_read": False,
        "checks_run": len(checks),
        "checks_passed": sum(checks),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if checks and all(checks) else 1


def failure_document(error: PreflightError) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "status": "STOP",
        "failure_code": error.code,
        "transport": "web_api",
        "api_version": API_VERSION,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("self-test", help="run an offline synthetic self-test")
    live = subparsers.add_parser("preflight", help="run the bounded future live preflight")
    live.add_argument("--library-alias", required=True)
    live.add_argument("--library-type", required=True, choices=("user", "group"))
    live.add_argument("--library-id")
    live.add_argument("--collection-name", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "self-test":
        return self_test()

    try:
        if args.library_alias != CANONICAL_LIBRARY_ALIAS:
            fail("LIBRARY_IDENTITY_AMBIGUOUS")
        if args.collection_name != CANONICAL_COLLECTION_NAME:
            fail("COLLECTION_NOT_FOUND")
        if args.library_type == "user" and args.library_id is not None:
            fail("LIBRARY_IDENTITY_AMBIGUOUS")
        if args.library_type == "group":
            _numeric_id(args.library_id)
        api_key = read_api_key()
        result = run_preflight(
            UrllibReadOnlyTransport(api_key),
            library_alias=args.library_alias,
            library_type=args.library_type,
            library_id=args.library_id,
            collection_name=args.collection_name,
        )
    except PreflightError as exc:
        print(
            json.dumps(
                failure_document(exc),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1

    print(
        json.dumps(
            result.serializable(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
