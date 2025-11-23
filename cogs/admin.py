import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import AsyncSessionLocal
from database.models import (
    ActiveMatch,
    Card,
    CardType,
    Collection,
    Logo,
    LogoRarity,
    PromoCode,
    ServerConfig,
    User,
)
from utils.card_spawner import CardSpawner
from utils.match_helpers import is_user_in_active_match

# Create module-level logger
logger = logging.getLogger("discord_bot")


async def is_admin_check(interaction: discord.Interaction) -> bool:
    """Check if user is admin (either Discord admin, database admin, or bot owner)"""
    user_id = interaction.user.id
    user_name = str(interaction.user)

    try:
        # Bot owner always has access
        if hasattr(interaction, "client") and hasattr(interaction.client, "is_owner"):
            try:
                if await interaction.client.is_owner(interaction.user):
                    logger.debug(
                        f"User {user_name} ({user_id}) is bot owner - granting admin access"
                    )
                    return True
            except Exception as e:
                logger.warning(f"Error checking bot owner status for {user_id}: {e}")

        # Must be in a guild for Discord admin checks
        if interaction.guild is None:
            logger.debug(
                f"User {user_name} ({user_id}) tried to use admin command outside of guild"
            )
            # Still check database admin status even outside guild
        else:
            guild_id = interaction.guild.id
            guild_name = interaction.guild.name

            # Guild owner always has access
            try:
                if interaction.guild.owner_id == interaction.user.id:
                    logger.debug(
                        f"User {user_name} ({user_id}) is guild owner of {guild_name} - granting admin access"
                    )
                    return True
            except Exception as e:
                logger.warning(
                    f"Error checking guild owner for {user_id} in {guild_name}: {e}"
                )

            # Get member object - interaction.user should already be a Member in guild context
            member = None

            # Method 1: interaction.user is already a Member in guild contexts
            if isinstance(interaction.user, discord.Member):
                member = interaction.user
                logger.debug(
                    f"Using interaction.user as Member for {user_name} ({user_id})"
                )

            # Method 2: Try cache if not already a Member
            if member is None:
                try:
                    member = interaction.guild.get_member(interaction.user.id)
                    if member:
                        logger.debug(
                            f"Found member {user_name} ({user_id}) in cache for {guild_name}"
                        )
                except Exception as e:
                    logger.debug(
                        f"Could not get member from cache for {user_id} in {guild_name}: {e}"
                    )

            # Method 3: Force fetch if still None (requires members intent)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(interaction.user.id)
                    logger.debug(
                        f"Fetched member {user_name} ({user_id}) for {guild_name}"
                    )
                except discord.NotFound:
                    logger.warning(f"Member {user_id} not found in guild {guild_name}")
                except discord.Forbidden:
                    logger.warning(
                        f"Missing permissions to fetch member {user_id} in guild {guild_name}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Error fetching member {user_id} in guild {guild_name}: {e}"
                    )

            # Check administrator permission
            if member is not None:
                try:
                    # Check if member has administrator permission
                    if (
                        hasattr(member, "guild_permissions")
                        and member.guild_permissions.administrator
                    ):
                        logger.debug(
                            f"User {user_name} ({user_id}) has administrator permission in {guild_name} - granting admin access"
                        )
                        return True
                    else:
                        logger.debug(
                            f"User {user_name} ({user_id}) does not have administrator permission in {guild_name}"
                        )
                        # Log permission value for debugging if available
                        if hasattr(member, "guild_permissions"):
                            logger.debug(
                                f"User {user_id} guild_permissions value: {member.guild_permissions.value}"
                            )
                except AttributeError as e:
                    logger.warning(
                        f"Member {user_id} does not have guild_permissions attribute: {e}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Error checking administrator permission for {user_id} in {guild_name}: {e}"
                    )
            else:
                logger.warning(
                    f"Could not get member object for {user_id} in {guild_name} - cannot check Discord admin status"
                )

        # Check database admin status (guild-scoped)
        # NOTE: DB admin is now per-guild to prevent cross-guild elevation
        try:
            if interaction.guild is not None:
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(User).where(User.id == interaction.user.id)
                    )
                    user = result.scalar_one_or_none()
                    if user and hasattr(user, "is_admin") and user.is_admin:
                        # DB admin still requires being in a guild to use commands
                        logger.debug(
                            f"User {user_name} ({user_id}) has database admin status in guild {interaction.guild.id} - granting admin access"
                        )
                        return True
                    else:
                        logger.debug(
                            f"User {user_name} ({user_id}) does not have database admin status"
                        )
            else:
                logger.debug(
                    f"User {user_name} ({user_id}) tried admin check outside guild - DB admin requires guild context"
                )
        except Exception as e:
            logger.error(
                f"Error checking database admin status for {user_id}: {e}",
                exc_info=True,
            )

        # All checks failed
        logger.info(f"User {user_name} ({user_id}) failed all admin checks")
        return False

    except Exception as e:
        # Ultimate catch-all - if ANYTHING goes wrong, deny access (fail secure)
        logger.error(
            f"Unexpected error in is_admin_check for {user_id}: {e}", exc_info=True
        )
        return False


