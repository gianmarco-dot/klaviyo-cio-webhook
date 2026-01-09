from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import os
import requests
import traceback

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY")

KLAVIYO_BASE_URL = "https://a.klaviyo.com/api/profiles/"
KLAVIYO_REVISION = "2024-02-15"


@app.post("/webhook")
async def webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    try:
        # 1️⃣ Auth
        if not WEBHOOK_SECRET:
            raise HTTPException(status_code=500, detail="Webhook secret not configured")

        if x_webhook_secret != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # 2️⃣ Parse body
        payload = await request.json()
        customer_id = payload.get("customer_id")
        email = payload.get("email")

        if not customer_id or not email:
            raise HTTPException(
                status_code=400,
                detail="customer_id and email are required"
            )

        # 3️⃣ Call Klaviyo — lookup by email
        headers = {
            "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
            "Accept": "application/json",
            "Revision": KLAVIYO_REVISION
        }

        params = {
            "filter": f'equals(email,"{email}")'
        }

        response = requests.get(
            KLAVIYO_BASE_URL,
            headers=headers,
            params=params,
            timeout=10
        )

        response.raise_for_status()
        data = response.json().get("data", [])

        # 4️⃣ Handle no profile found
        if not data:
            return {
                "status": "ok",
                "customer_id": customer_id,
                "email": email,
                "klaviyo_id": None,
                "last_active": None
            }

        # 5️⃣ Extract Klaviyo profile
        profile = data[0]
        klaviyo_id = profile.get("id")
        attributes = profile.get("attributes", {})
        last_active = attributes.get("last_active")

        # 6️⃣ Return (Customer.io update comes later)
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


@app.get("/")
def health():
    return {"status": "ok"}

