import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

__all__ = ["engine", "Base", "get_db", "async_session", "DATABASE_URL"]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./eve.db")

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = async_sessionmaker(
    engine, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with async_session() as session:
        yield session
