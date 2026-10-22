"""
db/database.py — Async SQLAlchemy engine متصل بـ MySQL (seha_db).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from config import DATABASE_URL

# ── Engine ────────────────────────────────────────────────────────────────────
# pool_pre_ping=True يضمن إن الاتصال شغّال دايماً حتى بعد انتهاء المهلة
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=3600,   # تجديد الاتصالات كل ساعة
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    بنتأكد إن الاتصال بـ MySQL شغّال.
    لو MySQL مش شغّال، بنسجّل تحذير ومش بنوقّف البوت.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("MySQL connected OK — seha_db ready.")
    except Exception as e:
        logger.warning(
            f"MySQL not available yet: {e}\n"
            "The bot will still run but saving reports will fail "
            "until MySQL is started."
        )


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
