"""
Database reset utility
WARNING: This will delete ALL data from the database!
Use only for development/testing purposes.
"""
import asyncio
from database.database import engine, Base
import sys

async def reset_database():
    """Drop all tables and recreate them"""
    print("=" * 60)
    print("DATABASE RESET UTILITY")
    print("=" * 60)
    print()
    print("⚠️  WARNING: This will delete ALL data from the database!")
    print("This includes:")
    print("  - All user data")
    print("  - All cards")
    print("  - All teams")
    print("  - All match history")
    print("  - All server configurations")
    print()
    
    response = input("Are you SURE you want to continue? (type 'YES' to confirm): ")
    
    if response != 'YES':
        print("\n❌ Operation cancelled")
        return
    
    print("\n🔄 Dropping all tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    print("✅ All tables dropped")
    
    print("🔄 Recreating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ All tables recreated")
    
    print("\n" + "=" * 60)
    print("✅ Database reset complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run: python populate_db.py")
    print("2. Run: python bot.py")
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(reset_database())
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

