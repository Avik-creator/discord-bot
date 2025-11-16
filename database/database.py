from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
import config
import ssl
import logging

logger = logging.getLogger('discord_bot')

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

async def migrate_add_is_admin():
    """Add is_admin column to users table if it doesn't exist"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Check if column already exists
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name = 'is_admin'
            """)
            
            result = await conn.execute(check_query)
            column_exists = result.fetchone() is not None
            
            if not column_exists:
                # Add the column with default value False
                alter_query = text("""
                    ALTER TABLE users 
                    ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE
                """)
                
                await conn.execute(alter_query)
                logger.info("✅ Added is_admin column to users table")
            else:
                logger.debug("is_admin column already exists")
    except Exception as e:
        logger.error(f"Error adding is_admin column: {e}", exc_info=True)
        # Don't raise - allow bot to continue even if migration fails
        # The column might already exist or there might be a permission issue

async def init_db():
    """Initialize database tables and run migrations"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Run migrations
    await migrate_add_is_admin()

async def get_session() -> AsyncSession:
    """Get a database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

