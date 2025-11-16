from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
import config
import ssl

Base = declarative_base()

# Configure SSL for cloud databases (like Neon)
# asyncpg requires SSL context, not query parameters like sslmode
connect_args = {}
if 'neon.tech' in config.DATABASE_URL or 'sslmode' in str(config.DATABASE_URL).lower():
    # For Neon and other cloud databases, create SSL context
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connect_args['ssl'] = ssl_context

engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    pool_pre_ping=True,
    connect_args=connect_args
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    """Get a database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

