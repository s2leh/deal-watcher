from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from .config import DATA_DIR, DB_PATH


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracked_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                asin TEXT,
                marketplace TEXT NOT NULL DEFAULT 'amazon.sa',
                title TEXT NOT NULL,
                currency TEXT NOT NULL DEFAULT 'SAR',
                initial_price REAL NOT NULL,
                last_price REAL NOT NULL,
                target_price REAL,
                alert_on_any_drop INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                last_checked_at TEXT,
                next_check_at TEXT NOT NULL,
                last_alerted_price REAL,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_products_due
            ON tracked_products(active, next_check_at);

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                price REAL NOT NULL,
                checked_at TEXT NOT NULL,
                FOREIGN KEY (product_id)
                    REFERENCES tracked_products(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS pending_actions (
                token TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            """
        )


def create_pending_action(
    token: str,
    action: str,
    payload: dict[str, Any],
    expires_minutes: int = 15,
) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO pending_actions
                (token, action, payload_json, status, created_at, expires_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (
                token,
                action,
                json.dumps(payload, ensure_ascii=False),
                iso(now),
                iso(now + timedelta(minutes=expires_minutes)),
            ),
        )


def consume_pending_action(token: str, expected_action: str) -> dict[str, Any]:
    now = iso()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM pending_actions
            WHERE token = ? AND action = ? AND status = 'pending'
            """,
            (token, expected_action),
        ).fetchone()

        if row is None:
            raise ValueError("The approval token does not exist or was already used.")

        if row["expires_at"] < now:
            conn.execute(
                "UPDATE pending_actions SET status = 'expired' WHERE token = ?",
                (token,),
            )
            raise ValueError("The approval token expired. Create a new preview.")

        conn.execute(
            "UPDATE pending_actions SET status = 'confirmed' WHERE token = ?",
            (token,),
        )
        return json.loads(row["payload_json"])


def add_product(
    *,
    url: str,
    asin: str | None,
    marketplace: str,
    title: str,
    price: float,
    currency: str,
    target_price: float | None,
    alert_on_any_drop: bool,
) -> int:
    now = utc_now()
    now_text = iso(now)
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tracked_products (
                url, asin, marketplace, title, currency,
                initial_price, last_price, target_price,
                alert_on_any_drop, active, last_checked_at,
                next_check_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (
                url,
                asin,
                marketplace,
                title,
                currency,
                price,
                price,
                target_price,
                1 if alert_on_any_drop else 0,
                now_text,
                now_text,
                now_text,
                now_text,
            ),
        )
        product_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO price_history(product_id, price, checked_at)
            VALUES (?, ?, ?)
            """,
            (product_id, price, now_text),
        )
        return product_id


def list_products(active_only: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM tracked_products"
    params: tuple[Any, ...] = ()
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY id DESC"

    with connect() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_product(product_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM tracked_products WHERE id = ?",
            (product_id,),
        ).fetchone()
        return dict(row) if row else None


def get_due_products(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tracked_products
            WHERE active = 1 AND next_check_at <= ?
            ORDER BY next_check_at ASC
            LIMIT ?
            """,
            (iso(), limit),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_check_success(
    product_id: int,
    new_price: float,
    next_check_at: datetime,
    alerted_price: float | None = None,
) -> None:
    checked_at = iso()
    with connect() as conn:
        conn.execute(
            """
            UPDATE tracked_products
            SET last_price = ?,
                last_checked_at = ?,
                next_check_at = ?,
                last_alerted_price = COALESCE(?, last_alerted_price),
                last_error = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                new_price,
                checked_at,
                iso(next_check_at),
                alerted_price,
                checked_at,
                product_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO price_history(product_id, price, checked_at)
            VALUES (?, ?, ?)
            """,
            (product_id, new_price, checked_at),
        )


def mark_check_failure(
    product_id: int,
    error: str,
    next_check_at: datetime,
) -> None:
    now_text = iso()
    with connect() as conn:
        conn.execute(
            """
            UPDATE tracked_products
            SET last_checked_at = ?,
                next_check_at = ?,
                last_error = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now_text, iso(next_check_at), error[:1000], now_text, product_id),
        )


def set_active(product_id: int, active: bool) -> bool:
    now_text = iso()
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE tracked_products
            SET active = ?, next_check_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (1 if active else 0, now_text, now_text, product_id),
        )
        return cursor.rowcount > 0


def delete_product(product_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM tracked_products WHERE id = ?",
            (product_id,),
        )
        return cursor.rowcount > 0


def force_check_now(product_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE tracked_products
            SET next_check_at = ?, active = 1, updated_at = ?
            WHERE id = ?
            """,
            (iso(), iso(), product_id),
        )
        return cursor.rowcount > 0
