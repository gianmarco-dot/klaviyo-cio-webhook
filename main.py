import os
from fastapi import FastAPI, Request, Header, HTTPException

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

@app.post("/webhook")
async def webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Secret not configured")

    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    print("Webhook received:", payload)

    return {
        "status": "ok",
        "received": payload
    }
