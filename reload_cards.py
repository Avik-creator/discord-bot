"""
Reload all cards from card_catalog.py
This script will DELETE all existing cards and reload them from the catalog.
WARNING: This will delete all card data from the database!
"""
import asyncio
from database.database import AsyncSessionLocal, init_db
from database.models import Card, CardType, Collection, TeamSlot, SpawnedCard
from data.card_catalog import iter_all_cards
from sqlalchemy import select, delete, func

async def reload_cards():
    """Delete all cards and reload from catalog"""
    print("=" * 60)
    print("CARD RELOAD UTILITY")
    print("=" * 60)
    print()
    print("⚠️  WARNING: This will delete ALL cards from the database!")
    print("This includes:")
    print("  - All card definitions")
    print("  - All user collections (cards owned by users)")
    print("  - All team lineups (players in teams)")
    print()
    
    response = input("Are you SURE you want to continue? (type 'YES' to confirm): ")
    
    if response != 'YES':
        print("\n❌ Operation cancelled")
        return
    
    # Initialize database
    print("\n🔄 Initializing database...")
    await init_db()
    print("✅ Database initialized")
    print()
    
    async with AsyncSessionLocal() as session:
        # Count existing cards
        result = await session.execute(select(func.count(Card.id)))
        existing_count = result.scalar()
        
        if existing_count > 0:
            print(f"🗑️  Deleting {existing_count} existing cards...")
            
            # Delete in order to respect foreign key constraints
            print("  Deleting spawned cards...")
            await session.execute(delete(SpawnedCard))
            
            print("  Deleting team slots...")
            await session.execute(delete(TeamSlot))
            
            print("  Deleting user collections...")
            await session.execute(delete(Collection))
            
            # Delete all cards (must be last due to foreign keys)
            print("  Deleting cards...")
            await session.execute(delete(Card))
            await session.commit()
            print(f"✅ Deleted {existing_count} cards and related data")
        else:
            print("ℹ️  No existing cards to delete")
        
        print()
        print("🔄 Loading cards from catalog...")
        
        # Type mapping
        type_map = {
            "base": CardType.BASE,
            "icon": CardType.ICON,
            "event": CardType.EVENT,
        }
        
        inserted = 0
        errors = []
        
        for definition in iter_all_cards():
            try:
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
                inserted += 1
                
                # Commit in batches of 50
                if inserted % 50 == 0:
                    await session.commit()
                    print(f"  Loaded {inserted} cards...")
            except Exception as e:
                errors.append(f"Error loading {definition.name}: {e}")
        
        # Final commit
        await session.commit()
        
        # Get final count
        result = await session.execute(select(func.count(Card.id)))
        total = result.scalar()
        
        print()
        print("=" * 60)
        print("✅ Reload Complete!")
        print("=" * 60)
        print(f"Loaded: {inserted} cards from catalog")
        print(f"Total cards in database: {total}")
        
        if errors:
            print(f"\n⚠️  {len(errors)} errors occurred:")
            for error in errors[:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(errors) > 10:
                print(f"  ... and {len(errors) - 10} more errors")
        
        print("=" * 60)
        print("\n📋 Summary:")
        print("  ✅ Cards reloaded from card_catalog.py")
        print("  ⚠️  User collections cleared (users will need to collect cards again)")
        print("  ⚠️  Team lineups cleared (users will need to rebuild their teams)")
        print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(reload_cards())
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

