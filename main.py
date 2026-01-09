from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import os
import requests
import traceback

app = FastAPI()

# =========================
# ENV VARS
# =========================
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY")

if not KLAVIYO_API_KEY:
    print("⚠️ KLAVIYO_API_KEY not set")

KlaviyoHeaders = {
    "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
    "Accept": "application/json",
    "Revision": "2024-02-15"
}

# =========================
# HEALTHCHECK
# =========================
@app.get("/")
def health():
    return {"status": "ok"}

# =========================
# WEBHOOK
# =========================
@app.post("/webhook")
async def webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    try:
        # ---- AUTH ----
        if not WEBHOOK_SECRET:
            raise HTTPException(status_code=500, detail="WEBHOOK_SECRET not configured")

        if x_webhook_secret != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # ---- BODY ----
        payload = await request.json()
        customer_id = payload.get("customer_id")
        email = payload.get("email")

        if not customer_id or not email:
            raise HTTPException(
                status_code=400,
                detail="customer_id and email are required"
            )

        # ---- 1. SEARCH PROFILE BY EMAIL ----
        search_url = (
            "https://a.klaviyo.com/api/profiles/"
            f"?filter=equals(email,\"{email}\")"
        )

        profile_resp = requests.get(search_url, headers=KlaviyoHeaders, timeout=10)
        profile_resp.raise_for_status()
        profile_data = profile_resp.json()

        if not profile_data.get("data"):
            raise HTTPException(
                status_code=404,
                detail="Klaviyo profile not found"
            )

        profile = profile_data["data"][0]
        klaviyo_id = profile["id"]
        attributes = profile["attributes"]

        # 🔑 ESTE ES EL CAMPO CORRECTO
        last_active = attributes.get("last_event_date")

        # ---- RESPONSE ----
        return {
            "status": "ok",
            "customer_id": customer_id,
            "email": email,
            "klaviyo_id": klaviyo_id,
            "last_active": last_active
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
                "message": str(e)
            }
        )

