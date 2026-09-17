#!/usr/bin/env python3
"""Offline synthetic tests for the GET-only Zotero Phase-3 preflight."""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import io
import json
import os
import socket
import subprocess
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import zotero_readonly_preflight as preflight


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "scripts/literature/zotero_readonly_preflight.py"
TEST_PATH = ROOT / "scripts/literature/test_zotero_readonly_preflight.py"

PROTECTED_PATHS = (
    "scripts/literature/zotero_executor.py",
    "scripts/literature/test_zotero_executor.py",
    "scripts/literature/materialize_packet.py",
    "scripts/literature/literature_validate.py",
    "scripts/kb_validate.py",
    "05_Literature/ZOTERO_INTEGRATION_CONFIG.yaml",
    "05_Literature/SOURCE_REGISTRY.yaml",
    "05_Literature/MATERIALIZATION_LOG.yaml",
    "03_Protocols/LIT_ZOTERO_INTEGRATION_SPEC_V1_0.md",
    "00_Project/PROJECT_METADATA.yaml",
    "00_Project/PROJECT_STATE.md",
    "00_Project/PROJECT_CONTROL.md",
    "requirements.txt",
    ".gitignore",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


PROTECTED_BASELINE = {
    relative: digest(ROOT / relative)
    for relative in PROTECTED_PATHS
    if (ROOT / relative).is_file()
}


def response(
    value: object = None,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    raw: bytes | None = None,
) -> preflight.TransportResponse:
    response_headers = {"Zotero-API-Version": "3"}
    if headers:
        response_headers.update(headers)
    body = raw if raw is not None else json.dumps(value, ensure_ascii=False).encode("utf-8")
    return preflight.TransportResponse(status, response_headers, body)


def user_key(*, read: bool = True, write: bool = False) -> dict:
    return {
        "userID": 101,
        "access": {"user": {"library": read, "write": write}},
    }


def group_key(
    *,
    group_id: str = "202",
    read: bool = True,
    write: bool = False,
    use_all: bool = False,
) -> dict:
    key = "all" if use_all else group_id
    return {
        "userID": 101,
        "access": {"groups": {key: {"library": read, "write": write}}},
    }


def collection(name: str = "CEF Dy", key: str = "COLL0001") -> dict:
    return {"key": key, "data": {"key": key, "name": name}}


def user_success_transport(
    *,
    collection_records: list[dict] | None = None,
    item_records: list[dict] | None = None,
) -> preflight.FixtureTransport:
    records = [collection()] if collection_records is None else collection_records
    items = [] if item_records is None else item_records
    return preflight.FixtureTransport(
        [
            (preflight.keys_current_endpoint(), response(user_key())),
            (preflight.user_collections_endpoint("101", 0), response(records)),
            (
                preflight.user_collection_items_endpoint("101", "COLL0001"),
                response(items),
            ),
        ]
    )


def run_user(transport: preflight.ReadOnlyTransport) -> preflight.PreflightResult:
    return preflight.run_preflight(
        transport,
        library_alias="project-main",
        library_type="user",
        library_id=None,
        collection_name="CEF Dy",
    )


def run_group(
    transport: preflight.ReadOnlyTransport,
    group_id: str = "202",
) -> preflight.PreflightResult:
    return preflight.run_preflight(
        transport,
        library_alias="project-main",
        library_type="group",
        library_id=group_id,
        collection_name="CEF Dy",
    )


class DummyHTTPResponse:
    def __init__(self, body: bytes = b"{}") -> None:
        self.status = 200
        self.headers = {"Zotero-API-Version": "3"}
        self._body = body

    def read(self, size: int = -1) -> bytes:
        del size
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "DummyHTTPResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback


class CapturingOpener:
    def __init__(self, result: object | None = None) -> None:
        self.request: urllib.request.Request | None = None
        self.timeout: float | None = None
        self.result = result if result is not None else DummyHTTPResponse()

    def open(self, request: urllib.request.Request, timeout: float) -> object:
        self.request = request
        self.timeout = timeout
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class OriginAndEndpointFirewallTests(unittest.TestCase):
    def assert_code(self, code: str, callback: object) -> None:
        with self.assertRaises(preflight.PreflightError) as caught:
            callback()  # type: ignore[operator]
        self.assertEqual(caught.exception.code, code)

    def test_01_https_api_origin_is_accepted(self) -> None:
        preflight._validate_origin_url("https://api.zotero.org/keys/current")
        self.assertEqual(
            preflight.endpoint_url(preflight.keys_current_endpoint()),
            "https://api.zotero.org/keys/current",
        )

    def test_02_non_https_is_rejected(self) -> None:
        self.assert_code(
            "ENDPOINT_FORBIDDEN",
            lambda: preflight._validate_origin_url("http://api.zotero.org/keys/current"),
        )

    def test_03_foreign_host_is_rejected(self) -> None:
        self.assert_code(
            "ENDPOINT_FORBIDDEN",
            lambda: preflight._validate_origin_url("https://example.invalid/keys/current"),
        )

    def test_04_localhost_and_ip_are_rejected(self) -> None:
        for url in ("https://localhost/keys/current", "https://127.0.0.1/keys/current"):
            with self.subTest(url=url):
                self.assert_code(
                    "ENDPOINT_FORBIDDEN", lambda url=url: preflight._validate_origin_url(url)
                )

    def test_05_caller_supplied_absolute_endpoint_is_rejected(self) -> None:
        endpoint = preflight._Endpoint("https://api.zotero.org/keys/current")
        self.assert_code("ENDPOINT_FORBIDDEN", lambda: preflight.endpoint_url(endpoint))

    def test_06_unknown_endpoint_is_rejected(self) -> None:
        endpoint = preflight._Endpoint("/users/101/items")
        self.assert_code("ENDPOINT_FORBIDDEN", lambda: preflight.endpoint_url(endpoint))

    def test_07_credential_query_parameter_is_rejected(self) -> None:
        endpoint = preflight._Endpoint("/keys/current", (("key", "synthetic"),))
        self.assert_code("ENDPOINT_FORBIDDEN", lambda: preflight.endpoint_url(endpoint))

    def test_08_only_required_endpoint_families_build(self) -> None:
        endpoints = (
            preflight.keys_current_endpoint(),
            preflight.user_collections_endpoint("101", 0),
            preflight.user_collection_items_endpoint("101", "COLL0001"),
            preflight.user_groups_endpoint("101"),
            preflight.group_metadata_endpoint("202"),
            preflight.group_collections_endpoint("202", 0),
            preflight.group_collection_items_endpoint("202", "COLL0001"),
        )
        self.assertTrue(all(preflight.endpoint_url(item).startswith(preflight.API_ORIGIN) for item in endpoints))

    def test_09_transport_protocol_exposes_only_get(self) -> None:
        public = {
            name
            for name, value in preflight.ReadOnlyTransport.__dict__.items()
            if callable(value) and not name.startswith("_")
        }
        self.assertEqual(public, {"get"})
        self.assertNotIn("method", inspect.signature(preflight.ReadOnlyTransport.get).parameters)

    def test_10_mutating_methods_are_structurally_absent(self) -> None:
        source = SOURCE_PATH.read_text(encoding="utf-8")
        for forbidden in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_11_live_request_has_fixed_get_and_required_headers(self) -> None:
        secret = "synthetic-" + "x" * 32
        opener = CapturingOpener()
        transport = preflight.UrllibReadOnlyTransport(secret, opener=opener)
        transport.get(preflight.keys_current_endpoint())
        self.assertIsNotNone(opener.request)
        request = opener.request
        assert request is not None
        headers = {key.casefold(): value for key, value in request.header_items()}
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(headers["zotero-api-version"], "3")
        self.assertEqual(headers["zotero-api-key"], secret)
        self.assertEqual(headers["accept"], "application/json")
        self.assertNotIn(secret, request.full_url)

    def test_12_redirect_handler_rejects_without_following(self) -> None:
        handler = preflight._RejectRedirectHandler()
        with self.assertRaises(preflight.PreflightError) as caught:
            handler.redirect_request(None, None, 302, "redirect", {}, "https://example.invalid")
        self.assertEqual(caught.exception.code, "REDIRECT_FORBIDDEN")


class CredentialBoundaryTests(unittest.TestCase):
    def test_13_missing_environment_key_is_classified(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(preflight.PreflightError) as caught:
                preflight.read_api_key()
        self.assertEqual(caught.exception.code, "CREDENTIAL_NOT_CONFIGURED")

    def test_14_synthetic_environment_key_is_accepted(self) -> None:
        secret = "synthetic-" + "a" * 32
        with mock.patch.dict(os.environ, {"ZOTERO_API_KEY": secret}, clear=True):
            self.assertEqual(preflight.read_api_key(), secret)

    def test_15_real_host_key_cannot_be_consumed_by_isolated_test(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertNotIn("ZOTERO_API_KEY", os.environ)
            with self.assertRaises(preflight.PreflightError):
                preflight.read_api_key()

    def test_16_credential_is_absent_from_success_result(self) -> None:
        secret = "synthetic-" + "b" * 32
        result = run_user(user_success_transport())
        self.assertNotIn(secret, json.dumps(result.serializable(), sort_keys=True))

    def test_17_credential_is_absent_from_exception_string(self) -> None:
        secret = "synthetic-" + "c" * 32
        opener = CapturingOpener(urllib.error.URLError("synthetic transport failure"))
        transport = preflight.UrllibReadOnlyTransport(secret, opener=opener)
        with self.assertRaises(preflight.PreflightError) as caught:
            transport.get(preflight.keys_current_endpoint())
        self.assertNotIn(secret, str(caught.exception))
        self.assertEqual(caught.exception.code, "NETWORK_ERROR")

    def test_18_credential_is_absent_from_stdout_and_stderr(self) -> None:
        secret = "synthetic-" + "d" * 32
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"ZOTERO_API_KEY": secret}, clear=True), mock.patch.object(
            preflight.UrllibReadOnlyTransport,
            "get",
            side_effect=preflight.PreflightError("NETWORK_ERROR"),
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = preflight.main(
                [
                    "preflight",
                    "--library-alias",
                    "project-main",
                    "--library-type",
                    "user",
                    "--collection-name",
                    "CEF Dy",
                ]
            )
        self.assertEqual(code, 1)
        self.assertNotIn(secret, stdout.getvalue())
        self.assertNotIn(secret, stderr.getvalue())

    def test_19_credential_is_not_persisted_to_repository(self) -> None:
        secret = "phase3-" + hashlib.sha256(str(id(self)).encode("ascii")).hexdigest()
        with mock.patch.dict(os.environ, {"ZOTERO_API_KEY": secret}, clear=True):
            self.assertEqual(preflight.read_api_key(), secret)
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            self.assertNotIn(secret.encode("utf-8"), data, str(path))

    def test_20_cli_has_no_credential_or_generic_transport_options(self) -> None:
        help_text = preflight.build_parser().format_help()
        source = SOURCE_PATH.read_text(encoding="utf-8")
        for option in (
            "--api-key",
            "--url",
            "--method",
            "--write",
            "--create",
            "--update",
            "--delete",
            "--local-api",
        ):
            with self.subTest(option=option):
                self.assertNotIn(option, help_text)
                self.assertNotIn(option, source)


class PermissionAndLibraryBindingTests(unittest.TestCase):
    def test_21_user_read_only_permissions_and_exact_binding_succeed(self) -> None:
        result = run_user(user_success_transport())
        self.assertEqual(result.candidate_library_type, "user")
        self.assertEqual(result.candidate_library_id, "101")
        self.assertTrue(result.read_access_verified)
        self.assertTrue(result.write_access_verified_false)
        self.assertTrue(result.principal_relation_verified)

    def test_22_user_write_permission_stops_before_library_request(self) -> None:
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), response(user_key(write=True)))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "UNEXPECTED_WRITE_CAPABILITY")
        self.assertEqual(len(transport.calls), 1)

    def test_23_group_read_only_permissions_and_explicit_binding_succeed(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(group_key())),
                (preflight.user_groups_endpoint("101"), response({"202": 7})),
                (preflight.group_metadata_endpoint("202"), response({"id": 202, "data": {"id": 202}})),
                (preflight.group_collections_endpoint("202", 0), response([collection()])),
                (preflight.group_collection_items_endpoint("202", "COLL0001"), response([])),
            ]
        )
        result = run_group(transport)
        self.assertEqual(result.candidate_library_type, "group")
        self.assertEqual(result.candidate_library_id, "202")
        self.assertTrue(result.principal_relation_verified)

    def test_24_group_all_read_only_permission_is_accepted(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(group_key(use_all=True))),
                (preflight.user_groups_endpoint("101"), response({"202": 7})),
                (preflight.group_metadata_endpoint("202"), response({"id": 202})),
                (preflight.group_collections_endpoint("202", 0), response([collection()])),
                (preflight.group_collection_items_endpoint("202", "COLL0001"), response([])),
            ]
        )
        self.assertEqual(run_group(transport).status, "PASS")

    def test_25_group_write_permission_stops_before_relation_request(self) -> None:
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), response(group_key(write=True)))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_group(transport)
        self.assertEqual(caught.exception.code, "UNEXPECTED_WRITE_CAPABILITY")
        self.assertEqual(len(transport.calls), 1)

    def test_26_authentication_rejection_is_classified(self) -> None:
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), response(status=401, raw=b""))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "CREDENTIAL_REJECTED")

    def test_27_read_denial_is_classified(self) -> None:
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), response(user_key(read=False)))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "READ_ACCESS_DENIED")

    def test_28_http_read_denial_after_authentication_is_classified(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(user_key())),
                (preflight.user_collections_endpoint("101", 0), response(status=403, raw=b"")),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "READ_ACCESS_DENIED")

    def test_29_malformed_permission_structure_fails_closed(self) -> None:
        malformed = {"userID": 101, "access": {"user": {"library": True}}}
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), response(malformed))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "RESPONSE_INVALID")

    def test_30_missing_principal_identity_fails_closed(self) -> None:
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), response({"access": user_key()["access"]}))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "RESPONSE_INVALID")

    def test_31_group_relation_mismatch_is_rejected(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(group_key())),
                (preflight.user_groups_endpoint("101"), response({"303": 1})),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_group(transport)
        self.assertEqual(caught.exception.code, "LIBRARY_NOT_FOUND")

    def test_32_conflicting_group_metadata_is_ambiguous(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(group_key())),
                (preflight.user_groups_endpoint("101"), response({"202": 1})),
                (preflight.group_metadata_endpoint("202"), response({"id": 202, "data": {"id": 303}})),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_group(transport)
        self.assertEqual(caught.exception.code, "LIBRARY_IDENTITY_AMBIGUOUS")

    def test_33_missing_group_library_is_classified(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(group_key())),
                (preflight.user_groups_endpoint("101"), response({"202": 1})),
                (preflight.group_metadata_endpoint("202"), response(status=404, raw=b"")),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_group(transport)
        self.assertEqual(caught.exception.code, "LIBRARY_NOT_FOUND")


