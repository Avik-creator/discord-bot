import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from database.database import AsyncSessionLocal
from database.models import Card, CardType, Collection, PromoCode, User
from utils.api_football import APIFootball
from utils.embeds import EmbedBuilder
from utils.match_helpers import is_user_in_active_match

logger = logging.getLogger("discord_bot")


class CardTypeSelectView(discord.ui.View):
    """View for selecting card type filter"""

    def __init__(self, user_id: int, player_name: str, cards_by_type: dict, cog):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.player_name = player_name
        self.cards_by_type = cards_by_type
        self.cog = cog

        # Build dropdown options based on available card types
        options = []
        if cards_by_type.get(CardType.BASE):
            options.append(
                discord.SelectOption(
                    label="Base Cards",
                    value="base",
                    description=f"{len(cards_by_type[CardType.BASE])} base card(s)",
                    emoji="⚽",
                )
            )
        if cards_by_type.get(CardType.ICON):
            options.append(
                discord.SelectOption(
                    label="Icon Cards",
                    value="icon",
                    description=f"{len(cards_by_type[CardType.ICON])} icon card(s)",
                    emoji="🌟",
                )
            )
        if cards_by_type.get(CardType.EVENT):
            options.append(
                discord.SelectOption(
                    label="Event Cards",
                    value="event",
                    description=f"{len(cards_by_type[CardType.EVENT])} event card(s)",
                    emoji="🎉",
                )
            )

        if len(options) > 1:
            select = discord.ui.Select(
                placeholder="Choose card type to display...",
                options=options,
                min_values=1,
                max_values=1,
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        """Handle card type selection"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ This menu is not for you!", ephemeral=True
            )
            return

        await interaction.response.defer()

        # Get selected card type
        selected_type = interaction.data["values"][0]
        type_map = {
            "base": CardType.BASE,
            "icon": CardType.ICON,
            "event": CardType.EVENT,
        }
        card_type = type_map[selected_type]

        # Get cards of selected type
        cards = self.cards_by_type.get(card_type, [])
        if not cards:
            await interaction.followup.send(
                f"❌ No {selected_type} cards found!", ephemeral=True
            )
            return

        # Use smart matching on the filtered list
        card = self.cog._smart_match_card(cards, self.player_name)

        # Show the card
        embed = EmbedBuilder.card_embed(card, show_full=True)

        # Disable the view
        for item in self.children:
            item.disabled = True

        await interaction.edit_original_response(embed=embed, view=self)


class CollectionCog(commands.Cog):
    """Collection and pack commands"""

    def __init__(self, bot):
        self.bot = bot
        self.api_football = APIFootball()

        # Validate cooldown config on startup
        required_cooldowns = [
            "daily_pack",
            "weekly_pack",
            "event_pack",
            "premium_pack",
            "booster_pack",
            "vote",
        ]
        for cooldown_type in required_cooldowns:
            if cooldown_type not in config.COOLDOWNS:
                logger.warning(
                    f"Missing cooldown config for '{cooldown_type}' - defaulting to 0 seconds"
                )
                config.COOLDOWNS[cooldown_type] = 0

    async def _get_or_create_user(
        self, session: AsyncSession, user_id: int, username: str
    ) -> User:
        """Get or create user within an active session. Centralized to avoid duplication."""
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(id=user_id, username=username)
            session.add(user)
            await session.flush()

        return user

    def _smart_match_card(self, card_list, player_name: str):
        """Smart match a card from a list using exact > prefix > highest OVR logic"""
        player_name_lower = player_name.lower()

        # Try exact match first
        for card in card_list:
            if card.name.lower() == player_name_lower:
                return card

        # Try prefix match
        for card in card_list:
            if card.name.lower().startswith(player_name_lower):
                return card

        # Fallback to first match (should be highest OVR if sorted)
        return card_list[0] if card_list else None

    def _format_time(self, seconds: int) -> str:
        """Format seconds into a human-readable time string (e.g., '23h 45m 30s' or '6d 12h 30m')"""
        if seconds <= 0:
            return "0s"

        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 and days == 0:  # Only show seconds if less than a day
            parts.append(f"{secs}s")

        return " ".join(parts) if parts else "0s"

    async def _check_cooldown(self, user: User, cooldown_type: str) -> tuple[bool, int]:
        """Check if cooldown has expired. Returns (can_use, seconds_remaining)"""
        cooldown_field = f"{cooldown_type}_cooldown"
        last_use = getattr(user, cooldown_field, None)

        if last_use is None:
            return True, 0

        cooldown_duration = config.COOLDOWNS.get(cooldown_type, 0)
        # Use discord.utils.utcnow() for timezone-aware datetime
        now = discord.utils.utcnow()
        # Ensure last_use is timezone-aware (if it's naive, make it aware)
        if last_use.tzinfo is None:
            from datetime import timezone

            last_use = last_use.replace(tzinfo=timezone.utc)
        time_passed = (now - last_use).total_seconds()

        if time_passed >= cooldown_duration:
            return True, 0
        else:
            return False, int(cooldown_duration - time_passed)

    async def _give_random_card(
        self, session: AsyncSession, user: User, card_type: CardType = None
    ) -> Card:
        """Give a random card to user (does NOT commit - caller must commit).
        Assumes user is attached to the provided session.
        """
        # Get random card - handle None card_type meaning "any type"
        card = await self.api_football.get_random_card_from_db(session, card_type)

        if not card:
            return None

        # Add to collection
        collection_entry = Collection(user_id=user.id, card_id=card.id)
        session.add(collection_entry)

        # Update user stats (user is already attached to session)
        user.cards_collected += 1

        # DO NOT commit here - let the caller commit after interaction succeeds
        return card

    @app_commands.command(name="pack", description="Open a pack")
    @app_commands.describe(pack_type="Type of pack to open")
    @app_commands.choices(
        pack_type=[
            app_commands.Choice(name="Daily Pack (Base Players)", value="daily_pack"),
            app_commands.Choice(name="Weekly Pack (Icons)", value="weekly_pack"),
            app_commands.Choice(name="Event Pack", value="event_pack"),
            app_commands.Choice(name="Premium Pack (Icon/Event)", value="premium_pack"),
            app_commands.Choice(name="Booster Pack (Base)", value="booster_pack"),
        ]
    )
    async def open_pack(self, interaction: discord.Interaction, pack_type: str):
        """Open different types of packs"""
        # Defer immediately to avoid timeout
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Check if user is in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, interaction.user.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ You cannot open packs while in an active match!\n"
                        f"Please complete your match in <#{channel_id}> first.",
                        ephemeral=True,
                    )
                    return

                # Get or create user
                user = await self._get_or_create_user(
                    session, interaction.user.id, interaction.user.name
                )
</parameter>


                # Check cooldown
                can_use, seconds_remaining = await self._check_cooldown(user, pack_type)

                if not can_use:
                    time_str = self._format_time(seconds_remaining)
                    pack_name = pack_type.replace("_", " ").title()
                    await interaction.followup.send(
                        f"⏰ **{pack_name}** is on cooldown!\n"
                        f"⏳ Time remaining: **{time_str}**",
                        ephemeral=True,
                    )
                    return

                # Determine card type based on pack
                card_type_map = {
                    "daily_pack": CardType.BASE,
                    "weekly_pack": CardType.ICON,
                    "event_pack": CardType.EVENT,
                    "premium_pack": None,  # None means random from any type
                    "booster_pack": CardType.BASE,
                }

                card_type = card_type_map.get(pack_type)

                # Give random card (pass user object, not user_id)
                card = await self._give_random_card(session, user, card_type)

                if not card:
                    # Don't apply cooldown on failure
                    await interaction.followup.send(
                        "❌ Error opening pack. No cards available. Please try again later.",
                        ephemeral=True,
                    )
                    return

                # Update cooldown ONLY on success
                cooldown_field = f"{pack_type}_cooldown"
                setattr(user, cooldown_field, discord.utils.utcnow())

                # Show card FIRST before committing
                embed = EmbedBuilder.card_embed(card, show_full=True)
                embed.title = f"📦 Pack Opened - {card.name}!"
                embed.color = discord.Color.gold()

                # Commit first, then send response
                await session.commit()
                await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in open_pack: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ An error occurred while opening the pack. Please try again.",
                    ephemeral=True,
                )
            except:
                logger.error("Failed to send error message to user")

    @app_commands.command(name="collection", description="View your card collection")
    @app_commands.describe(
        sort_by="How to sort your collection",
        event_filter="Filter by event type",
        page="Page number",
    )
    @app_commands.choices(
        sort_by=[
            app_commands.Choice(name="Overall Rating", value="ovr"),
            app_commands.Choice(name="Alphabetical", value="name"),
            app_commands.Choice(name="Recently Obtained", value="date"),
        ]
    )
    async def view_collection(
        self,
        interaction: discord.Interaction,
        sort_by: str = "ovr",
        event_filter: str = None,
        page: int = 1,
    ):
        """View user's card collection"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Get user
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()

                if not user:
                    await interaction.followup.send(
                        "You don't have any cards yet! Use `/pack` or catch spawned cards.",
                        ephemeral=True,
                    )
                    return

                # Get collection
                query = (
                    select(Card, Collection)
                    .join(Collection, Card.id == Collection.card_id)
                    .where(Collection.user_id == interaction.user.id)
                )

                # Apply event filter (validate it's not garbage)
                if event_filter:
                    # Optionally validate event_filter is a valid CardType
                    query = query.where(Card.event_type == event_filter)

                # Apply sorting
                if sort_by == "ovr":
                    query = query.order_by(Card.overall_rating.desc())
                elif sort_by == "name":
                    query = query.order_by(Card.name)
                elif sort_by == "date":
                    query = query.order_by(Collection.obtained_at.desc())

                result = await session.execute(query)
                card_data = result.all()

                if not card_data:
                    await interaction.followup.send(
                        "No cards found with those filters!", ephemeral=True
                    )
                    return

                cards = [card for card, _ in card_data]

                # Pagination
                cards_per_page = 10
                total_pages = (len(cards) + cards_per_page - 1) // cards_per_page
                page = max(1, min(page, total_pages))

                start_idx = (page - 1) * cards_per_page
                end_idx = start_idx + cards_per_page
                page_cards = cards[start_idx:end_idx]

                embed = EmbedBuilder.collection_embed(
                    user, page_cards, page, total_pages, sort_by
                )

                await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in collection: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while loading your collection.", ephemeral=True
            )

    @view_collection.autocomplete("event_filter")
    async def event_filter_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        """Autocomplete for event filter with smart filtering"""
        try:
            async with AsyncSessionLocal() as session:
                # Get distinct event types from user's collection
                query = (
                    select(Card.event_type)
                    .distinct()
                    .join(Collection, Card.id == Collection.card_id)
                    .where(Collection.user_id == interaction.user.id)
                    .where(Card.event_type.isnot(None))
                )

                if current and current.strip():
                    query = query.where(Card.event_type.ilike(f"%{current}%"))

                result = await session.execute(query)
                all_event_types = [et for et in result.scalars().all() if et]

                if not current or not current.strip():
                    # Show all event types alphabetically
                    event_types = sorted(all_event_types)[:25]
                else:
                    # Smart sorting: exact match > starts with > contains
                    current_lower = current.lower()
                    exact = [e for e in all_event_types if e.lower() == current_lower]
                    starts = [
                        e
                        for e in all_event_types
                        if e.lower().startswith(current_lower) and e not in exact
                    ]
                    contains = [
                        e
                        for e in all_event_types
                        if current_lower in e.lower()
                        and e not in exact
                        and e not in starts
                    ]

                    event_types = (exact + starts + contains)[:25]

                return [
                    app_commands.Choice(name=event_type, value=event_type)
                    for event_type in event_types
                ]
        except Exception as e:
            logger.error(f"Error in event_filter_autocomplete: {e}", exc_info=True)
            return []

    @app_commands.command(name="show", description="Display a specific card in detail")
    @app_commands.describe(player_name="Name of the player to show")
    async def show_card(self, interaction: discord.Interaction, player_name: str):
        """Show detailed card information with card type filter"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Find ALL matching cards in user's collection
                result = await session.execute(
                    select(Card, Collection)
                    .join(Collection, Card.id == Collection.card_id)
                    .where(Collection.user_id == interaction.user.id)
                    .where(Card.name.ilike(f"%{player_name}%"))
                    .order_by(Card.overall_rating.desc())
                )
                card_data_list = result.all()

                if not card_data_list:
                    await interaction.followup.send(
                        f"You don't have a card matching '{player_name}'!",
                        ephemeral=True,
                    )
                    return

                # Group cards by type
                cards_by_type = {}
                for card_obj, _ in card_data_list:
                    if card_obj.card_type not in cards_by_type:
                        cards_by_type[card_obj.card_type] = []
                    cards_by_type[card_obj.card_type].append(card_obj)

                # If only one type exists, show it directly
                if len(cards_by_type) == 1:
                    card_type = list(cards_by_type.keys())[0]
                    cards = cards_by_type[card_type]
                    card = self._smart_match_card(cards, player_name)
                    embed = EmbedBuilder.card_embed(card, show_full=True)
                    await interaction.followup.send(embed=embed)
                else:
                    # Multiple types - show dropdown selector
                    view = CardTypeSelectView(
                        interaction.user.id, player_name, cards_by_type, self
                    )

                    # Create initial embed showing all types available
                    embed = discord.Embed(
                        title=f"🎴 Multiple Card Types Found for '{player_name}'",
                        description="Select which card type you want to view:",
                        color=discord.Color.blue(),
                    )

                    # Add fields for each type
                    if cards_by_type.get(CardType.BASE):
                        cards = cards_by_type[CardType.BASE]
                        embed.add_field(
                            name="⚽ Base Cards",
                            value=f"{len(cards)} card(s) - Highest: {cards[0].overall_rating} OVR",
                            inline=False,
                        )
                    if cards_by_type.get(CardType.ICON):
                        cards = cards_by_type[CardType.ICON]
                        embed.add_field(
                            name="🌟 Icon Cards",
                            value=f"{len(cards)} card(s) - Highest: {cards[0].overall_rating} OVR",
                            inline=False,
                        )
                    if cards_by_type.get(CardType.EVENT):
                        cards = cards_by_type[CardType.EVENT]
                        event_names = ", ".join(
                            set(c.event_type or "Special" for c in cards[:3])
                        )
                        embed.add_field(
                            name="🎉 Event Cards",
                            value=f"{len(cards)} card(s) - Highest: {cards[0].overall_rating} OVR\nEvents: {event_names}",
                            inline=False,
                        )

                    await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error in show_card: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while showing the card.", ephemeral=True
            )

    @app_commands.command(name="stats", description="View your statistics")
    async def view_stats(self, interaction: discord.Interaction):
        """Show user statistics"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()

            if not user:
                await interaction.followup.send(
                    "You don't have any stats yet! Start playing to build your profile.",
                    ephemeral=True,
                )
                return

            embed = EmbedBuilder.stats_embed(user)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in stats: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while loading your stats.", ephemeral=True
            )

    @app_commands.command(name="vote", description="Vote for the bot to get a reward")
    async def vote_reward(self, interaction: discord.Interaction):
        """Give reward for voting"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Get or create user
                user = await self._get_or_create_user(
                    session, interaction.user.id, interaction.user.name
                )

                # Check cooldown
                can_use, seconds_remaining = await self._check_cooldown(user, "vote")

                if not can_use:
                    time_str = self._format_time(seconds_remaining)
                    await interaction.followup.send(
                        f"⏰ You can vote again in **{time_str}**", ephemeral=True
                    )
                    return

                # Give random base card (pass user object)
                card = await self._give_random_card(session, user, CardType.BASE)

                if not card:
                    # Don't apply cooldown on failure
                    await interaction.followup.send(
                        "❌ Error giving reward. No cards available.", ephemeral=True
                    )
                    return

                # Update cooldown ONLY on success
                user.vote_cooldown = discord.utils.utcnow()

                embed = discord.Embed(
                    title="🗳️ Thanks for Voting!",
                    description=f"You received **{card.name}** ({card.overall_rating} OVR)!",
                    color=discord.Color.gold(),
                )
                embed.add_field(
                    name="Vote Link",
                    value="[Vote on top.gg](https://top.gg)",
                    inline=False,
                )

                # Commit first, then send
                await session.commit()
                await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in vote_reward: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ An error occurred while processing your vote.", ephemeral=True
                )
            except:
                logger.error("Failed to send error message to user")

    @app_commands.command(name="promo", description="Redeem a promo code")
    @app_commands.describe(code="The promo code to redeem")
    async def redeem_promo(self, interaction: discord.Interaction, code: str):
        """Redeem a promo code"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Check if user is in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, interaction.user.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ You cannot redeem promo codes while in an active match!\n"
                        f"Please complete your match in <#{channel_id}> first.",
                        ephemeral=True,
                    )
                    return

                # Get or create user
                user = await self._get_or_create_user(
                    session, interaction.user.id, interaction.user.name
                )

                # Find promo code
                result = await session.execute(
                    select(PromoCode).where(PromoCode.code == code.upper())
                )
                promo = result.scalar_one_or_none()

                if not promo or not promo.active:
                    await interaction.followup.send(
                        "❌ Invalid or expired promo code!", ephemeral=True
                    )
                    return

                # Safely handle used_by (could be None, list, or JSON)
                used_by = promo.used_by if promo.used_by is not None else []
                if not isinstance(used_by, list):
                    # Handle case where DB stores as JSON string or weird type
                    logger.error(f"Promo code used_by is not a list: {type(used_by)}")
                    used_by = []

                # Check if user already used this code
                if interaction.user.id in used_by:
                    await interaction.followup.send(
                        "❌ You have already used this promo code!", ephemeral=True
                    )
                    return

                # Safely handle current_uses null
                current_uses = (
                    promo.current_uses if promo.current_uses is not None else 0
                )

                # Check max uses
                if promo.max_uses and current_uses >= promo.max_uses:
                    await interaction.followup.send(
                        "❌ This promo code has reached its usage limit!",
                        ephemeral=True,
                    )
                    return

                # Check expiration
                if promo.expires_at and discord.utils.utcnow() > promo.expires_at:
                    await interaction.followup.send(
                        "❌ This promo code has expired!", ephemeral=True
                    )
                    return

                # Give reward based on type
                reward = promo.reward
                reward_text = ""

                if reward["type"] == "card":
                    # Give specific card
                    card_id = reward.get("card_id")
                    if card_id:
                        collection_entry = Collection(user_id=user.id, card_id=card_id)
                        session.add(collection_entry)
                        user.cards_collected += 1
                        reward_text = "You received a special card!"

                elif reward["type"] == "pack":
                    # Give pack type
                    pack_type = reward.get("pack_type", "base")
                    card_type_map = {
                        "base": CardType.BASE,
                        "icon": CardType.ICON,
                        "event": CardType.EVENT,
                    }
                    card = await self._give_random_card(
                        session, user, card_type_map.get(pack_type, CardType.BASE)
                    )
                    if card:
                        reward_text = (
                            f"You received **{card.name}** ({card.overall_rating} OVR)!"
                        )

                # Update promo code usage safely
                promo.current_uses = current_uses + 1
                used_by.append(interaction.user.id)
                promo.used_by = used_by

                embed = discord.Embed(
                    title="🎁 Promo Code Redeemed!",
                    description=reward_text,
                    color=discord.Color.gold(),
                )

                # Commit first, then send
                await session.commit()
                await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in redeem_promo: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ An error occurred while redeeming the promo code.",
                    ephemeral=True,
                )
            except:
                logger.error("Failed to send error message to user")

    @app_commands.command(name="buy", description="Get a link to the Patreon store")
    async def buy_link(self, interaction: discord.Interaction):
        """Show Patreon store link"""
        embed = discord.Embed(
            title="🛒 Support the Bot!",
            description=f"Visit our Patreon store to get premium packs and exclusive cards!\n\n"
            f"[Visit Store]({config.PATREON_STORE_LINK})",
            color=discord.Color.orange(),
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="pack_timer",
        description="Check cooldown timers for daily and weekly packs",
    )
    async def pack_timer(self, interaction: discord.Interaction):
        """Show cooldown timers for daily and weekly packs"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Get or create user
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()

                if not user:
                    user = User(id=interaction.user.id, username=interaction.user.name)
                    session.add(user)
                    await session.flush()

                # Check cooldowns for daily and weekly packs
                daily_can_use, daily_remaining = await self._check_cooldown(
                    user, "daily_pack"
                )
                weekly_can_use, weekly_remaining = await self._check_cooldown(
                    user, "weekly_pack"
                )

                embed = discord.Embed(
                    title="⏰ Pack Cooldown Timers",
                    description="Check when you can open your next packs!",
                    color=discord.Color.blue(),
                )

                # Daily pack status
                if daily_can_use:
                    daily_status = "✅ **Ready to open!**"
                else:
                    daily_time = self._format_time(daily_remaining)
                    daily_status = f"⏳ **{daily_time}** remaining"

                embed.add_field(name="📦 Daily Pack", value=daily_status, inline=False)

                # Weekly pack status
                if weekly_can_use:
                    weekly_status = "✅ **Ready to open!**"
                else:
                    weekly_time = self._format_time(weekly_remaining)
                    weekly_status = f"⏳ **{weekly_time}** remaining"

                embed.add_field(
                    name="📦 Weekly Pack", value=weekly_status, inline=False
                )

                await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in pack_timer: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ An error occurred while checking pack timers.", ephemeral=True
                )
            except:
                logger.error("Failed to send error message to user")


async def setup(bot):
    await bot.add_cog(CollectionCog(bot))
