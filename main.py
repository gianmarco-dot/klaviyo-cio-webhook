from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import os
import requests
import traceback
from dateutil import parser
from datetime import datetime, timezone

app = FastAPI()

# =========================
# ENV VARS
# =========================
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY")
CIO_SITE_ID = os.getenv("CIO_SITE_ID")
CIO_API_KEY = os.getenv("CIO_API_KEY")
MOCK_MODE = os.getenv("MOCK_MODE", "true") == "true"

# =========================
# KLAVIYO HELPERS
# =========================
def get_klaviyo_last_active(email: str):
    """
    Uses Klaviyo official profile-search endpoint
    Returns last_active (string) or None
    """
    url = "https://a.klaviyo.com/api/profile-search/"
    headers = {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = {
        "data": {
            "type": "profile-search",
            "attributes": {
                "email": email
            }
        }
    }

    r = requests.post(url, headers=headers, json=payload, timeout=10)
    r.raise_for_status()

    data = r.json().get("data", [])
    if not data:
        return None

    profile = data[0]
    return profile.get("attributes", {}).get("last_active")


# =========================
# CUSTOMER.IO HELPERS
# =========================
def update_customer_io(customer_id: str, attributes: dict):
    url = f"https://track.customer.io/api/v1/customers/{customer_id}"
    auth = (CIO_SITE_ID, CIO_API_KEY)

    r = requests.put(
        url,
        auth=auth,
        json=attributes,
        timeout=10,
    )
    r.raise_for_status()


# =========================
# WEBHOOK
# =========================
@app.post("/webhook")
async def webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    try:
        # -------- AUTH --------
        if not WEBHOOK_SECRET:
            raise HTTPException(status_code=500, detail="Webhook secret not configured")

        if x_webhook_secret != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # -------- PAYLOAD --------
        payload = await request.json()
        customer_id = payload.get("customer_id")
        email = payload.get("email")

        if not customer_id or not email:
            raise HTTPException(
                status_code=400,
                detail="customer_id and email are required"
            )

        now_iso = datetime.now(timezone.utc).isoformat()

        # -------- MOCK MODE --------
        if MOCK_MODE:
            return {
                "status": "ok",
                "mode": "mock",
                "customer_id": customer_id,
                "email": email,
            }

        # -------- KLAVIYO LOOKUP --------
        last_active_raw = get_klaviyo_last_active(email)

        if not last_active_raw:
            update_customer_io(customer_id, {
                "klaviyo_sync_status": "not_found",
                "klaviyo_last_synced_at": now_iso,
            })

            return {
                "status": "ok",
                "message": "No Klaviyo last_active found",
                "customer_id": customer_id,
            }

        # -------- NORMALIZE DATE --------
        last_active_iso = parser.parse(last_active_raw).isoformat()

        # -------- UPDATE CUSTOMER.IO --------
        update_customer_io(customer_id, {
            "last_active_klaviyo": last_active_iso,
            "klaviyo_sync_status": "success",
            "klaviyo_last_synced_at": now_iso,
        })

        return {
            "status": "ok",
            "customer_id": customer_id,
            "last_active": last_active_iso,
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        print("🔥 UNHANDLED ERROR")
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e),
            },
        )


# =========================
# HEALTHCHECK
# =========================
@app.get("/")
def health():
    return {"status": "ok"}