class CollectionAndItemProofTests(unittest.TestCase):
    def test_34_zero_exact_collection_matches(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(user_key())),
                (preflight.user_collections_endpoint("101", 0), response([collection("Other")])),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "COLLECTION_NOT_FOUND")

    def test_35_one_exact_collection_match(self) -> None:
        result = run_user(user_success_transport())
        self.assertEqual(result.collection_exact_match_count, 1)
        self.assertEqual(result.candidate_collection_key, "COLL0001")

    def test_36_multiple_exact_collection_matches(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(user_key())),
                (
                    preflight.user_collections_endpoint("101", 0),
                    response([collection(key="COLL0001"), collection(key="COLL0002")]),
                ),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "COLLECTION_AMBIGUOUS")

    def test_37_case_and_fuzzy_collection_names_do_not_bind(self) -> None:
        records = [collection("cef dy", "COLL0002"), collection("CEF Dy ", "COLL0003")]
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(user_key())),
                (preflight.user_collections_endpoint("101", 0), response(records)),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "COLLECTION_NOT_FOUND")

    def test_38_collection_pagination_is_complete(self) -> None:
        first_page = [collection(f"Other {index}", f"K{index:07d}") for index in range(100)]
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(user_key())),
                (
                    preflight.user_collections_endpoint("101", 0),
                    response(first_page, headers={"Total-Results": "101"}),
                ),
                (
                    preflight.user_collections_endpoint("101", 100),
                    response([collection()], headers={"Total-Results": "101"}),
                ),
                (preflight.user_collection_items_endpoint("101", "COLL0001"), response([])),
            ]
        )
        result = run_user(transport)
        self.assertEqual(result.candidate_collection_key, "COLL0001")
        self.assertEqual(len(transport.calls), 4)

    def test_39_nonempty_item_read_is_verified_and_redacted(self) -> None:
        private_item = {
            "key": "ITEM0001",
            "data": {
                "title": "PRIVATE-TITLE-SENTINEL",
                "creators": [{"lastName": "PRIVATE-CREATOR-SENTINEL"}],
                "DOI": "10.1000/private-sentinel",
                "note": "PRIVATE-NOTE-SENTINEL",
            },
        }
        result = run_user(user_success_transport(item_records=[private_item]))
        serialized = json.dumps(result.serializable(), sort_keys=True)
        self.assertTrue(result.generic_item_read_verified)
        for sentinel in (
            "PRIVATE-TITLE-SENTINEL",
            "PRIVATE-CREATOR-SENTINEL",
            "10.1000/private-sentinel",
            "PRIVATE-NOTE-SENTINEL",
            "ITEM0001",
        ):
            self.assertNotIn(sentinel, serialized)

    def test_40_empty_collection_is_valid_item_read_proof(self) -> None:
        result = run_user(user_success_transport(item_records=[]))
        self.assertTrue(result.generic_item_read_verified)

    def test_41_item_response_must_be_a_list(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(user_key())),
                (preflight.user_collections_endpoint("101", 0), response([collection()])),
                (preflight.user_collection_items_endpoint("101", "COLL0001"), response({})),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "RESPONSE_INVALID")

    def test_42_malformed_json_is_rejected(self) -> None:
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), response(raw=b"{not-json"))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "RESPONSE_INVALID")

    def test_43_required_collection_field_absence_is_rejected(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(user_key())),
                (preflight.user_collections_endpoint("101", 0), response([{"data": {}}])),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "RESPONSE_INVALID")

    def test_44_timeout_is_network_error(self) -> None:
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), TimeoutError("synthetic timeout"))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "NETWORK_ERROR")

    def test_45_rate_limit_is_classified(self) -> None:
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), response(status=429, raw=b""))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "RATE_LIMITED")

    def test_46_redirect_response_is_rejected(self) -> None:
        transport = preflight.FixtureTransport(
            [(preflight.keys_current_endpoint(), response(status=302, raw=b""))]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "REDIRECT_FORBIDDEN")

    def test_47_api_version_mismatch_is_rejected(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (
                    preflight.keys_current_endpoint(),
                    response(user_key(), headers={"Zotero-API-Version": "2"}),
                )
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "API_VERSION_MISMATCH")

    def test_48_invalid_total_results_header_fails_closed(self) -> None:
        transport = preflight.FixtureTransport(
            [
                (preflight.keys_current_endpoint(), response(user_key())),
                (
                    preflight.user_collections_endpoint("101", 0),
                    response([collection()], headers={"Total-Results": "unknown"}),
                ),
            ]
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            run_user(transport)
        self.assertEqual(caught.exception.code, "RESPONSE_INVALID")


class CliAndRepositoryBoundaryTests(unittest.TestCase):
    def test_49_self_test_is_offline_machine_readable(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(preflight, "read_api_key", side_effect=AssertionError("credential read")), contextlib.redirect_stdout(stdout):
            code = preflight.main(["self-test"])
        self.assertEqual(code, 0)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        result = json.loads(lines[0])
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["network_used"])
        self.assertFalse(result["credential_read"])

    def test_50_no_arguments_prints_usage_to_stderr_and_exits_two(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                preflight.main([])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("usage:", stderr.getvalue())

    def test_51_user_library_id_is_rejected_before_credential_read(self) -> None:
        with mock.patch.object(preflight, "read_api_key", side_effect=AssertionError("credential read")):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = preflight.main(
                    [
                        "preflight",
                        "--library-alias",
                        "project-main",
                        "--library-type",
                        "user",
                        "--library-id",
                        "101",
                        "--collection-name",
                        "CEF Dy",
                    ]
                )
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["failure_code"], "LIBRARY_IDENTITY_AMBIGUOUS")

    def test_52_group_library_id_is_required_and_numeric(self) -> None:
        for value in (None, "zero", "0"):
            arguments = [
                "preflight",
                "--library-alias",
                "project-main",
                "--library-type",
                "group",
                "--collection-name",
                "CEF Dy",
            ]
            if value is not None:
                arguments.extend(["--library-id", value])
            with self.subTest(value=value), mock.patch.object(
                preflight, "read_api_key", side_effect=AssertionError("credential read")
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = preflight.main(arguments)
                self.assertEqual(code, 1)
                self.assertEqual(
                    json.loads(stdout.getvalue())["failure_code"],
                    "LIBRARY_IDENTITY_AMBIGUOUS",
                )

    def test_53_production_source_excludes_local_api_pilots_and_mutation_logic(self) -> None:
        source = SOURCE_PATH.read_text(encoding="utf-8")
        forbidden = (
            "local_api",
            "Zotero-Write-Token",
            "If-Unmodified-Since-Version",
            "SRC-000001",
            "SRC-000002",
            "Klement",
            "Scheie",
            "pyzotero",
            "requests.",
            "httpx",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, source)

    def test_54_network_block_harness_rejects_socket_and_http(self) -> None:
        def blocked(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise AssertionError("network blocked")

        with mock.patch("socket.socket", side_effect=blocked), mock.patch(
            "socket.create_connection", side_effect=blocked
        ), mock.patch("urllib.request.urlopen", side_effect=blocked), mock.patch(
            "urllib.request.OpenerDirector.open", side_effect=blocked
        ):
            with self.assertRaises(AssertionError):
                socket.create_connection(("api.zotero.org", 443))
            with self.assertRaises(AssertionError):
                urllib.request.urlopen("https://api.zotero.org/keys/current")

    def test_55_protected_files_and_forbidden_artifacts_are_unchanged(self) -> None:
        protected_after = {
            relative: digest(ROOT / relative)
            for relative in PROTECTED_BASELINE
        }
        self.assertEqual(PROTECTED_BASELINE, protected_after)
        for relative in (
            "05_Literature/ZOTERO_OPERATION_LOG.yaml",
            "05_Literature/references.bib",
            ".env",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_56_worktree_scope_contains_only_the_two_new_files(self) -> None:
        process = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        changed = {
            line[3:]
            for line in process.stdout.splitlines()
            if line.strip()
        }
        self.assertEqual(
            changed,
            {
                "scripts/literature/zotero_readonly_preflight.py",
                "scripts/literature/test_zotero_readonly_preflight.py",
            },
        )


def network_forbidden(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise AssertionError("real network access attempted by Phase-3 synthetic tests")


if __name__ == "__main__":
    with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
        "socket.socket", side_effect=network_forbidden
    ), mock.patch(
        "socket.create_connection", side_effect=network_forbidden
    ), mock.patch(
        "urllib.request.urlopen", side_effect=network_forbidden
    ), mock.patch(
        "urllib.request.OpenerDirector.open", side_effect=network_forbidden
    ):
        unittest.main(verbosity=2)
