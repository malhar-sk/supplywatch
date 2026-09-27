import hashlib
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import select

from api.auth import require_api_key
from api.routes.alerts import router as alerts_router
from api.routes.guest import router as guest_router
from api.routes.health import router as health_router
from api.routes.materials import router as materials_router
from api.schemas import CreateApiKeyRequest
from core.config import get_settings
from core.database import ApiKey, AsyncSessionLocal, Base, Material, engine
from scheduler.jobs import build_scheduler

SEED_MATERIALS = [
    ("Gallium", "Ga", "Critical Metal", ["China", "Germany"]),
    ("Germanium", "Ge", "Critical Metal", ["China", "Canada"]),
    ("Cobalt", "Co", "Battery Metal", ["DRC", "Indonesia"]),
    ("Lithium", "Li", "Battery Metal", ["Australia", "Chile"]),
    ("Yttrium", "Y", "Rare Earth", ["China", "Myanmar"]),
    ("Dysprosium", "Dy", "Rare Earth", ["China", "Australia"]),
    ("Indium", "In", "Critical Metal", ["China", "South Korea"]),
    ("Graphite", "C", "Battery Material", ["China", "Mozambique"]),
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        for n, s, c, p in SEED_MATERIALS:
            exists = (await db.execute(select(Material).where(Material.name == n))).scalar_one_or_none()
            if not exists:
                db.add(Material(name=n, symbol=s, category=c, primary_producers=p))
        await db.commit()
    scheduler = build_scheduler(AsyncSessionLocal)
    if get_settings().enable_scheduler:
        scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(title="SupplyWatch", version=get_settings().app_version, lifespan=lifespan)
app.include_router(health_router)
app.include_router(materials_router)
app.include_router(alerts_router)
app.include_router(guest_router)

@app.post('/auth/keys')
async def create_key(payload: CreateApiKeyRequest):
    raw_key = f"sw_{secrets.token_urlsafe(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    async with AsyncSessionLocal() as db:
        db.add(ApiKey(key_hash=key_hash, company_name=payload.company_name, tier=payload.tier))
        await db.commit()
    return {"data": {"api_key": raw_key, "tier": payload.tier}, "meta": {"timestamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc), "version": get_settings().app_version}}
