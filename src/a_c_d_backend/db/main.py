from sqlmodel.ext.asyncio.session import AsyncSession
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from ...a_c_d_backend.config import settings

DATABASE_URL = settings.DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=True, pool_pre_ping=True, pool_size=20, max_overflow=10,)

Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False, autocommit=False)

# async def init_db():
#     async with engine.begin() as conn:
#         await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with Session() as session:
        yield session
