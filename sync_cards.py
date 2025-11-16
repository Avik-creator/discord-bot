"""
Sync card catalog with database
Updates existing cards and inserts new ones
"""
import asyncio
from database.database import AsyncSessionLocal, init_db
from database.models import Card, CardType
from data.card_catalog import iter_all_cards
from sqlalchemy import select

async def sync_cards():
    """Sync all cards from catalog to database"""
    print("=" * 60)
    print("Card Catalog Sync")
    print("=" * 60)
    print()
    
    # Initialize database
    print("🔄 Initializing database...")
    await init_db()
    print("✅ Database initialized")
    print()
    
    type_map = {
        "base": CardType.BASE,
        "icon": CardType.ICON,
        "event": CardType.EVENT,
    }
    
    async with AsyncSessionLocal() as session:
        updated = 0
        inserted = 0
        skipped = 0
        
        print("🔄 Syncing cards from catalog...")
        
        for definition in iter_all_cards():
            # Check if card exists by code or name
            if definition.code:
                result = await session.execute(
                    select(Card).where(Card.code == definition.code)
                )
                existing = result.scalar_one_or_none()
            else:
                # For cards without code, check by name and position
                result = await session.execute(
                    select(Card).where(
                        Card.name == definition.name,
                        Card.position == definition.position
                    )
                )
                existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing card
                existing.name = definition.name
                existing.position = definition.position
                existing.overall_rating = definition.overall
                existing.attack_stat = definition.attack
                existing.defense_stat = definition.defense
                existing.club = definition.club
                existing.nation = definition.nation
                existing.league = definition.league
                existing.card_type = type_map[definition.card_type]
                existing.event_type = definition.event_type
                if definition.code:
                    existing.code = definition.code
                updated += 1
            else:
                # Insert new card
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
            if (updated + inserted) % 50 == 0:
                await session.commit()
                print(f"  Processed {updated + inserted} cards...")
        
        # Final commit
        await session.commit()
        
        # Get total count
        from sqlalchemy import func
        result = await session.execute(select(func.count(Card.id)))
        total = result.scalar()
        
        print()
        print("=" * 60)
        print("✅ Sync Complete!")
        print("=" * 60)
        print(f"Updated: {updated} cards")
        print(f"Inserted: {inserted} cards")
        print(f"Total cards in database: {total}")
        print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(sync_cards())
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

