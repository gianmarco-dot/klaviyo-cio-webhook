from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import os
import requests
import traceback
from dateutil import parser

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY")
CIO_SITE_ID = os.getenv("CIO_SITE_ID")
CIO_API_KEY = os.getenv("CIO_API_KEY")
MOCK_MODE = os.getenv("MOCK_MODE", "true") == "true"


def get_klaviyo_last_active(email: str):
    url = "https://a.klaviyo.com/api/profiles/"
    headers = {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
        "Accept": "application/json"
    }
    params = {
        "filter": f"equals(email,\"{email}\")"
    }

    r = requests.get(url, headers=headers, params=params, timeout=10)
    r.raise_for_status()

    data = r.json().get("data", [])
    if not data:
        return None

    profile = data[0]
    last_active = profile["attributes"].get("last_active")
    return last_active


def update_customer_io(customer_id: str, last_active_iso: str):
    url = f"https://track.customer.io/api/v1/customers/{customer_id}"
    auth = (CIO_SITE_ID, CIO_API_KEY)
    payload = {
        "last_active_klaviyo": last_active_iso
    }

    r = requests.put(url, auth=auth, json=payload, timeout=10)
    r.raise_for_status()


@app.post("/webhook")
async def webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    try:
        # 1. Auth
        if not WEBHOOK_SECRET:
            raise HTTPException(status_code=500, detail="Webhook secret not configured")

        if x_webhook_secret != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")

        payload = await request.json()
        customer_id = payload.get("customer_id")
        email = payload.get("email")

        if not customer_id or not email:
            raise HTTPException(
                status_code=400,
                detail="customer_id and email are required"
            )

        # 2. MOCK
        if MOCK_MODE:
            return {
                "status": "ok",
                "mode": "mock",
                "customer_id": customer_id,
                "email": email
            }

        # 3. Klaviyo lookup
        last_active_raw = get_klaviyo_last_active(email)

        if not last_active_raw:
            return {
                "status": "ok",
                "message": "No Klaviyo last_active found",
                "customer_id": customer_id
            }

        # 4. Normalize date → ISO 8601
        last_active_iso = parser.parse(last_active_raw).isoformat()

        # 5. Update Customer.io
        update_customer_io(customer_id, last_active_iso)

        return {
            "status": "ok",
            "customer_id": customer_id,
            "last_active": last_active_iso
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

