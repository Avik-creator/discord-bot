"""
Cleanup script to remove duplicate active matches from the database.
Run this if you're seeing "Multiple rows were found" errors.
"""

import asyncio
import logging

from sqlalchemy import func, select

from database.database import AsyncSessionLocal
from database.models import ActiveMatch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cleanup_duplicate_matches():
    """Remove duplicate active matches, keeping only the most recent one per player"""
    async with AsyncSessionLocal() as session:
        try:
            # Get all active matches
            result = await session.execute(select(ActiveMatch))
            all_matches = result.scalars().all()

            if not all_matches:
                logger.info("No active matches found in database")
                return

            logger.info(f"Found {len(all_matches)} total active matches")

            # Track which users we've seen and keep only first match per user
            seen_players = set()
            matches_to_delete = []
            matches_to_keep = []

            for match in all_matches:
                # Check if either player is already in another match
                player1_seen = match.player1_id in seen_players
                player2_seen = match.player2_id in seen_players

                if player1_seen or player2_seen:
                    # This is a duplicate
                    matches_to_delete.append(match)
                    logger.warning(
                        f"Found duplicate match (ID: {match.id}): "
                        f"Player1={match.player1_id}, Player2={match.player2_id}, "
                        f"Channel={match.channel_id}"
                    )
                else:
                    # First time seeing these players
                    matches_to_keep.append(match)
                    seen_players.add(match.player1_id)
                    seen_players.add(match.player2_id)

            # Delete duplicates
            if matches_to_delete:
                logger.info(f"Deleting {len(matches_to_delete)} duplicate matches...")
                for match in matches_to_delete:
                    await session.delete(match)
                await session.commit()
                logger.info(
                    f"✅ Successfully deleted {len(matches_to_delete)} duplicate matches"
                )
            else:
                logger.info("✅ No duplicate matches found")

            logger.info(f"Active matches remaining: {len(matches_to_keep)}")
            for match in matches_to_keep:
                logger.info(
                    f"  - Match ID {match.id}: "
                    f"Player1={match.player1_id}, Player2={match.player2_id}, "
                    f"Channel={match.channel_id}"
                )

        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
            await session.rollback()


async def clear_all_active_matches():
    """Clear ALL active matches from the database (use if matches are stuck)"""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(ActiveMatch))
            all_matches = result.scalars().all()

            if not all_matches:
                logger.info("No active matches to clear")
                return

            logger.info(f"Clearing {len(all_matches)} active matches...")
            for match in all_matches:
                await session.delete(match)
            await session.commit()
            logger.info(f"✅ Successfully cleared all active matches")

        except Exception as e:
            logger.error(f"Error clearing matches: {e}", exc_info=True)
            await session.rollback()


async def main():
    """Main function"""
    print("\n=== Active Match Cleanup Tool ===\n")
    print("1. Remove duplicate matches only")
    print("2. Clear ALL active matches (use if stuck)")
    print("3. Exit")

    choice = input("\nEnter your choice (1-3): ").strip()

    if choice == "1":
        logger.info("Starting duplicate match cleanup...")
        await cleanup_duplicate_matches()
    elif choice == "2":
        confirm = (
            input("Are you sure you want to clear ALL active matches? (yes/no): ")
            .strip()
            .lower()
        )
        if confirm == "yes":
            logger.info("Clearing all active matches...")
            await clear_all_active_matches()
        else:
            logger.info("Cancelled")
    elif choice == "3":
        logger.info("Exiting")
    else:
        logger.error("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())
