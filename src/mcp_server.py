from __future__ import annotations

from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from .amazon_scraper import scrape_product
from .config import PLAYWRIGHT_HEADLESS
from .database import (
    add_product,
    consume_pending_action,
    create_pending_action,
    force_check_now,
    init_db,
    list_products,
    set_active,
)


mcp = FastMCP("deal-watcher")


@mcp.tool()
def preview_amazon_tracking(
    url: str,
    target_price: float | None = None,
    alert_on_any_drop: bool = True,
) -> dict:
    """
    افحص رابط Amazon.sa واعرض خطة المراقبة فقط.
    لا يحفظ المنتج. يجب عرض النتيجة للمستخدم وطلب موافقته،
    ثم استدعاء confirm_amazon_tracking باستخدام approval_token.
    """
    init_db()
    snapshot = scrape_product(url, headless=PLAYWRIGHT_HEADLESS)
    token = uuid4().hex[:10].upper()

    payload = {
        "url": snapshot.url,
        "asin": snapshot.asin,
        "marketplace": snapshot.marketplace,
        "title": snapshot.title,
        "price": snapshot.price,
        "currency": snapshot.currency,
        "target_price": target_price,
        "alert_on_any_drop": alert_on_any_drop,
    }
    create_pending_action(token, "add_product", payload)

    return {
        "status": "awaiting_human_approval",
        "approval_token": token,
        "expires_in_minutes": 15,
        "product": {
            "title": snapshot.title,
            "current_price": snapshot.price,
            "currency": snapshot.currency,
            "url": snapshot.url,
            "asin": snapshot.asin,
        },
        "tracking_plan": {
            "target_price": target_price,
            "alert_on_any_drop": alert_on_any_drop,
        },
        "instruction": "اعرض الخطة للمستخدم ولا تستدعِ التأكيد حتى يقول موافق بوضوح.",
    }


@mcp.tool()
def confirm_amazon_tracking(approval_token: str) -> dict:
    """
    حفظ المنتج بعد موافقة بشرية صريحة.
    لا تستخدمه إلا بعد أن يوافق المستخدم على الخطة المعروضة.
    """
    init_db()
    payload = consume_pending_action(
        approval_token.strip().upper(),
        "add_product",
    )
    product_id = add_product(**payload)
    return {
        "status": "tracking_started",
        "product_id": product_id,
        "title": payload["title"],
        "current_price": payload["price"],
        "currency": payload["currency"],
    }


@mcp.tool()
def list_tracked_products() -> list[dict]:
    """عرض المنتجات المحفوظة وحالتها وآخر سعر وموعد الفحص القادم."""
    init_db()
    return list_products()


@mcp.tool()
def pause_tracked_product(product_id: int) -> dict:
    """إيقاف فحص منتج مؤقتًا. يجب أخذ موافقة المستخدم قبل الاستدعاء."""
    return {"success": set_active(product_id, False), "product_id": product_id}


@mcp.tool()
def resume_tracked_product(product_id: int) -> dict:
    """استئناف فحص منتج متوقف. يجب أخذ موافقة المستخدم قبل الاستدعاء."""
    return {"success": set_active(product_id, True), "product_id": product_id}


@mcp.tool()
def check_product_now(product_id: int) -> dict:
    """تحديد منتج ليتم فحصه في دورة الـWorker القادمة."""
    return {"success": force_check_now(product_id), "product_id": product_id}


if __name__ == "__main__":
    init_db()
    mcp.run()
