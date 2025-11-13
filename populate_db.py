"""
Script to populate the database with player data from API-Football
Run this once after setting up the database to add initial players
"""
import asyncio
import sys
from database.database import AsyncSessionLocal, init_db
from database.models import Card, Logo, LogoRarity, CardType
from utils.api_football import APIFootball
from data.card_catalog import iter_all_cards
import random

async def create_sample_logos(session):
    """Create some sample logos"""
    logos = [
        # Common logos
        Logo(name="Classic Shield", rarity=LogoRarity.COMMON, bonus=1),
        Logo(name="Star Badge", rarity=LogoRarity.COMMON, bonus=1),
        Logo(name="Crown Emblem", rarity=LogoRarity.COMMON, bonus=1),
        Logo(name="Lion Crest", rarity=LogoRarity.COMMON, bonus=1),
        Logo(name="Eagle Badge", rarity=LogoRarity.COMMON, bonus=1),
        
        # Rare logos
        Logo(name="Diamond Shield", rarity=LogoRarity.RARE, bonus=2),
        Logo(name="Golden Star", rarity=LogoRarity.RARE, bonus=2),
        Logo(name="Royal Crown", rarity=LogoRarity.RARE, bonus=2),
        Logo(name="Phoenix Crest", rarity=LogoRarity.RARE, bonus=2),
        
        # Legendary logos
        Logo(name="Ultimate Champion", rarity=LogoRarity.LEGENDARY, bonus=3),
        Logo(name="Legendary Trophy", rarity=LogoRarity.LEGENDARY, bonus=3),
        Logo(name="Mythic Emblem", rarity=LogoRarity.LEGENDARY, bonus=3),
    ]
    
    for logo in logos:
        session.add(logo)
    
    await session.commit()
    print(f"✅ Created {len(logos)} logos")

async def create_sample_cards(session):
    """Create sample cards if API-Football is not available"""
    type_map = {
        "base": CardType.BASE,
        "icon": CardType.ICON,
        "event": CardType.EVENT,
    }
    
    created = 0
    for definition in iter_all_cards():
        card = Card(
            code=definition.code,
            name=definition.name,
            position=definition.position,
            overall_rating=definition.overall,
            attack_stat=definition.attack,
            defense_stat=definition.defense,
            club=definition.club,
            nation=definition.nation,
            league=definition.league,
            card_type=type_map[definition.card_type],
            event_type=definition.event_type,
        )
        session.add(card)
        created += 1
    
    await session.commit()
    print(f"✅ Created {created} sample cards")

async def populate_from_api(session, count=100):
    """Populate database from API-Football"""
    print(f"🔄 Fetching {count} players from API-Football...")
    api = APIFootball()
    
    try:
        cached_count = await api.populate_database(session, count)
        print(f"✅ Successfully cached {cached_count} players from API-Football")
        return True
    except Exception as e:
        print(f"❌ Error fetching from API-Football: {e}")
        print("⚠️  This might be due to:")
        print("   - Invalid API key")
        print("   - Rate limit exceeded")
        print("   - Network issues")
        return False

async def main():
    """Main population function"""
    print("=" * 60)
    print("Football Card Bot - Database Population")
    print("=" * 60)
    print()
    
    # Initialize database
    print("🔄 Initializing database...")
    await init_db()
    print("✅ Database initialized")
    print()
    
    async with AsyncSessionLocal() as session:
        # Check if cards already exist
        from sqlalchemy import select, func
        result = await session.execute(select(func.count(Card.id)))
        existing_count = result.scalar()
        
        if existing_count > 0:
            print(f"⚠️  Database already contains {existing_count} cards")
            response = input("Do you want to add more cards? (y/n): ").lower()
            if response != 'y':
                print("Exiting...")
                return
        
        # Create logos first
        print("\n📦 Creating logos...")
        await create_sample_logos(session)
        
        # Ask user which method to use
        print("\n" + "=" * 60)
        print("Choose population method:")
        print("1. Use API-Football (requires valid API key)")
        print("2. Use sample data (30+ pre-defined cards)")
        print("3. Both (API-Football first, then sample data as backup)")
        print("=" * 60)
        
        choice = input("Enter choice (1/2/3) [default: 3]: ").strip() or "3"
        
        if choice == "1":
            # API-Football only
            count = input("How many players to fetch? [default: 100]: ").strip()
            count = int(count) if count.isdigit() else 100
            success = await populate_from_api(session, count)
            if not success:
                print("\n❌ Failed to populate from API. Please check your API key and try again.")
                sys.exit(1)
        
        elif choice == "2":
            # Sample data only
            print("\n🔄 Creating sample cards...")
            await create_sample_cards(session)
        
        else:
            # Both
            count = input("How many players to fetch from API? [default: 100]: ").strip()
            count = int(count) if count.isdigit() else 100
            success = await populate_from_api(session, count)
            
            if not success:
                print("\n⚠️  API population failed. Falling back to sample data...")
                await create_sample_cards(session)
        
        # Get final count
        result = await session.execute(select(func.count(Card.id)))
        total_cards = result.scalar()
        
        result = await session.execute(select(func.count(Logo.id)))
        total_logos = result.scalar()
        
        print("\n" + "=" * 60)
        print("✅ Database Population Complete!")
        print("=" * 60)
        print(f"Total Cards: {total_cards}")
        print(f"Total Logos: {total_logos}")
        print()
        print("You can now run the bot with: python bot.py")
        print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

