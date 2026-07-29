from __future__ import annotations

import logging
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

from .amazon_scraper import ScrapeError, scrape_product
from .config import (
    CHECK_INTERVAL_HOURS,
    FAILURE_RETRY_MINUTES,
    LOG_DIR,
    PLAYWRIGHT_HEADLESS,
    WORKER_POLL_SECONDS,
)
from .database import (
    get_due_products,
    init_db,
    mark_check_failure,
    mark_check_success,
    utc_now,
)
from .telegram_notify import NotificationError, send_telegram_message


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "worker.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


class SingleInstance:
    """A simple lock that prevents multiple workers on Windows."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+", encoding="utf-8")
        if os.name == "nt":
            import msvcrt

            try:
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Another worker instance is already running.") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle:
            if os.name == "nt":
                import msvcrt

                try:
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            self.handle.close()


def should_alert(product: dict, new_price: float) -> tuple[bool, str]:
    old_price = float(product["last_price"])
    target = product["target_price"]
    last_alerted = product["last_alerted_price"]

    reasons: list[str] = []

    if target is not None and new_price <= float(target):
        if last_alerted is None or new_price < float(last_alerted):
            reasons.append(f"reached the target price ({float(target):.2f} SAR)")

    if bool(product["alert_on_any_drop"]) and new_price < old_price:
        if last_alerted is None or new_price < float(last_alerted):
            reasons.append("price is below the last recorded price")

    return bool(reasons), ", ".join(reasons)


def build_alert(product: dict, new_price: float, reason: str) -> str:
    old_price = float(product["last_price"])
    difference = old_price - new_price
    percentage = (difference / old_price * 100) if old_price else 0

    return (
        "A tracked product price dropped!\n\n"
        f"Product: {product['title']}\n"
        f"Previous price: {old_price:.2f} SAR\n"
        f"Current price: {new_price:.2f} SAR\n"
        f"Drop: {difference:.2f} SAR ({percentage:.1f}%)\n"
        f"Reason: {reason}\n\n"
        f"URL: {product['url']}"
    )


def check_one(product: dict) -> None:
    product_id = int(product["id"])
    logging.info("Checking product #%s: %s", product_id, product["title"])

    try:
        snapshot = scrape_product(
            product["url"],
            headless=PLAYWRIGHT_HEADLESS,
        )

        alert, reason = should_alert(product, snapshot.price)
        alerted_price = None

        if alert:
            message = build_alert(product, snapshot.price, reason)
            try:
                send_telegram_message(message)
                alerted_price = snapshot.price
                logging.info("Alert sent for product #%s", product_id)
            except NotificationError:
                logging.exception("Failed to send alert for product #%s", product_id)

        mark_check_success(
            product_id,
            snapshot.price,
            utc_now() + timedelta(hours=CHECK_INTERVAL_HOURS),
            alerted_price=alerted_price,
        )
        logging.info(
            "Product #%s check succeeded. Price: %.2f SAR",
            product_id,
            snapshot.price,
        )

    except (ScrapeError, ValueError, RuntimeError) as exc:
        logging.warning("Product #%s check failed: %s", product_id, exc)
        mark_check_failure(
            product_id,
            str(exc),
            utc_now() + timedelta(minutes=FAILURE_RETRY_MINUTES),
        )
    except Exception as exc:
        logging.exception("Unexpected error while checking product #%s", product_id)
        mark_check_failure(
            product_id,
            f"Unexpected error: {exc}",
            utc_now() + timedelta(minutes=FAILURE_RETRY_MINUTES),
        )


def main() -> None:
    configure_logging()
    init_db()

    lock_path = LOG_DIR / "worker.lock"
    try:
        with SingleInstance(lock_path):
            logging.info(
                "Price Tracker Worker started. Default interval: %s hours.",
                CHECK_INTERVAL_HOURS,
            )
            while True:
                due_products = get_due_products()
                if not due_products:
                    time.sleep(WORKER_POLL_SECONDS)
                    continue

                for product in due_products:
                    check_one(product)
    except RuntimeError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        logging.info("Worker stopped manually.")


if __name__ == "__main__":
    main()
