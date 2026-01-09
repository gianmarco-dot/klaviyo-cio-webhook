import os
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Header, HTTPException
from pydantic import BaseModel

# =========================
# ENV VARS
# =========================
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY")
CIO_SITE_ID = os.getenv("CIO_SITE_ID")
CIO_API_KEY = os.getenv("CIO_API_KEY")

# =========================
# FASTAPI
# =========================
app = FastAPI()


# =========================
# MODELS
# =========================
class WebhookPayload(BaseModel):
    customer_id: str
    email: str
    klaviyo_id: str | None = None


# =========================
# HELPERS
# =========================
def is_mock_mode() -> bool:
    return KLAVIYO_API_KEY in (None, "", "test")


def get_klaviyo_profile_by_email(email: str) -> dict | None:
    url = "https://a.klaviyo.com/api/profiles/"
    headers = {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
        "revision": "2024-10-15",
    }
    params = {
        "filter": f"equals(email,'{email}')"
    }

    r = requests.get(url, headers=headers, params=params, timeout=10)
    r.raise_for_status()

    data = r.json().get("data", [])
    return data[0] if data else None


def get_klaviyo_profile_by_id(klaviyo_id: str) -> dict | None:
    url = f"https://a.klaviyo.com/api/profiles/{klaviyo_id}"
    headers = {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
        "revision": "2024-10-15",
    }

    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json().get("data")


def update_customerio(customer_id: str, attributes: dict):
    url = f"https://track.customer.io/api/v1/customers/{customer_id}"
    r = requests.put(
        url,
        auth=(CIO_SITE_ID, CIO_API_KEY),
        json={"attributes": attributes},
        timeout=10,
    )
    r.raise_for_status()


# =========================
# WEBHOOK
# =========================
@app.post("/webhook")
async def webhook(
    payload: WebhookPayload,
    request: Request,
    x_webhook_secret: str = Header(None),
):
    # ---- Auth ----
    if not WEBHOOK_SECRET or x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    customer_id = payload.customer_id
    email = payload.email
    klaviyo_id = payload.klaviyo_id

    now_iso = datetime.now(timezone.utc).isoformat()

    # =========================
    # MOCK MODE (LOCAL / TEST)
    # =========================
    if is_mock_mode():
        update_customerio(customer_id, {
            "klaviyo_sync_status": "mock_success",
            "klaviyo_last_active": now_iso,
            "klaviyo_last_synced_at": now_iso,
        })

        return {
            "status": "ok",
            "mode": "mock"
        }

    # =========================
    # REAL KLAVIYO MODE
    # =========================
    try:
        profile = None

        if klaviyo_id:
            profile = get_klaviyo_profile_by_id(klaviyo_id)

        if not profile:
            profile = get_klaviyo_profile_by_email(email)

        if not profile:
            update_customerio(customer_id, {
                "klaviyo_sync_status": "not_found",
                "klaviyo_last_synced_at": now_iso,
            })

            return {
                "status": "ok",
                "reason": "profile_not_found"
            }

        last_active = (
            profile
            .get("attributes", {})
            .get("last_active")
        )

        update_customerio(customer_id, {
            "klaviyo_sync_status": "success",
            "klaviyo_last_active": last_active,
            "klaviyo_last_synced_at": now_iso,
        })

        return {
            "status": "ok",
            "mode": "production"
        }

    # =========================
    # ERROR SAFETY NET
    # =========================
    except Exception as e:
        update_customerio(customer_id, {
            "klaviyo_sync_status": "error_klaviyo_api",
            "klaviyo_last_synced_at": now_iso,
            "klaviyo_error_message": str(e)[:255],
        })

        return {
            "status": "error",
            "reason": "klaviyo_api_error"
        }

