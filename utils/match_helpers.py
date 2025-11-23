"""Helper functions for match-related operations"""

import logging
from typing import Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ActiveMatch

logger = logging.getLogger("discord_bot")


async def is_user_in_active_match(
    session: AsyncSession, user_id: int
) -> Tuple[bool, Optional[int]]:
    """
    Check if a user is currently in an active match.

    Args:
        session: Database session
        user_id: Discord user ID to check

    Returns:
        Tuple of (is_in_match: bool, channel_id: Optional[int])
        - is_in_match: True if user is in an active match
        - channel_id: Channel ID where the match is happening (None if not in match)
    """
    try:
        result = await session.execute(
            select(ActiveMatch).where(
                or_(
                    ActiveMatch.player1_id == user_id, ActiveMatch.player2_id == user_id
                )
            )
        )
        active_match = result.scalar_one_or_none()

        if active_match:
            logger.info(
                f"User {user_id} is in active match in channel {active_match.channel_id}"
            )
            return True, active_match.channel_id

        return False, None

    except Exception as e:
        logger.error(
            f"Error checking active match for user {user_id}: {e}", exc_info=True
        )
        # On error, allow the action (fail open to avoid blocking legitimate actions)
        return False, None


async def get_active_match_for_user(
    session: AsyncSession, user_id: int
) -> Optional[ActiveMatch]:
    """
    Get the active match object for a user if they are in one.

    Args:
        session: Database session
        user_id: Discord user ID to check

    Returns:
        ActiveMatch object if user is in a match, None otherwise
    """
    try:
        result = await session.execute(
            select(ActiveMatch).where(
                or_(
                    ActiveMatch.player1_id == user_id, ActiveMatch.player2_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()

    except Exception as e:
        logger.error(
            f"Error getting active match for user {user_id}: {e}", exc_info=True
        )
        return None
