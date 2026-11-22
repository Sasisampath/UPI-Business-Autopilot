from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import preflight
from .config import get_settings
from .routers import core, engage, money

@asynccontextmanager
async def lifespan(_: FastAPI):
    preflight.enforce(get_settings())  # refuse to serve a shared preview that is not locked down
    yield


app = FastAPI(title="UPI Business Autopilot API", version="0.1.0", lifespan=lifespan,
              description="Sales-to-payment coordination for Indian merchants. Verified-ledger MVP.")
for r in (core.router, money.router, engage.router):
    app.include_router(r)


@app.get("/v1/health")
def health():
    return {"status": "ok", "demo_mode": get_settings().demo_mode}
