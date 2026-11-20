from fastapi import FastAPI

from .config import get_settings
from .routers import core, engage, money

app = FastAPI(title="UPI Business Autopilot API", version="0.1.0",
              description="Sales-to-payment coordination for Indian merchants. Verified-ledger MVP.")
for r in (core.router, money.router, engage.router):
    app.include_router(r)


@app.get("/v1/health")
def health():
    return {"status": "ok", "demo_mode": get_settings().demo_mode}
