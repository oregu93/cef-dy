"""Private, non-authoritative Telegram attention transport.

The gateway is deliberately a projection adapter.  SQLite remains the durable
operational authority, Git/canonical governance remain authoritative, and no
Telegram input can grant scientific or Project-Control authority.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Iterator, Protocol
from urllib import error, parse, request
import uuid

from .model import utc_now
from .reliability import M1bStore
from .authoring import is_historical_lifecycle_receipt


TELEGRAM_SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_gateway_state (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  update_offset INTEGER NOT NULL DEFAULT 0,
  control_mode TEXT NOT NULL DEFAULT 'NORMAL',
  muted_until REAL,
  observed_at TEXT,
  last_error TEXT
);
INSERT OR IGNORE INTO telegram_gateway_state(singleton) VALUES(1);
CREATE TABLE IF NOT EXISTS telegram_updates (
  update_id INTEGER PRIMARY KEY,
  payload_hash TEXT NOT NULL,
  outcome TEXT NOT NULL,
  received_at TEXT NOT NULL,
  processed_at TEXT
);
CREATE TABLE IF NOT EXISTS telegram_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  update_id INTEGER,
  event_type TEXT NOT NULL,
  subject_id TEXT,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS telegram_projections (
  projection_id TEXT PRIMARY KEY,
  attention_id TEXT NOT NULL,
  source_event_id TEXT NOT NULL,
  task_id TEXT,
  kind TEXT NOT NULL,
  projection_digest TEXT NOT NULL,
  body_json TEXT NOT NULL,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(attention_id,projection_digest)
);
CREATE TABLE IF NOT EXISTS telegram_deliveries (
  delivery_id TEXT PRIMARY KEY,
  projection_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  claim_owner TEXT,
  claim_expires_at REAL,
  next_attempt_at REAL NOT NULL DEFAULT 0,
  telegram_message_id TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS telegram_delivery_attempts (
  attempt_id TEXT PRIMARY KEY,
  delivery_id TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  outcome TEXT NOT NULL,
  telegram_message_id TEXT,
  detail TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS telegram_questions (
  attention_id TEXT NOT NULL,
  question_version INTEGER NOT NULL,
  task_id TEXT NOT NULL,
  question_kind TEXT NOT NULL,
  constraints_json TEXT NOT NULL,
  state TEXT NOT NULL,
  selected_response_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(attention_id,question_version)
);
CREATE TABLE IF NOT EXISTS telegram_responses (
  response_id TEXT PRIMARY KEY,
  attention_id TEXT NOT NULL,
  question_version INTEGER NOT NULL,
  update_id INTEGER NOT NULL UNIQUE,
  response_text TEXT NOT NULL,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS telegram_user_decisions (
  decision_id TEXT PRIMARY KEY,
  response_id TEXT NOT NULL UNIQUE,
  task_id TEXT NOT NULL,
  decision_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS telegram_confirmations (
  token TEXT PRIMARY KEY,
  update_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  subject_id TEXT,
  expected_state TEXT NOT NULL,
  expires_at REAL NOT NULL,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL,
  used_at TEXT
);
CREATE TABLE IF NOT EXISTS telegram_holds (
  task_id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  source_update_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  released_at TEXT
);
"""

NOTIFICATION_KINDS = {
    "HUMAN_ACTION_REQUIRED", "PROJECT_STALLED", "SCIENTIFIC_DECISION_REQUIRED",
    "RECOVERY_FAILED", "MAJOR_MILESTONE",
}
DELIVERY_STATES = {
    "READY", "CLAIMED", "SEND_OUTCOME_UNKNOWN", "SENT", "RETRY_WAIT",
    "DEAD_LETTER", "CANCELLED",
}
CONTROL_COMMANDS = {
    "/pause_ai", "/drain", "/quiesce", "/safe", "/resume", "/mute",
    "/unmute", "/hold", "/release",
}
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _safe_text(value: Any, limit: int = 500) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    text = re.sub(r"(?i)(token|password|secret|authorization)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)\b(?:gh[oprsu]_[A-Za-z0-9_]{12,}|xox[baprs]-\S+|\d{5,}:[A-Za-z0-9_-]{20,})", "[credential]", text)
    text = re.sub(r"(?<![A-Za-z0-9._-])/(?:[^\s/]+/)+[^\s]*", "[path]", text)
    text = re.sub(r"\b[A-Za-z]:\\(?:[^\s\\]+\\)+[^\s]*", "[path]", text)
    text = re.sub(r"@[A-Za-z0-9_]{2,}", "[mention]", text)
    return text[:limit]


@dataclass(frozen=True)
class TelegramSecrets:
    token: str
    user_id: int
    chat_id: int

    @classmethod
    def from_environment(cls, cfg: dict[str, Any]) -> "TelegramSecrets":
        section = cfg["telegram"]
        secret_file = Path(section["secret_file"]).expanduser()
        try:
            mode = secret_file.stat().st_mode & 0o777
        except OSError as exc:
            raise RuntimeError("Telegram secret file is unavailable") from exc
        if not secret_file.is_file() or mode != 0o600:
            raise RuntimeError("Telegram secret file must be a regular mode-0600 file")
        values = [os.environ.get(section[name], "") for name in (
            "token_env", "allowed_user_id_env", "allowed_chat_id_env",
        )]
        if not all(values):
            raise RuntimeError("Telegram secret environment is incomplete")
        try:
            user_id, chat_id = int(values[1]), int(values[2])
        except ValueError as exc:
            raise RuntimeError("Telegram allowlist identifiers must be integers") from exc
        if not values[0].strip() or user_id == 0 or chat_id == 0:
            raise RuntimeError("Telegram secret environment is invalid")
        return cls(values[0], user_id, chat_id)


