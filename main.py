import os
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# ===== ENV =====
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY")
CIO_SITE_ID = os.getenv("CIO_SITE_ID")
CIO_API_KEY = os.getenv("CIO_API_KEY")

KLAVIYO_REVISION = "2024-10-15"


# ===== MODELS =====
class Payload(BaseModel):
    customer_id: str
    email: str
    klaviyo_id: Optional[str] = None


# ===== HELPERS =====
def klaviyo_headers():
    return {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
        "Accept": "application/json",
        "revision": KLAVIYO_REVISION,
    }


def get_klaviyo_profile_by_id(klaviyo_id: str):
    url = f"https://a.klaviyo.com/api/profiles/{klaviyo_id}"
    r = requests.get(url, headers=klaviyo_headers(), timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("data")


def get_klaviyo_profile_by_email(email: str):
    url = "https://a.klaviyo.com/api/profiles/"
    params = {
        "filter": f"equals(email,'{email}')",
        "page[size]": 1,
    }
    r = requests.get(url, headers=klaviyo_headers(), params=params, timeout=20)
    r.raise_for_status()
    data = r.json().get("data", [])
    return data[0] if data else None


def update_customerio(customer_id: str, attributes: dict):
    url = f"https://track.customer.io/api/v1/customers/{customer_id}"
    payload = {"attributes": attributes}
    r = requests.put(url, json=payload, auth=(CIO_SITE_ID, CIO_API_KEY), timeout=20)
    r.raise_for_status()


# ===== WEBHOOK =====
@app.post("/webhook")
async def webhook(
    request: Request,
    payload: Payload,
    x_webhook_secret: str = Header(None),
):
    # Security
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not KLAVIYO_API_KEY or not CIO_API_KEY:
        raise HTTPException(status_code=500, detail="Missing API keys")

    customer_id = payload.customer_id
    email = payload.email
    klaviyo_id = payload.klaviyo_id

    # Resolve Klaviyo profile
    profile = None
    if klaviyo_id:
        profile = get_klaviyo_profile_by_id(klaviyo_id)

    if not profile:
        profile = get_klaviyo_profile_by_email(email)

    if not profile:
        update_customerio(customer_id, {
            "klaviyo_sync_status": "profile_not_found",
            "klaviyo_last_synced_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"status": "profile_not_found"}

    klaviyo_id = profile["id"]
    last_active = profile.get("attributes", {}).get("last_active_at")

    attrs = {
        "klaviyo_id": klaviyo_id,
        "klaviyo_last_synced_at": datetime.now(timezone.utc).isoformat(),
    }

    if last_active:
        attrs["klaviyo_last_active_at"] = last_active
        attrs["klaviyo_sync_status"] = "success"
    else:
        attrs["klaviyo_sync_status"] = "no_last_active"

    update_customerio(customer_id, attrs)

    return {"status": "ok"}