async def can_manage_admins(interaction: discord.Interaction) -> bool:
    """Check if user can manage admins (bot owner or existing admin)"""
    # Bot owner can always manage admins
    if await interaction.client.is_owner(interaction.user):
        return True

    # Check if user is admin (Discord or database)
    return await is_admin_check(interaction)


class AdminCog(commands.Cog):
    """Admin commands"""

    def __init__(self, bot):
        self.bot = bot
        self.card_spawner = CardSpawner(bot)

    @app_commands.command(
        name="admin_spawn", description="[ADMIN] Spawn 15 cards at once"
    )
    @app_commands.check(is_admin_check)
    async def admin_spawn(self, interaction: discord.Interaction):
        """admin_spawn"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Get server config to check spawn channel
                result = await session.execute(
                    select(ServerConfig).where(
                        ServerConfig.guild_id == interaction.guild.id
                    )
                )
                server_config = result.scalar_one_or_none()

                if not server_config or not server_config.spawn_channel_id:
                    await interaction.followup.send(
                        "❌ Please configure a spawn channel first using `/configure`!",
                        ephemeral=True,
                    )
                    return

                channel_id = server_config.spawn_channel_id

                # Get the channel to verify it exists and bot has permissions
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    # Try fetching the channel if not in cache
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except Exception as e:
                        await interaction.followup.send(
                            f"❌ Could not find channel with ID {channel_id}. Please check the configured spawn channel.",
                            ephemeral=True,
                        )
                        logger = logging.getLogger("discord_bot")
                        logger.error(f"Error fetching channel {channel_id}: {e}")
                        return

                # Check bot permissions
                if not channel.permissions_for(interaction.guild.me).send_messages:
                    await interaction.followup.send(
                        f"❌ I don't have permission to send messages in {channel.mention}!",
                        ephemeral=True,
                    )
                    return

                await interaction.followup.send(
                    "🔄 Spawning 15 cards...", ephemeral=True
                )

                # Spawn 15 cards with delay OUTSIDE DB session to avoid rate limits
                spawned_count = 0

                for i in range(15):
                    try:
                        # Use ONE session per spawn, but don't nest them
                        async with AsyncSessionLocal() as spawn_session:
                            message = await self.card_spawner.spawn_card(
                                spawn_session,
                                interaction.guild.id,
                                channel_id,
                                bypass_active_check=True,
                            )
                            # Commit happens inside spawn_card
                            if message:
                                spawned_count += 1
                            else:
                                logger.warning(f"Failed to spawn card {i + 1}/15")
                        # Delay AFTER session closes to avoid holding locks
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(
                            f"Error spawning card {i + 1}/15: {e}", exc_info=True
                        )

                embed = discord.Embed(
                    title="✅ Cards Spawned!",
                    description=f"Successfully spawned {spawned_count} out of 15 cards in {channel.mention}!",
                    color=discord.Color.green()
                    if spawned_count == 15
                    else discord.Color.orange(),
                )

                if spawned_count < 15:
                    embed.add_field(
                        name="⚠️ Note",
                        value=f"{15 - spawned_count} cards failed to spawn. Check logs for details.",
                        inline=False,
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in admin_spawn: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while spawning cards.", ephemeral=True
            )

    @app_commands.command(name="give_user", description="[ADMIN] Give a card to a user")
    @app_commands.describe(
        user="The user to give the card to", card_name="Name of the card"
    )
    @app_commands.check(is_admin_check)
    async def give_user_card(
        self, interaction: discord.Interaction, user: discord.Member, card_name: str
    ):
        """give_user_card"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Check if user is in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, user.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ Cannot give cards to {user.mention} - they are in an active match!\n"
                        f"Please wait until their match in <#{channel_id}> is complete.",
                        ephemeral=True,
                    )
                    return

                # Find card - handle multiple matches with smart selection
                result = await session.execute(
                    select(Card)
                    .where(Card.name.ilike(f"%{card_name}%"))
                    .order_by(Card.overall_rating.desc())
                )
                cards = result.scalars().all()

                if not cards:
                    await interaction.followup.send(
                        f"❌ Card '{card_name}' not found!", ephemeral=True
                    )
                    return

                # Smart matching: exact > prefix > highest OVR
                card = None
                card_name_lower = card_name.lower()
                for c in cards:
                    if c.name.lower() == card_name_lower:
                        card = c
                        break
                if not card:
                    for c in cards:
                        if c.name.lower().startswith(card_name_lower):
                            card = c
                            break
                if not card:
                    card = cards[0]

                multiple_matches_warning = None
                if len(cards) > 1:
                    matching_names = [c.name for c in cards[:5]]
                    multiple_matches_warning = (
                        f"⚠️ Multiple cards found. Using: **{card.name}** (best match)\n"
                    )
                    multiple_matches_warning += (
                        f"Other matches: {', '.join(matching_names[1:])}"
                    )
                    if len(cards) > 5:
                        multiple_matches_warning += f" (and {len(cards) - 5} more)"

                # Get or create user with proper field initialization
                result = await session.execute(select(User).where(User.id == user.id))
                db_user = result.scalar_one_or_none()

                if not db_user:
                    db_user = User(
                        id=user.id,
                        username=user.name,
                        cards_collected=0,
                        is_admin=False,
                    )
                    session.add(db_user)
                    await session.flush()

                # Check if user already has this card (duplicate prevention)
                existing_collection = await session.execute(
                    select(Collection).where(
                        Collection.user_id == user.id, Collection.card_id == card.id
                    )
                )
                if existing_collection.scalar_one_or_none():
                    await interaction.followup.send(
                        f"ℹ️ {user.mention} already has **{card.name}** in their collection!",
                        ephemeral=True,
                    )
                    return

                # Add to collection
                collection_entry = Collection(user_id=user.id, card_id=card.id)
                session.add(collection_entry)

                # Safely increment cards_collected
                db_user.cards_collected = (db_user.cards_collected or 0) + 1

                await session.commit()

                embed = discord.Embed(
                    title="✅ Card Given!",
                    description=f"**{card.name}** has been given to {user.mention}!",
                    color=discord.Color.green(),
                )

                if multiple_matches_warning:
                    embed.add_field(
                        name="⚠️ Note", value=multiple_matches_warning, inline=False
                    )

                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in give_user_card: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while giving the card.", ephemeral=True
            )

    @app_commands.command(
        name="give_club", description="[ADMIN] Give all cards from a club"
    )
    @app_commands.describe(
        user="The user to give cards to", club_name="Name of the club"
    )
    @app_commands.check(is_admin_check)
    async def give_club(
        self, interaction: discord.Interaction, user: discord.Member, club_name: str
    ):
        """give_club"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Check if user is in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, user.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ Cannot give cards to {user.mention} - they are in an active match!\n"
                        f"Please wait until their match in <#{channel_id}> is complete.",
                        ephemeral=True,
                    )
                    return

                # Find all cards from club
                result = await session.execute(
                    select(Card).where(Card.club.ilike(f"%{club_name}%"))
                )
                cards = result.scalars().all()

                if not cards:
                    await interaction.followup.send(
                        f"❌ No cards found for club '{club_name}'!", ephemeral=True
                    )
                    return

                # Get or create user
                result = await session.execute(select(User).where(User.id == user.id))
                db_user = result.scalar_one_or_none()

                if not db_user:
                    db_user = User(id=user.id, username=user.name)
                    session.add(db_user)
                    await session.flush()

                # Check which cards user already has
                result = await session.execute(
                    select(Collection.card_id).where(Collection.user_id == user.id)
                )
                existing_card_ids = set(result.scalars().all())

                # Add only new cards to collection
                new_cards = []
                for card in cards:
                    if card.id not in existing_card_ids:
                        collection_entry = Collection(user_id=user.id, card_id=card.id)
                        session.add(collection_entry)
                        new_cards.append(card)

                db_user.cards_collected += len(new_cards)

                await session.commit()

                embed = discord.Embed(
                    title="✅ Club Collection Given!",
                    description=f"Given {len(new_cards)} new cards from **{club_name}** to {user.mention}!",
                    color=discord.Color.green(),
                )

                duplicates = len(cards) - len(new_cards)
                if duplicates > 0:
                    embed.add_field(
                        name="⚠️ Note",
                        value=f"Skipped {duplicates} duplicate cards already in collection.",
                        inline=False,
                    )

                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in give_club: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while giving club cards.", ephemeral=True
            )

    @app_commands.command(
        name="give_event", description="[ADMIN] Give all cards from an event"
    )
    @app_commands.describe(
        user="The user to give cards to",
        event_type="Type of event (TOTW, TOTS, TOTY, etc.)",
    )
    @app_commands.check(is_admin_check)
    async def give_event(
        self, interaction: discord.Interaction, user: discord.Member, event_type: str
    ):
        """give_event"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Check if user is in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, user.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ Cannot give cards to {user.mention} - they are in an active match!\n"
                        f"Please wait until their match in <#{channel_id}> is complete.",
                        ephemeral=True,
                    )
                    return

                # Find all event cards
                result = await session.execute(
                    select(Card)
                    .where(Card.card_type == CardType.EVENT)
                    .where(Card.event_type.ilike(f"%{event_type}%"))
                )
                cards = result.scalars().all()

                if not cards:
                    await interaction.followup.send(
                        f"❌ No cards found for event '{event_type}'!", ephemeral=True
                    )
                    return

                # Get or create user with proper initialization
                result = await session.execute(select(User).where(User.id == user.id))
                db_user = result.scalar_one_or_none()

                if not db_user:
                    db_user = User(
                        id=user.id,
                        username=user.name,
                        cards_collected=0,
                        is_admin=False,
                    )
                    session.add(db_user)
                    await session.flush()

                # Check existing collection to avoid duplicates
                result = await session.execute(
                    select(Collection.card_id)
                    .where(Collection.user_id == user.id)
                    .where(Collection.card_id.in_([c.id for c in cards]))
                )
                existing_card_ids = {row[0] for row in result.all()}

                # Add only new cards
                new_cards = [c for c in cards if c.id not in existing_card_ids]
                for card in new_cards:
                    collection_entry = Collection(user_id=user.id, card_id=card.id)
                    session.add(collection_entry)

                db_user.cards_collected = (db_user.cards_collected or 0) + len(
                    new_cards
                )

                await session.commit()

                embed = discord.Embed(
                    title="✅ Event Collection Given!",
                    description=f"Given {len(new_cards)} new cards from **{event_type}** event to {user.mention}!",
                    color=discord.Color.green(),
                )

                if len(existing_card_ids) > 0:
                    embed.add_field(
                        name="⚠️ Note",
                        value=f"Skipped {len(existing_card_ids)} duplicate cards.",
                        inline=False,
                    )

                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in give_event: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while giving event cards.", ephemeral=True
            )

    @app_commands.command(
        name="give_full",
        description="[ADMIN] Give every BASE card (excludes icons/events)",
    )
    @app_commands.describe(user="The user to give all base cards to")
    @app_commands.check(is_admin_check)
    async def give_full(self, interaction: discord.Interaction, user: discord.Member):
        """Give all BASE cards to a user (excludes premium/icon/event)"""
        await interaction.response.defer(ephemeral=True)

        async with AsyncSessionLocal() as session:
            # Check if user is in an active match
            is_in_match, channel_id = await is_user_in_active_match(session, user.id)
            if is_in_match:
                await interaction.followup.send(
                    f"⚠️ Cannot give cards to {user.mention} - they are in an active match!\n"
                    f"Please wait until their match in <#{channel_id}> is complete.",
                    ephemeral=True,
                )
                return

            # Get ONLY base cards (not icons/events)
            result = await session.execute(
                select(Card).where(Card.card_type == CardType.BASE)
            )
            cards = result.scalars().all()

            if not cards:
                await interaction.followup.send(
                    "❌ No base cards found in database!", ephemeral=True
                )
                return

            # Get or create user with proper initialization
            result = await session.execute(select(User).where(User.id == user.id))
            db_user = result.scalar_one_or_none()

            if not db_user:
                db_user = User(
                    id=user.id, username=user.name, cards_collected=0, is_admin=False
                )
                session.add(db_user)
                await session.flush()

            # Check existing collection to avoid duplicates
            result = await session.execute(
                select(Collection.card_id)
                .where(Collection.user_id == user.id)
                .where(Collection.card_id.in_([c.id for c in cards]))
            )
            existing_card_ids = {row[0] for row in result.all()}

            # Add only new cards
            new_cards = [c for c in cards if c.id not in existing_card_ids]
            for card in new_cards:
                collection_entry = Collection(user_id=user.id, card_id=card.id)
                session.add(collection_entry)

            db_user.cards_collected = (db_user.cards_collected or 0) + len(new_cards)

            await session.commit()

            embed = discord.Embed(
                title="✅ Full Base Collection Given!",
                description=f"Given {len(new_cards)} base cards to {user.mention}!",
                color=discord.Color.green(),
            )

            if len(existing_card_ids) > 0:
                embed.add_field(
                    name="⚠️ Note",
                    value=f"Skipped {len(existing_card_ids)} duplicate cards.",
                    inline=False,
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="promo_add", description="[ADMIN] Add a promo code")
    @app_commands.describe(
        code="The promo code",
        reward_type="Type of reward",
        card_name="Card name (if reward is a card)",
        max_uses="Maximum number of uses (optional)",
    )
    @app_commands.choices(
        reward_type=[
            app_commands.Choice(name="Random Base Card", value="pack_base"),
            app_commands.Choice(name="Random Icon Card", value="pack_icon"),
            app_commands.Choice(name="Random Event Card", value="pack_event"),
            app_commands.Choice(name="Specific Card", value="card"),
        ]
    )
    @app_commands.check(is_admin_check)
    async def promo_add(
        self,
        interaction: discord.Interaction,
        code: str,
        reward_type: str,
        card_name: str = None,
        max_uses: int = None,
    ):
        """promo_add"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Check if code already exists
                result = await session.execute(
                    select(PromoCode).where(PromoCode.code == code.upper())
                )
                existing = result.scalar_one_or_none()

                if existing:
                    await interaction.followup.send(
                        "❌ This promo code already exists!", ephemeral=True
                    )
                    return

                # Create reward object
                if reward_type == "card":
                    if not card_name:
                        await interaction.followup.send(
                            "❌ Please provide a card name for this reward type!",
                            ephemeral=True,
                        )
                        return

                    # Find card with smart matching
                    result = await session.execute(
                        select(Card)
                        .where(Card.name.ilike(f"%{card_name}%"))
                        .order_by(Card.overall_rating.desc())
                    )
                    cards = result.scalars().all()

                    if not cards:
                        await interaction.followup.send(
                            f"❌ Card '{card_name}' not found!", ephemeral=True
                        )
                        return

                    # Smart matching: exact > prefix > highest OVR
                    card = None
                    card_name_lower = card_name.lower()
                    for c in cards:
                        if c.name.lower() == card_name_lower:
                            card = c
                            break
                    if not card:
                        for c in cards:
                            if c.name.lower().startswith(card_name_lower):
                                card = c
                                break
                    if not card:
                        card = cards[0]

                    if len(cards) > 1:
                        logger.warning(
                            f"Multiple cards found for '{card_name}', using best match: {card.name}"
                        )

                    reward = {"type": "card", "card_id": card.id}
                else:
                    pack_type = reward_type.replace("pack_", "")
                    reward = {"type": "pack", "pack_type": pack_type}

                # Create promo code
                promo = PromoCode(
                    code=code.upper(),
                    reward=reward,
                    max_uses=max_uses,
                    current_uses=0,
                    used_by=[],
                    active=True,
                )
                session.add(promo)
                await session.commit()

                embed = discord.Embed(
                    title="✅ Promo Code Added!",
                    description=f"Code: **{code.upper()}**",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Reward", value=reward_type, inline=True)
                if max_uses:
                    embed.add_field(name="Max Uses", value=str(max_uses), inline=True)

                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in promo_add: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while adding the promo code.", ephemeral=True
            )

    @app_commands.command(
        name="promo_remove", description="[ADMIN] Remove a promo code"
    )
    @app_commands.describe(code="The promo code to remove")
    @app_commands.check(is_admin_check)
    async def promo_remove(self, interaction: discord.Interaction, code: str):
        """promo_remove"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(PromoCode).where(PromoCode.code == code.upper())
                )
                promo = result.scalar_one_or_none()

                if not promo:
                    await interaction.followup.send(
                        "❌ Promo code not found!", ephemeral=True
                    )
                    return

                await session.delete(promo)
                await session.commit()

                embed = discord.Embed(
                    title="✅ Promo Code Removed!",
                    description=f"Code **{code.upper()}** has been removed.",
                    color=discord.Color.green(),
                )

                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in promo_remove: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while removing the promo code.", ephemeral=True
            )

    @app_commands.command(name="logo_add", description="[ADMIN] Add a logo to the game")
    @app_commands.describe(
        name="Name of the logo",
        bonus="OVR bonus (1, 2, or 3)",
        rarity="Rarity of the logo",
    )
    @app_commands.choices(
        rarity=[
            app_commands.Choice(name="Common (+1 OVR)", value="common"),
            app_commands.Choice(name="Rare (+2 OVR)", value="rare"),
            app_commands.Choice(name="Legendary (+3 OVR)", value="legendary"),
        ]
    )
    @app_commands.check(is_admin_check)
    async def logo_add(
        self, interaction: discord.Interaction, name: str, bonus: int, rarity: str
    ):
        """Add a logo to the game"""
        # Defer immediately to avoid interaction timeout
        await interaction.response.defer(ephemeral=False)

        if bonus not in [1, 2, 3]:
            await interaction.followup.send(
                "❌ Bonus must be 1, 2, or 3!", ephemeral=True
            )
            return

        async with AsyncSessionLocal() as session:
            # Check if logo exists
            result = await session.execute(select(Logo).where(Logo.name == name))
            existing = result.scalar_one_or_none()

            if existing:
                await interaction.followup.send(
                    "❌ A logo with this name already exists!", ephemeral=True
                )
                return

            # Create logo
            rarity_enum = LogoRarity[rarity.upper()]
            new_logo = Logo(name=name, rarity=rarity_enum, bonus=bonus)
            session.add(new_logo)
            await session.commit()

            embed = discord.Embed(
                title="✅ Logo Added!",
                description=f"**{name}** ({rarity}) - +{bonus} OVR",
                color=discord.Color.green(),
            )

            await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="logo_remove", description="[ADMIN] Remove a logo from the game"
    )
    @app_commands.describe(name="Name of the logo to remove")
    @app_commands.check(is_admin_check)
    async def logo_remove(self, interaction: discord.Interaction, name: str):
        """logo_remove"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Logo).where(Logo.name.ilike(f"%{name}%"))
                )
                logo = result.scalar_one_or_none()

                if not logo:
                    await interaction.followup.send(
                        f"❌ Logo '{name}' not found!", ephemeral=True
                    )
                    return

                await session.delete(logo)
                await session.commit()

                embed = discord.Embed(
                    title="✅ Logo Removed!",
                    description=f"**{logo.name}** has been removed from the game.",
                    color=discord.Color.green(),
                )

                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in logo_remove: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while removing the logo.", ephemeral=True
            )

    @app_commands.command(
        name="admin_manage",
        description="[ADMIN] Grant or revoke admin status to a user",
    )
    @app_commands.describe(
        user="The user to grant or revoke admin status",
        action="Grant or revoke admin status",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Grant Admin", value="grant"),
            app_commands.Choice(name="Revoke Admin", value="revoke"),
        ]
    )
    async def admin_manage(
        self, interaction: discord.Interaction, user: discord.User, action: str
    ):
        """Manage admin status for users"""
        # Check if user can manage admins
        if not await can_manage_admins(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to manage admins! Only bot owners and existing admins can use this command.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            async with AsyncSessionLocal() as session:
                # Get or create user with proper initialization
                result = await session.execute(select(User).where(User.id == user.id))
                db_user = result.scalar_one_or_none()

                if not db_user:
                    db_user = User(
                        id=user.id,
                        username=user.name,
                        is_admin=False,
                        cards_collected=0,
                    )
                    session.add(db_user)
                    await session.flush()

                if action == "grant":
                    if db_user.is_admin:
                        await interaction.followup.send(
                            f"ℹ️ {user.mention} is already an admin!", ephemeral=True
                        )
                        return

                    db_user.is_admin = True
                    embed = discord.Embed(
                        title="✅ Admin Granted!",
                        description=f"**{user.mention}** has been granted admin status!",
                        color=discord.Color.green(),
                    )
                else:  # revoke
                    if not db_user.is_admin:
                        await interaction.followup.send(
                            f"ℹ️ {user.mention} is not an admin!", ephemeral=True
                        )
                        return

                    # Prevent revoking bot owner's admin (extra safety)
                    if await interaction.client.is_owner(user):
                        await interaction.followup.send(
                            "❌ Cannot revoke admin status from bot owner!",
                            ephemeral=True,
                        )
                        return

                    # Prevent revoking your own admin status
                    if user.id == interaction.user.id:
                        await interaction.followup.send(
                            "❌ You cannot revoke your own admin status!",
                            ephemeral=True,
                        )
                        return

                    db_user.is_admin = False
                    embed = discord.Embed(
                        title="✅ Admin Revoked!",
                        description=f"**{user.mention}** has had their admin status revoked.",
                        color=discord.Color.orange(),
                    )

                await session.commit()
                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in admin_manage: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while managing admin status.", ephemeral=True
            )

    # Removed sync_commands - use bot owner commands for tree sync instead
    # The previous implementation would overwrite guild-specific command trees

    @app_commands.command(
        name="stop_match",
        description="[ADMIN] Force stop an active match in this channel",
    )
    @app_commands.check(is_admin_check)
    async def stop_match(self, interaction: discord.Interaction):
        """Force stop an active match"""
        await interaction.response.defer(ephemeral=True)

        try:
            # Get the match cog
            match_cog = self.bot.get_cog("MatchCog")
            if not match_cog:
                await interaction.followup.send(
                    "❌ Match system is not available!", ephemeral=True
                )
                return

            # Check if there's an active match in this channel
            match_state = await match_cog._get_match_state(interaction.channel_id)
            if not match_state:
                await interaction.followup.send(
                    "❌ There is no active match in this channel!", ephemeral=True
                )
                return

            # Delete the match state
            await match_cog._delete_match_state(interaction.channel_id)

            # Delete all active matches from database for this channel
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(ActiveMatch).where(
                        ActiveMatch.channel_id == interaction.channel_id
                    )
                )
                active_matches = result.scalars().all()
                for active_match in active_matches:
                    await session.delete(active_match)
                if active_matches:
                    await session.commit()

            # Get player mentions
            player1 = await self.bot.fetch_user(match_state.player1_id)
            player2 = await self.bot.fetch_user(match_state.player2_id)

            embed = discord.Embed(
                title="🛑 Match Stopped",
                description=f"The match between {player1.mention} and {player2.mention} has been forcefully stopped by an admin.",
                color=discord.Color.orange(),
            )

            await interaction.followup.send(embed=embed)

            # Notify in channel
            await interaction.channel.send(embed=embed)

        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in stop_match: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while stopping the match.", ephemeral=True
            )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Handle app command errors for this cog"""
        if isinstance(error, app_commands.CheckFailure):
            # Provide helpful error message when admin check fails
            logger.info(
                f"Admin check failed for user {interaction.user.id} ({interaction.user}) in command {interaction.command.name if interaction.command else 'unknown'}"
            )

            # Try to send an error message
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ You don't have permission to use this command!\n\n"
                        "**To use admin commands, you need one of the following:**\n"
                        "• Discord Server Administrator permission\n"
                        "• Guild Owner status\n"
                        "• Database admin status (granted via `/admin_manage`)\n"
                        "• Bot Owner status",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        "❌ You don't have permission to use this command!\n\n"
                        "**To use admin commands, you need one of the following:**\n"
                        "• Discord Server Administrator permission\n"
                        "• Guild Owner status\n"
                        "• Database admin status (granted via `/admin_manage`)\n"
                        "• Bot Owner status",
                        ephemeral=True,
                    )
            except Exception as e:
                logger.error(f"Error sending CheckFailure message: {e}", exc_info=True)
            return  # Don't re-raise, we've handled it

        # For other errors, log and let the global handler deal with it
        logger.error(f"Unhandled app command error in AdminCog: {error}", exc_info=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
