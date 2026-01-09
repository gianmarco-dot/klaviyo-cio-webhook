from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import os
import traceback

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

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

        # 2. Parse body safely
        payload = await request.json()

        customer_id = payload.get("customer_id")
        email = payload.get("email")

        if not customer_id or not email:
            raise HTTPException(
                status_code=400,
                detail="customer_id and email are required"
            )

        # 3. MOCK MODE (no external calls yet)
        return {
            "status": "ok",
            "mode": "mock",
            "customer_id": customer_id,
            "email": email
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        # 👇 ESTO ES CLAVE PARA EL 502
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

