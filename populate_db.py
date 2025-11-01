"""
Script to populate the database with player data from API-Football
Run this once after setting up the database to add initial players
"""
import asyncio
import sys
from database.database import AsyncSessionLocal, init_db
from database.models import Card, Logo, LogoRarity, CardType
from utils.api_football import APIFootball
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
    sample_players = [
        # Top tier players
        ("Lionel Messi", "RW", 93, 95, 45, "Inter Miami", "Argentina", "MLS", CardType.ICON),
        ("Cristiano Ronaldo", "ST", 91, 93, 50, "Al Nassr", "Portugal", "Saudi Pro League", CardType.ICON),
        ("Kylian Mbappé", "ST", 92, 96, 48, "Real Madrid", "France", "La Liga", CardType.BASE),
        ("Erling Haaland", "ST", 91, 94, 46, "Manchester City", "Norway", "Premier League", CardType.BASE),
        ("Kevin De Bruyne", "CAM", 91, 92, 72, "Manchester City", "Belgium", "Premier League", CardType.BASE),
        
        # High tier players
        ("Vinícius Jr", "LW", 89, 93, 50, "Real Madrid", "Brazil", "La Liga", CardType.BASE),
        ("Mohamed Salah", "RW", 89, 92, 58, "Liverpool", "Egypt", "Premier League", CardType.BASE),
        ("Harry Kane", "ST", 89, 90, 60, "Bayern Munich", "England", "Bundesliga", CardType.BASE),
        ("Bukayo Saka", "RW", 87, 90, 65, "Arsenal", "England", "Premier League", CardType.BASE),
        ("Jude Bellingham", "CAM", 88, 85, 75, "Real Madrid", "England", "La Liga", CardType.BASE),
        
        # Midfielders
        ("Luka Modrić", "RCM", 87, 75, 85, "Real Madrid", "Croatia", "La Liga", CardType.ICON),
        ("Rodri", "CDM", 88, 70, 90, "Manchester City", "Spain", "Premier League", CardType.BASE),
        ("Joshua Kimmich", "CDM", 88, 72, 88, "Bayern Munich", "Germany", "Bundesliga", CardType.BASE),
        ("Bruno Fernandes", "CAM", 87, 86, 75, "Manchester United", "Portugal", "Premier League", CardType.BASE),
        ("Martin Ødegaard", "CAM", 87, 88, 74, "Arsenal", "Norway", "Premier League", CardType.BASE),
        
        # Defenders
        ("Virgil van Dijk", "RCB", 89, 60, 92, "Liverpool", "Netherlands", "Premier League", CardType.BASE),
        ("Rúben Dias", "RCB", 88, 55, 90, "Manchester City", "Portugal", "Premier League", CardType.BASE),
        ("Antonio Rüdiger", "LCB", 87, 58, 89, "Real Madrid", "Germany", "La Liga", CardType.BASE),
        ("Trent Alexander-Arnold", "RB", 87, 82, 80, "Liverpool", "England", "Premier League", CardType.BASE),
        ("Andrew Robertson", "LB", 86, 75, 85, "Liverpool", "Scotland", "Premier League", CardType.BASE),
        
        # Goalkeepers
        ("Thibaut Courtois", "GK", 89, 10, 92, "Real Madrid", "Belgium", "La Liga", CardType.BASE),
        ("Alisson", "GK", 89, 10, 91, "Liverpool", "Brazil", "Premier League", CardType.BASE),
        ("Ederson", "GK", 88, 10, 90, "Manchester City", "Brazil", "Premier League", CardType.BASE),
        ("Marc-André ter Stegen", "GK", 88, 10, 90, "Barcelona", "Germany", "La Liga", CardType.BASE),
        
        # More variety
        ("Pedri", "LCM", 86, 82, 78, "Barcelona", "Spain", "La Liga", CardType.BASE),
        ("Gavi", "LCM", 85, 80, 76, "Barcelona", "Spain", "La Liga", CardType.BASE),
        ("Phil Foden", "CAM", 87, 88, 70, "Manchester City", "England", "Premier League", CardType.BASE),
        ("Bernardo Silva", "RCM", 88, 86, 76, "Manchester City", "Portugal", "Premier League", CardType.BASE),
        ("Federico Valverde", "RCM", 87, 82, 82, "Real Madrid", "Uruguay", "La Liga", CardType.BASE),
        ("Declan Rice", "CDM", 86, 68, 86, "Arsenal", "England", "Premier League", CardType.BASE),
    ]
    
    # Add Event cards (TOTW examples)
    event_players = [
        ("TOTW Mbappé", "ST", 94, 98, 50, "Real Madrid", "France", "La Liga", CardType.EVENT, "TOTW"),
        ("TOTW Salah", "RW", 91, 94, 60, "Liverpool", "Egypt", "Premier League", CardType.EVENT, "TOTW"),
        ("TOTS Haaland", "ST", 95, 97, 48, "Manchester City", "Norway", "Premier League", CardType.EVENT, "TOTS"),
        ("TOTS De Bruyne", "CAM", 94, 95, 75, "Manchester City", "Belgium", "Premier League", CardType.EVENT, "TOTS"),
        ("UCL Vinícius", "LW", 91, 95, 52, "Real Madrid", "Brazil", "La Liga", CardType.EVENT, "UCL"),
    ]
    
    all_players = sample_players + [(name, pos, ovr, att, def, club, nat, league, card_type, event) 
                                    for name, pos, ovr, att, def, club, nat, league, card_type, event 
                                    in [(p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9]) 
                                        for p in event_players]]
    
    for player_data in sample_players:
        card = Card(
            name=player_data[0],
            position=player_data[1],
            overall_rating=player_data[2],
            attack_stat=player_data[3],
            defense_stat=player_data[4],
            club=player_data[5],
            nation=player_data[6],
            league=player_data[7],
            card_type=player_data[8]
        )
        session.add(card)
    
    for player_data in event_players:
        card = Card(
            name=player_data[0],
            position=player_data[1],
            overall_rating=player_data[2],
            attack_stat=player_data[3],
            defense_stat=player_data[4],
            club=player_data[5],
            nation=player_data[6],
            league=player_data[7],
            card_type=player_data[8],
            event_type=player_data[9]
        )
        session.add(card)
    
    await session.commit()
    print(f"✅ Created {len(sample_players) + len(event_players)} sample cards")

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

