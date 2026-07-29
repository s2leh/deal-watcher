from __future__ import annotations

import argparse
import json
import sys
from uuid import uuid4

from .amazon_scraper import scrape_product
from .config import PLAYWRIGHT_HEADLESS
from .database import (
    add_product,
    create_pending_action,
    delete_product,
    force_check_now,
    init_db,
    list_products,
    set_active,
)


def command_init(_: argparse.Namespace) -> None:
    init_db()
    print("Database initialized: data/tracker.db")


def command_preview(args: argparse.Namespace) -> None:
    init_db()
    snapshot = scrape_product(args.url, headless=args.headless)
    token = uuid4().hex[:10].upper()

    payload = {
        "url": snapshot.url,
        "asin": snapshot.asin,
        "marketplace": snapshot.marketplace,
        "title": snapshot.title,
        "price": snapshot.price,
        "currency": snapshot.currency,
        "target_price": args.target,
        "alert_on_any_drop": args.any_drop,
    }
    create_pending_action(token, "add_product", payload)

    print("Product:", snapshot.title)
    print(f"Current price: {snapshot.price:.2f} {snapshot.currency}")
    print("Target price:", args.target if args.target is not None else "not set")
    print("Alert on any drop:", "yes" if args.any_drop else "no")
    print()
    print("Awaiting approval. Approval token:")
    print(token)
    print()
    print(f"To confirm: python -m src.cli confirm {token}")


def command_confirm(args: argparse.Namespace) -> None:
    from .database import consume_pending_action

    init_db()
    payload = consume_pending_action(args.token.upper(), "add_product")
    product_id = add_product(**payload)
    print(f"Product tracking started. Product ID: {product_id}")


def command_list(_: argparse.Namespace) -> None:
    init_db()
    products = list_products()
    if not products:
        print("No tracked products found.")
        return

    for product in products:
        state = "active" if product["active"] else "paused"
        target = (
            f"{float(product['target_price']):.2f}"
            if product["target_price"] is not None
            else "-"
        )
        print(
            f"#{product['id']} | {state} | {product['title']}\n"
            f"  Price: {float(product['last_price']):.2f} {product['currency']} "
            f"| Target: {target} | Next check: {product['next_check_at']}\n"
            f"  {product['url']}"
        )


def command_pause(args: argparse.Namespace) -> None:
    print("Product paused." if set_active(args.id, False) else "Product not found.")


def command_resume(args: argparse.Namespace) -> None:
    print("Product resumed." if set_active(args.id, True) else "Product not found.")


def command_delete(args: argparse.Namespace) -> None:
    print("Product deleted." if delete_product(args.id) else "Product not found.")


def command_check(args: argparse.Namespace) -> None:
    print(
        "Product will be checked during the next worker cycle."
        if force_check_now(args.id)
        else "Product not found."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Amazon.sa Deal Watcher")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.set_defaults(func=command_init)

    p_preview = sub.add_parser("preview")
    p_preview.add_argument("url")
    p_preview.add_argument("--target", type=float)
    p_preview.add_argument(
        "--any-drop",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    p_preview.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=PLAYWRIGHT_HEADLESS,
    )
    p_preview.set_defaults(func=command_preview)

    p_confirm = sub.add_parser("confirm")
    p_confirm.add_argument("token")
    p_confirm.set_defaults(func=command_confirm)

    p_list = sub.add_parser("list")
    p_list.set_defaults(func=command_list)

    for name, func in [
        ("pause", command_pause),
        ("resume", command_resume),
        ("delete", command_delete),
        ("check-now", command_check),
    ]:
        subparser = sub.add_parser(name)
        subparser.add_argument("id", type=int)
        subparser.set_defaults(func=func)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
