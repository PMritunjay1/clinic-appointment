import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routers import auth, centres, bookings, payments
from app.database import engine, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup database on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created.")
    yield

app = FastAPI(
    title="EVE Healthcare API", 
    description="API for diagnostic test bookings and simulated payments",
    lifespan=lifespan
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(centres.router, prefix="/api/centres", tags=["Diagnostic Centres"])
app.include_router(bookings.router, prefix="/api/bookings", tags=["Bookings"])
app.include_router(payments.router, prefix="/api/payments", tags=["Payments"])

@app.get("/")
async def root():
    return {"message": "Welcome to EVE Healthcare API. Visit /docs for Swagger documentation."}