class TelegramTransport(Protocol):
    def get_updates(self, *, offset: int, timeout_seconds: int) -> list[dict[str, Any]]: ...
    def send_message(self, *, text: str, reply_markup: dict[str, Any] | None = None) -> str: ...


class TelegramTransportError(RuntimeError):
    pass


class SendOutcomeUnknown(TelegramTransportError):
    """The caller cannot prove whether Telegram accepted sendMessage."""



class TelegramBotAPI:
    """Minimal Bot API transport.  It has no inbound listener."""

    def __init__(self, secrets: TelegramSecrets, *, api_base: str, timeout_seconds: int):
        if api_base.rstrip("/") != "https://api.telegram.org":
            raise RuntimeError("Telegram api_base must be https://api.telegram.org")
        self._token = secrets.token
        self._chat_id = secrets.chat_id
        self._base = api_base.rstrip("/")
        self._timeout = int(timeout_seconds)

    def _call(self, method: str, payload: dict[str, Any]) -> Any:
        encoded = parse.urlencode({
            key: _canonical(value) if isinstance(value, (dict, list)) else str(value)
            for key, value in payload.items()
        }).encode()
        req = request.Request(
            f"{self._base}/bot{self._token}/{method}", data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
        )
        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError) as exc:
            exception = SendOutcomeUnknown if method == "sendMessage" else TelegramTransportError
            raise exception(f"Telegram transport {type(exc).__name__}") from exc
        except json.JSONDecodeError as exc:
            raise TelegramTransportError("Telegram response was not valid JSON") from exc
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise TelegramTransportError("Telegram API rejected request")
        return value.get("result")

    def get_updates(self, *, offset: int, timeout_seconds: int) -> list[dict[str, Any]]:
        result = self._call("getUpdates", {
            "offset": offset, "timeout": timeout_seconds,
            "allowed_updates": ["message", "callback_query"],
        })
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise RuntimeError("Telegram updates payload invalid")
        return result

    def send_message(self, *, text: str, reply_markup: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {"chat_id": self._chat_id, "text": text, "disable_web_page_preview": True}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = self._call("sendMessage", payload)
        if not isinstance(result, dict) or not isinstance(result.get("message_id"), int):
            raise RuntimeError("Telegram send acknowledgement missing message_id")
        return str(result["message_id"])


class TelegramStore:
    """Durable gateway state over the existing local SQLite authority."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.executescript(TELEGRAM_SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    def event(self, event_type: str, *, update_id: int | None = None,
              subject_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            "INSERT INTO telegram_events(update_id,event_type,subject_id,detail_json,created_at) VALUES(?,?,?,?,?)",
            (update_id, event_type, subject_id, _canonical(detail or {}), utc_now()),
        )

    def state(self) -> dict[str, Any]:
        return dict(self.conn.execute("SELECT * FROM telegram_gateway_state WHERE singleton=1").fetchone())

    def set_observation(self, state: str, detail: str, *, error_text: str | None = None) -> None:
        self.conn.execute(
            "UPDATE telegram_gateway_state SET observed_at=?,last_error=? WHERE singleton=1",
            (utc_now(), _safe_text(error_text, 300) if error_text else None),
        )
        self.event("GATEWAY_OBSERVATION", detail={"state": state, "detail": _safe_text(detail, 300)})

    def update_offset(self, offset: int) -> None:
        self.conn.execute(
            "UPDATE telegram_gateway_state SET update_offset=MAX(update_offset,?) WHERE singleton=1",
            (int(offset),),
        )

    def record_update(self, update_id: int, payload_hash: str) -> str:
        row = self.conn.execute(
            "SELECT payload_hash,outcome FROM telegram_updates WHERE update_id=?", (update_id,),
        ).fetchone()
        if row:
            if row[0] != payload_hash:
                return "conflict"
            return "resume" if row[1] == "RECEIVED" else "duplicate"
        self.conn.execute(
            "INSERT INTO telegram_updates(update_id,payload_hash,outcome,received_at) VALUES(?,?,?,?)",
            (update_id, payload_hash, "RECEIVED", utc_now()),
        )
        return "created"

    def finish_update(self, update_id: int, outcome: str) -> None:
        self.conn.execute(
            "UPDATE telegram_updates SET outcome=?,processed_at=? WHERE update_id=?",
            (outcome, utc_now(), update_id),
        )

    def enqueue_projection(self, *, attention_id: str, source_event_id: str,
                           task_id: str | None, kind: str, body: dict[str, Any],
                           major_milestones: bool = False) -> str:
        if kind not in NOTIFICATION_KINDS:
            return "suppressed"
        if kind == "MAJOR_MILESTONE" and not major_milestones:
            return "suppressed"
        for value in (attention_id, source_event_id):
            if _SAFE_ID.fullmatch(value) is None:
                raise ValueError("unsafe projection identity")
        safe_body = {
            "attention_id": attention_id,
            "task_id": task_id,
            "reason_code": _safe_text(body.get("reason_code"), 80),
            "safe_context": _safe_text(body.get("safe_context"), 400),
            "requested_response": _safe_text(body.get("requested_response"), 200),
            "consequence_of_no_action": _safe_text(body.get("consequence_of_no_action"), 200),
            "review_state": _safe_text(body.get("review_state"), 80),
            "created_at": str(body.get("created_at") or utc_now()),
            "source_event_id": source_event_id,
        }
        digest = _digest(safe_body)
        existing = self.conn.execute(
            "SELECT projection_digest FROM telegram_projections WHERE attention_id=? ORDER BY created_at DESC LIMIT 1",
            (attention_id,),
        ).fetchone()
        if existing and existing[0] == digest:
            return "duplicate"
        projection_id = hashlib.sha256(f"{attention_id}\0{digest}".encode()).hexdigest()
        delivery_id = hashlib.sha256(f"telegram\0{projection_id}".encode()).hexdigest()
        now = utc_now()
        with self.transaction():
            self.conn.execute(
                "INSERT INTO telegram_projections VALUES(?,?,?,?,?,?,?,?,?)",
                (projection_id, attention_id, source_event_id, task_id, kind, digest,
                 _canonical(safe_body), "VALIDATED", now),
            )
            self.conn.execute(
                "INSERT INTO telegram_deliveries(delivery_id,projection_id,state,created_at,updated_at) VALUES(?,?,?,?,?)",
                (delivery_id, projection_id, "READY", now, now),
            )
            self.event("PROJECTION_VALIDATED", subject_id=projection_id,
                       detail={"kind": kind, "attention_id": attention_id})
        return "enqueued"

    def open_question(self, *, attention_id: str, task_id: str, question_version: int = 1,
                      question_kind: str = "BOUNDED_TEXT", constraints: dict[str, Any] | None = None) -> None:
        now = utc_now()
        self.conn.execute(
            "INSERT OR IGNORE INTO telegram_questions VALUES(?,?,?,?,?,?,?,?,?)",
            (attention_id, question_version, task_id, question_kind,
             _canonical(constraints or {"max_length": 500}), "OPEN", None, now, now),
        )

    def claim_delivery(self, owner: str, now_epoch: float, lease_seconds: int) -> sqlite3.Row | None:
        with self.transaction():
            row = self.conn.execute(
                "SELECT d.*,p.body_json,p.kind,p.attention_id FROM telegram_deliveries d "
                "JOIN telegram_projections p USING(projection_id) "
                "WHERE d.state IN ('READY','RETRY_WAIT','SEND_OUTCOME_UNKNOWN') "
                "AND d.next_attempt_at<=? ORDER BY d.created_at,d.delivery_id LIMIT 1",
                (now_epoch,),
            ).fetchone()
            if row is None:
                return None
            changed = self.conn.execute(
                "UPDATE telegram_deliveries SET state='CLAIMED',claim_owner=?,claim_expires_at=?,attempts=attempts+1,updated_at=? "
                "WHERE delivery_id=? AND state=?",
                (owner, now_epoch + lease_seconds, utc_now(), row["delivery_id"], row["state"]),
            ).rowcount
            if changed != 1:
                return None
            return self.conn.execute(
                "SELECT d.*,p.body_json,p.kind,p.attention_id FROM telegram_deliveries d "
                "JOIN telegram_projections p USING(projection_id) WHERE d.delivery_id=?",
                (row["delivery_id"],),
            ).fetchone()

    def reconcile_expired_claims(self, now_epoch: float) -> int:
        rows = list(self.conn.execute(
            "SELECT delivery_id FROM telegram_deliveries WHERE state='CLAIMED' AND claim_expires_at<?",
            (now_epoch,),
        ))
        for row in rows:
            self.conn.execute(
                "UPDATE telegram_deliveries SET state='SEND_OUTCOME_UNKNOWN',claim_owner=NULL,claim_expires_at=NULL,"
                "next_attempt_at=?,last_error=?,updated_at=? WHERE delivery_id=?",
                (now_epoch + 30, "claim expired before durable send acknowledgement", utc_now(), row[0]),
            )
            self.event("SEND_OUTCOME_UNKNOWN", subject_id=row[0])
        return len(rows)

    def _finish_attempt(self, delivery: sqlite3.Row, outcome: str, *, message_id: str | None,
                        detail: str | None, state: str, next_attempt_at: float = 0) -> None:
        if state not in DELIVERY_STATES:
            raise ValueError("invalid delivery state")
        now = utc_now()
        self.conn.execute(
            "INSERT INTO telegram_delivery_attempts VALUES(?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), delivery["delivery_id"], delivery["attempts"], outcome,
             message_id, _safe_text(detail, 500) if detail else None, now, now),
        )
        self.conn.execute(
            "UPDATE telegram_deliveries SET state=?,telegram_message_id=COALESCE(?,telegram_message_id),"
            "last_error=?,claim_owner=NULL,claim_expires_at=NULL,next_attempt_at=?,updated_at=? WHERE delivery_id=?",
            (state, message_id, _safe_text(detail, 500) if detail else None,
             next_attempt_at, now, delivery["delivery_id"]),
        )
        self.event(outcome, subject_id=delivery["delivery_id"], detail={"attempt": delivery["attempts"]})

    def sent(self, delivery: sqlite3.Row, message_id: str) -> None:
        if not message_id:
            raise ValueError("SENT requires Telegram message_id")
        self._finish_attempt(delivery, "SENT", message_id=message_id, detail=None, state="SENT")

    def send_unknown(self, delivery: sqlite3.Row, reason: str, now_epoch: float,
                     max_attempts: int) -> None:
        terminal = int(delivery["attempts"]) >= int(max_attempts)
        detail = reason if not terminal else f"{reason}; bounded retry budget exhausted"
        self._finish_attempt(
            delivery, "SEND_OUTCOME_UNKNOWN", message_id=None, detail=detail,
            state="DEAD_LETTER" if terminal else "SEND_OUTCOME_UNKNOWN",
            next_attempt_at=0 if terminal else now_epoch + 30,
        )

    def retry(self, delivery: sqlite3.Row, reason: str, now_epoch: float, max_attempts: int) -> None:
        terminal = int(delivery["attempts"]) >= int(max_attempts)
        self._finish_attempt(
            delivery, "DEAD_LETTER" if terminal else "RETRY_WAIT", message_id=None,
            detail=reason, state="DEAD_LETTER" if terminal else "RETRY_WAIT",
            next_attempt_at=0 if terminal else now_epoch + min(300, 5 * 2 ** max(0, int(delivery["attempts"]) - 1)),
        )

    def accept_response(self, *, attention_id: str, update_id: int, text: str,
                        question_version: int = 1) -> str:
        if len(text) > 500 or not text.strip():
            return "INVALID_RESPONSE"
        now = utc_now()
        with self.transaction():
            duplicate = self.conn.execute(
                "SELECT response_id FROM telegram_responses WHERE update_id=?", (update_id,),
            ).fetchone()
            if duplicate:
                return "DUPLICATE"
            question = self.conn.execute(
                "SELECT * FROM telegram_questions WHERE attention_id=? AND question_version=?",
                (attention_id, question_version),
            ).fetchone()
            if question is None or question["state"] != "OPEN":
                self.event("RESPONSE_REJECTED_ALREADY_ANSWERED", update_id=update_id,
                           subject_id=attention_id)
                return "REJECTED_ALREADY_ANSWERED"
            constraints = json.loads(question["constraints_json"])
            allowed = constraints.get("choices")
            if isinstance(allowed, list) and text not in allowed:
                return "INVALID_RESPONSE"
            response_id = hashlib.sha256(f"{attention_id}\0{question_version}\0{update_id}".encode()).hexdigest()
            self.conn.execute(
                "INSERT INTO telegram_responses VALUES(?,?,?,?,?,?,?)",
                (response_id, attention_id, question_version, update_id, text, "ACCEPTED", now),
            )
            changed = self.conn.execute(
                "UPDATE telegram_questions SET state='ANSWERED',selected_response_id=?,updated_at=? "
                "WHERE attention_id=? AND question_version=? AND state='OPEN'",
                (response_id, now, attention_id, question_version),
            ).rowcount
            if changed != 1:
                raise RuntimeError("question response arbitration conflict")
            decision_id = hashlib.sha256(f"USER_DECISION\0{response_id}".encode()).hexdigest()
            decision = {
                "provenance": "USER", "transport": "TELEGRAM",
                "authority": "INPUT_ONLY_NON_AUTHORITATIVE", "attention_id": attention_id,
                "question_version": question_version, "response": text,
            }
            self.conn.execute(
                "INSERT INTO telegram_user_decisions VALUES(?,?,?,?,?,NULL)",
                (decision_id, response_id, question["task_id"], _canonical(decision), now),
            )
            self.event("USER_DECISION_CREATED", update_id=update_id, subject_id=decision_id,
                       detail={"task_id": question["task_id"]})
        return "ACCEPTED"

    def cancel_response(self, attention_id: str, update_id: int) -> str:
        with self.transaction():
            row = self.conn.execute(
                "SELECT r.response_id,r.state,d.consumed_at FROM telegram_responses r "
                "JOIN telegram_user_decisions d USING(response_id) WHERE r.attention_id=? "
                "ORDER BY r.created_at DESC LIMIT 1", (attention_id,),
            ).fetchone()
            if row is None:
                return "NOT_FOUND"
            if row["consumed_at"] is not None:
                self.event("RESPONSE_CANCEL_REJECTED_CONSUMED", update_id=update_id,
                           subject_id=row["response_id"])
                return "ALREADY_CONSUMED"
            self.conn.execute(
                "UPDATE telegram_responses SET state='CANCEL_REQUESTED' WHERE response_id=?",
                (row["response_id"],),
            )
            self.event("RESPONSE_CANCEL_REQUESTED", update_id=update_id,
                       subject_id=row["response_id"])
        return "CANCEL_REQUESTED"

    def _confirmation_state(self, action: str, subject_id: str | None) -> str:
        state: dict[str, Any] = {"control_mode": self.state()["control_mode"]}
        if action in {"HOLD", "RELEASE"}:
            row = self.conn.execute(
                "SELECT state,source_update_id,created_at,released_at FROM telegram_holds "
                "WHERE task_id=?", (subject_id,),
            ).fetchone()
            state["subject_hold"] = "MISSING" if row is None else {
                "state": row["state"], "source_update_id": row["source_update_id"],
                "created_at": row["created_at"], "released_at": row["released_at"],
            }
        return _canonical(state)

    def create_confirmation(self, *, update_id: int, action: str, subject_id: str | None,
                            now_epoch: float, ttl_seconds: int) -> str:
        token = hashlib.sha256(f"{update_id}\0{action}\0{subject_id or ''}\0{uuid.uuid4()}".encode()).hexdigest()[:32]
        expected_state = self._confirmation_state(action, subject_id)
        self.conn.execute(
            "INSERT INTO telegram_confirmations VALUES(?,?,?,?,?,?,?,?,NULL)",
            (token, update_id, action, subject_id, expected_state, now_epoch + ttl_seconds,
             "PENDING", utc_now()),
        )
        self.event("CONTROL_CONFIRMATION_REQUESTED", update_id=update_id, subject_id=subject_id,
                   detail={"action": action})
        return token

    def apply_confirmation(self, token: str, *, update_id: int, now_epoch: float,
                           resume_health_ok: bool) -> str:
        with self.transaction():
            row = self.conn.execute(
                "SELECT * FROM telegram_confirmations WHERE token=?", (token,),
            ).fetchone()
            if row is None or row["state"] != "PENDING" or float(row["expires_at"]) < now_epoch:
                return "INVALID_OR_EXPIRED_CONFIRMATION"
            action, subject = row["action"], row["subject_id"]
            if self._confirmation_state(action, subject) != row["expected_state"]:
                return "STATE_CHANGED"
            if action == "RESUME":
                if not resume_health_ok:
                    return "RESUME_HEALTH_CHECK_FAILED"
                self.conn.execute("UPDATE telegram_gateway_state SET control_mode='NORMAL' WHERE singleton=1")
            elif action in {"AI_PAUSED", "DRAIN", "QUIESCED", "SAFE"}:
                self.conn.execute("UPDATE telegram_gateway_state SET control_mode=? WHERE singleton=1", (action,))
            elif action == "MUTE":
                self.conn.execute("UPDATE telegram_gateway_state SET muted_until=? WHERE singleton=1", (now_epoch + float(subject or 0),))
            elif action == "UNMUTE":
                self.conn.execute("UPDATE telegram_gateway_state SET muted_until=NULL WHERE singleton=1")
            elif action == "HOLD" and subject:
                self.conn.execute(
                    "INSERT INTO telegram_holds VALUES(?, 'ACTIVE', ?, ?, NULL) "
                    "ON CONFLICT(task_id) DO UPDATE SET state='ACTIVE',source_update_id=excluded.source_update_id,created_at=excluded.created_at,released_at=NULL",
                    (subject, update_id, utc_now()),
                )
            elif action == "RELEASE" and subject:
                self.conn.execute(
                    "UPDATE telegram_holds SET state='RELEASED',released_at=? WHERE task_id=? AND state='ACTIVE'",
                    (utc_now(), subject),
                )
            else:
                return "UNSUPPORTED_ACTION"
            self.conn.execute(
                "UPDATE telegram_confirmations SET state='APPLIED',used_at=? WHERE token=?",
                (utc_now(), token),
            )
            self.event("USER_OPERATIONAL_CONTROL_APPLIED", update_id=update_id,
                       subject_id=subject, detail={"action": action, "provenance": "USER"})
        return "APPLIED"


class TelegramGateway:
    def __init__(self, cfg: dict[str, Any], conn: sqlite3.Connection,
                 transport: TelegramTransport, secrets: TelegramSecrets,
                 *, clock: Any = time.time):
        self.cfg = cfg
        self.conn = conn
        self.store = TelegramStore(conn)
        self.transport = transport
        self.secrets = secrets
        self.clock = clock
        self.owner = "telegram-" + str(uuid.uuid4())

    def _authorized(self, update: dict[str, Any]) -> tuple[bool, dict[str, Any] | None, str | None]:
        message = update.get("message")
        callback = update.get("callback_query")
        source = message if isinstance(message, dict) else callback.get("message") if isinstance(callback, dict) else None
        actor = message.get("from") if isinstance(message, dict) else callback.get("from") if isinstance(callback, dict) else None
        if not isinstance(source, dict) or not isinstance(actor, dict):
            return False, None, None
        chat = source.get("chat")
        if not isinstance(chat, dict) or chat.get("type") != "private":
            return False, None, None
        try:
            matches = int(actor.get("id")) == self.secrets.user_id and int(chat.get("id")) == self.secrets.chat_id
        except (TypeError, ValueError):
            matches = False
        if not matches or (isinstance(message, dict) and any(key in message for key in ("forward_origin", "forward_from", "forward_date"))):
            return False, None, None
        text = message.get("text") if isinstance(message, dict) else callback.get("data") if isinstance(callback, dict) else None
        return isinstance(text, str), source, text if isinstance(text, str) else None

    def _status(self) -> str:
        counts = {row["state"]: row["n"] for row in self.conn.execute(
            "SELECT state,COUNT(*) AS n FROM tasks GROUP BY state"
        )}
        controller = self.conn.execute(
            "SELECT state_json,updated_at FROM controller_state ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        state = json.loads(controller[0]) if controller else {}
        head = str(state.get("CANONICAL_HEAD") or "unknown")[:7]
        running = counts.get("RUNNING", 0)
        needs = counts.get("WAITING_USER", 0) + counts.get("WAITING_APPROVAL", 0)
        control = self.store.state()["control_mode"]
        return (f"Orch: {state.get('CURRENT_PHASE', 'UNKNOWN')} | control: {control}\n"
                f"HEAD: {head} | running: {running} | needs user: {needs}\n"
                f"AI lane: {state.get('AI_LANE_STATE', 'UNKNOWN')} | next: {_safe_text(state.get('NEXT_EXACT_ACTION'), 100)}")

    def _health(self) -> str:
        integrity = self.conn.execute("PRAGMA quick_check").fetchone()[0]
        controller = self.conn.execute(
            "SELECT state_json,updated_at FROM controller_state ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        state = json.loads(controller[0]) if controller else {}
        return (f"DB: {'ok' if integrity == 'ok' else 'degraded'} | "
                f"visibility: {state.get('AUTONOMY_VISIBILITY_STATE', 'UNKNOWN')} | "
                f"recovery: {state.get('RECOVERY_PROOF_STATE', 'UNKNOWN')} | "
                "Telegram: local gateway responding")

    def _attention(self) -> str:
        rows = self._current_attention_rows(limit=8)
        if not rows:
            return "No current user-attention items."
        return "\n".join(f"{row['task_id']}: {row['state']} — {_safe_text(row['reason'], 120)}" for row in rows)

    def _current_attention_rows(self, limit: int | None = None) -> list[sqlite3.Row]:
        rows = list(self.conn.execute(
            "SELECT task_id,envelope_hash,state,reason,updated_at FROM tasks "
            "WHERE state IN ('WAITING_USER','WAITING_APPROVAL','BLOCKED') "
            "ORDER BY updated_at DESC,task_id"
        ))
        current: list[sqlite3.Row] = []
        for row in rows:
            receipt_row = self.conn.execute(
                "SELECT receipt_json FROM authoring_receipts WHERE task_id=? "
                "ORDER BY rowid DESC LIMIT 1", (row["task_id"],),
            ).fetchone()
            try:
                receipt = json.loads(receipt_row[0]) if receipt_row else None
            except (TypeError, json.JSONDecodeError):
                receipt = None
            if receipt and is_historical_lifecycle_receipt(
                receipt, task_id=row["task_id"], envelope_hash=row["envelope_hash"],
            ):
                continue
            current.append(row)
            if limit is not None and len(current) >= limit:
                break
        return current

    def _last(self) -> str:
        row = self.conn.execute(
            "SELECT task_id,event_type,created_at FROM events "
            "WHERE event_type NOT IN ('POLL_UNCHANGED','DUPLICATE_DELIVERY') ORDER BY event_id DESC LIMIT 1"
        ).fetchone()
        return "No durable progress event." if row is None else f"{row['created_at']} {row['task_id'] or '-'} {row['event_type']}"

    def _task(self, task_id: str) -> str:
        if _SAFE_ID.fullmatch(task_id) is None:
            return "Invalid task id."
        row = self.conn.execute(
            "SELECT task_id,state,reason,attempt,updated_at FROM tasks WHERE task_id=?", (task_id,),
        ).fetchone()
        if row is None:
            return "Task not found."
        return f"{row['task_id']}\nstate: {row['state']} | attempt: {row['attempt']}\nupdated: {row['updated_at']}\n{_safe_text(row['reason'], 250)}"

    def _help(self) -> str:
        return ("Read-only: /status /health /attention /last /task <id>\n"
                "Questions: /respond <attention_id> <answer>, /cancel <attention_id>\n"
                "Confirmed operations: /pause_ai /drain /quiesce /safe /resume "
                "/mute <seconds> /unmute /hold <task_id> /release <task_id>\n"
                "Telegram is transport only: it cannot authorize science, holdout access, stages, Git, shell, or services.")

    def _resume_health_ok(self) -> bool:
        row = self.conn.execute(
            "SELECT state_json,updated_at FROM controller_state "
            "WHERE task_id='ORCH-M1B-RELIABILITY-REBUILD-001'"
        ).fetchone()
        try:
            if row is None or not isinstance(row["updated_at"], str):
                return False
            state = json.loads(row["state_json"])
            observed = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
            if not isinstance(state, dict) or observed.tzinfo is None or observed.utcoffset() is None:
                return False
            age = float(self.clock()) - observed.timestamp()
            stale_after = int(self.cfg["telegram"]["resume_observation_stale_after_seconds"])
        except (TypeError, ValueError, json.JSONDecodeError, OverflowError):
            return False
        if age < 0 or age > stale_after:
            return False
        blockers = state.get("HARD_BLOCKERS")
        return bool(
            state.get("RECOVERY_PROOF_STATE") == "PROVEN"
            and state.get("AUTONOMY_VISIBILITY_STATE") == "AUTONOMY_VISIBILITY_OK"
            and isinstance(blockers, list) and not blockers
        )

    def _confirmation(self, update_id: int, command: str, args: list[str]) -> tuple[str, dict[str, Any]]:
        action, subject = {
            "/pause_ai": ("AI_PAUSED", None), "/drain": ("DRAIN", None),
            "/quiesce": ("QUIESCED", None), "/safe": ("SAFE", None),
            "/resume": ("RESUME", None), "/unmute": ("UNMUTE", None),
        }.get(command, ("", None))
        if command == "/mute":
            if len(args) != 1 or not args[0].isdigit() or not 60 <= int(args[0]) <= 86400:
                return "Usage: /mute <60..86400 seconds>", {}
            action, subject = "MUTE", args[0]
        if command in {"/hold", "/release"}:
            if len(args) != 1 or _SAFE_ID.fullmatch(args[0]) is None:
                return f"Usage: {command} <task_id>", {}
            action, subject = command[1:].upper(), args[0]
        if not action:
            return "Unsupported operation.", {}
        token = self.store.create_confirmation(
            update_id=update_id, action=action, subject_id=subject,
            now_epoch=float(self.clock()),
            ttl_seconds=int(self.cfg["telegram"]["confirmation_ttl_seconds"]),
        )
        return (f"Confirm {action}. This changes only orchestrator operational control; it grants no scientific authority.",
                {"inline_keyboard": [[{"text": "Confirm", "callback_data": f"confirm:{token}"},
                                      {"text": "Cancel", "callback_data": f"reject:{token}"}]]})

    def _dispatch_command(self, update_id: int, text: str) -> tuple[str, dict[str, Any] | None]:
        if len(text) > 800 or not text.startswith("/"):
            return "Only exact allowlisted commands are accepted. Use /help.", None
        parts = text.strip().split(maxsplit=2)
        command = parts[0].split("@", 1)[0]
        args = parts[1:]
        if command == "/help" or command == "/start":
            return self._help(), None
        if command == "/status":
            return self._status(), None
        if command == "/health":
            return self._health(), None
        if command in {"/attention", "/waiting"}:
            return self._attention(), None
        if command == "/last":
            return self._last(), None
        if command == "/task":
            return self._task(args[0]) if len(args) == 1 else "Usage: /task <id>", None
        if command == "/respond":
            if len(parts) != 3 or _SAFE_ID.fullmatch(parts[1]) is None:
                return "Usage: /respond <attention_id> <answer>", None
            outcome = self.store.accept_response(attention_id=parts[1], update_id=update_id, text=parts[2])
            return f"Response: {outcome}. It is durable USER input, not scientific approval.", None
        if command == "/cancel":
            if len(args) != 1 or _SAFE_ID.fullmatch(args[0]) is None:
                return "Usage: /cancel <attention_id>", None
            return f"Cancellation: {self.store.cancel_response(args[0], update_id)}.", None
        if command in CONTROL_COMMANDS:
            message, markup = self._confirmation(update_id, command, args)
            return message, markup or None
        return "Command not allowed. Use /help.", None

    def process_update(self, update: dict[str, Any]) -> str:
        update_id = update.get("update_id")
        if isinstance(update_id, bool) or not isinstance(update_id, int) or update_id < 0:
            return "invalid"
        payload_hash = _digest(update)
        observed = self.store.record_update(update_id, payload_hash)
        if observed == "duplicate":
            self.store.update_offset(update_id + 1)
            return "duplicate"
        if observed == "conflict":
            self.store.event("UPDATE_ID_CONFLICT", update_id=update_id)
            self.store.update_offset(update_id + 1)
            return "conflict"
        authorized, _, text = self._authorized(update)
        if not authorized or text is None:
            self.store.finish_update(update_id, "REJECTED_UNAUTHORIZED")
            self.store.event("UNAUTHORIZED_UPDATE_REJECTED", update_id=update_id)
            self.store.update_offset(update_id + 1)
            return "unauthorized"
        if text.startswith("confirm:"):
            outcome = self.store.apply_confirmation(
                text.partition(":")[2], update_id=update_id,
                now_epoch=float(self.clock()), resume_health_ok=self._resume_health_ok(),
            )
            reply, markup = f"Confirmation: {outcome}.", None
        elif text.startswith("reject:"):
            self.conn.execute(
                "UPDATE telegram_confirmations SET state='REJECTED',used_at=? WHERE token=? AND state='PENDING'",
                (utc_now(), text.partition(":")[2]),
            )
            reply, markup = "Operation cancelled.", None
        else:
            reply, markup = self._dispatch_command(update_id, text)
        self.store.finish_update(update_id, "PROCESSED")
        self.store.update_offset(update_id + 1)
        self.store.enqueue_projection(
            attention_id=f"reply-{update_id}", source_event_id=f"update-{update_id}",
            task_id=None, kind="HUMAN_ACTION_REQUIRED",
            body={"reason_code": "TELEGRAM_COMMAND_REPLY", "safe_context": reply,
                  "requested_response": _canonical(markup) if markup else "",
                  "consequence_of_no_action": "none", "review_state": "OPERATIONAL"},
        )
        return "processed"

    def sync_attention(self) -> int:
        count = 0
        rows = reversed(self._current_attention_rows())
        for row in rows:
            reason_code = "HUMAN_ACTION_REQUIRED" if row["state"] != "BLOCKED" else "PROJECT_STALLED"
            outcome = self.store.enqueue_projection(
                attention_id=f"task-{row['task_id']}",
                source_event_id=f"task-state-{row['task_id']}-{row['updated_at']}",
                task_id=row["task_id"], kind=reason_code,
                body={"reason_code": row["state"],
                      "safe_context": _safe_text(row["reason"], 300),
                      "requested_response": "Use /task for status; answer only an explicit open question.",
                      "consequence_of_no_action": "Task remains waiting.",
                      "review_state": "OPERATIONAL", "created_at": row["updated_at"]},
                major_milestones=bool(self.cfg["telegram"]["notify_major_milestones"]),
            )
            if outcome == "enqueued":
                count += 1
                if row["state"] == "WAITING_USER":
                    self.store.open_question(attention_id=f"task-{row['task_id']}", task_id=row["task_id"])
        return count

    def _message_text(self, delivery: sqlite3.Row) -> tuple[str, dict[str, Any] | None]:
        body = json.loads(delivery["body_json"])
        marker = delivery["delivery_id"][:10]
        text = (f"[{body['reason_code']}] {body['task_id'] or 'Orchestrator'}\n"
                f"{body['safe_context']}\n{body['requested_response']}\n"
                f"ref:{marker} (duplicate copies share this ref)")
        markup = None
        if body.get("reason_code") == "TELEGRAM_COMMAND_REPLY" and body.get("requested_response", "").startswith("{"):
            try:
                markup = json.loads(body["requested_response"])
                text = body["safe_context"] + f"\nref:{marker}"
            except json.JSONDecodeError:
                pass
        return text[:3500], markup

    def deliver_once(self) -> str:
        now = float(self.clock())
        state = self.store.state()
        if state["muted_until"] is not None and now < float(state["muted_until"]):
            urgent = self.conn.execute(
                "SELECT 1 FROM telegram_deliveries d JOIN telegram_projections p USING(projection_id) "
                "WHERE d.state IN ('READY','RETRY_WAIT','SEND_OUTCOME_UNKNOWN') "
                "AND p.kind IN ('SCIENTIFIC_DECISION_REQUIRED','RECOVERY_FAILED') LIMIT 1"
            ).fetchone()
            if urgent is None:
                return "muted"
        delivery = self.store.claim_delivery(
            self.owner, now, int(self.cfg["telegram"]["delivery_lease_seconds"]),
        )
        if delivery is None:
            return "idle"
        text, markup = self._message_text(delivery)
        try:
            message_id = self.transport.send_message(text=text, reply_markup=markup)
        except (SendOutcomeUnknown, TimeoutError, ConnectionError) as exc:
            self.store.send_unknown(
                delivery, type(exc).__name__, now,
                int(self.cfg["telegram"]["max_delivery_attempts"]),
            )
            return "SEND_OUTCOME_UNKNOWN"
        except Exception as exc:
            self.store.retry(delivery, type(exc).__name__, now,
                             int(self.cfg["telegram"]["max_delivery_attempts"]))
            return "retry"
        self.store.sent(delivery, message_id)
        return "sent"

    def cycle(self) -> dict[str, Any]:
        now = float(self.clock())
        expired = self.store.reconcile_expired_claims(now)
        projected = self.sync_attention()
        state = self.store.state()
        outcomes: list[str] = []
        try:
            updates = self.transport.get_updates(
                offset=int(state["update_offset"]),
                timeout_seconds=int(self.cfg["telegram"]["long_poll_seconds"]),
            )
            for update in updates:
                outcomes.append(self.process_update(update))
            delivery = self.deliver_once()
            self.store.set_observation("HEALTHY", "long polling and durable gateway loop completed")
            observation = {"state": "HEALTHY", "detail": "Gateway loop completed", "observed_at": utc_now()}
        except Exception as exc:
            self.store.set_observation("DEGRADED", "gateway loop failed safely", error_text=type(exc).__name__)
            observation = {"state": "DEGRADED", "detail": f"Gateway loop: {type(exc).__name__}", "observed_at": utc_now()}
            delivery = "not_attempted"
        M1bStore(self.conn, self.cfg).checkpoint(TELEGRAM_GATEWAY=observation)
        return {"expired_claims": expired, "projected": projected,
                "updates": outcomes, "delivery": delivery, "observation": observation}

    def run_forever(self) -> None:
        while True:
            self.cycle()
            time.sleep(max(1, int(self.cfg["telegram"]["loop_delay_seconds"])))
