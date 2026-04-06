import asyncio
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands

from config.settings import Config
from core.logger import setup_logger
from core.cache import CacheManager
from database.connection import DatabasePool
from events.bus import EventBus
from services import ServiceContainer
from services.player_service import PlayerService
from services.economy_service import EconomyService
from services.crime_service import CrimeService
from services.market_service import MarketService
from services.investment_service import InvestmentService
from services.business_service import BusinessService
from services.faction_service import FactionService
from services.ai_service import AIService
from services.image_service import ImageService
from services.world_service import WorldService


class ModBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        super().__init__(
            command_prefix=commands.when_mentioned_or("smod!"),
            intents=intents,
            help_command=None,
            activity=discord.Game(name="Moderating Simora City"),
            status=discord.Status.idle
        )

        self.logger = setup_logger("simcoin_mod")
        self.start_time = datetime.now(timezone.utc)

        self.db: Optional[DatabasePool] = None
        self.cache: Optional[CacheManager] = None
        self.event_bus: Optional[EventBus] = None
        self.services: Optional[ServiceContainer] = None

        self.mod_channel_ids = {
            "alerts": Config.MOD_ALERTS_CHANNEL_ID,
            "daily": Config.MOD_DAILY_CHANNEL_ID,
            "actions": Config.MOD_ACTIONS_CHANNEL_ID,
            "tickets": None
        }

    async def setup_hook(self) -> None:
        try:
            self.logger.info("Starting Mod Bot setup hook...")

            self.logger.info("Connecting to database...")
            self.db = await DatabasePool.connect(Config.DATABASE_URL)
            self.logger.info("Database connection established")

            self.logger.info("Initializing cache...")
            self.cache = CacheManager()

            self.logger.info("Initializing event bus...")
            self.event_bus = EventBus()
            await self.event_bus.initialize()
            self.logger.info("Event bus initialized")

            self.logger.info("Initializing AI service...")
            ai_service = AIService(
                groq_key=Config.GROQ_API_KEY,
                gemini_key=Config.GEMINI_API_KEY,
                cache_manager=self.cache
            )

            self.logger.info("Initializing image service...")
            image_service = ImageService(cache_manager=self.cache)

            self.logger.info("Initializing service container...")
            self.services = ServiceContainer(
                player=PlayerService(self.db, self.cache, self.event_bus),
                economy=EconomyService(self.db, self.cache, self.event_bus, None),
                crime=CrimeService(self.db, self.cache, self.event_bus, None),
                market=MarketService(self.db, self.cache, self.event_bus),
                investment=InvestmentService(self.db, self.cache, self.event_bus, None),
                business=BusinessService(self.db, self.cache, self.event_bus),
                faction=FactionService(self.db, self.cache, self.event_bus),
                ai=ai_service,
                image=image_service,
                world=WorldService(self.db, ai_service, self.cache, self.event_bus)
            )
            self.logger.info("Service container initialized")

            await self.load_mod_cogs()

            self.logger.info("Syncing mod commands...")
            await self.sync_commands()
            self.logger.info("Mod commands synced")

            self.logger.info("Mod Bot setup completed successfully")

        except Exception as e:
            self.logger.error(f"Setup hook failed: {e}")
            self.logger.error(traceback.format_exc())
            raise

    async def load_mod_cogs(self) -> None:
        import os
        import importlib

        cogs_path = os.path.join(os.path.dirname(__file__), "cogs")

        if not os.path.exists(cogs_path):
            self.logger.warning(f"Cogs directory not found at {cogs_path}")
            return

        loaded_cogs = []
        failed_cogs = []

        for filename in os.listdir(cogs_path):
            if filename.endswith(".py") and not filename.startswith("__"):
                cog_name = filename[:-3]
                module_path = f"mod_bot.cogs.{cog_name}"

                try:
                    module = importlib.import_module(module_path)

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, commands.Cog) and attr is not commands.Cog:
                            await self.add_cog(attr(self))
                            loaded_cogs.append(cog_name)
                            self.logger.info(f"Loaded mod cog: {cog_name}")
                            break
                    else:
                        if hasattr(module, "setup"):
                            await module.setup(self)
                            loaded_cogs.append(cog_name)
                            self.logger.info(f"Loaded mod cog via setup: {cog_name}")
                        else:
                            self.logger.warning(f"No cog class in {cog_name}")
                            failed_cogs.append(cog_name)

                except Exception as e:
                    self.logger.error(f"Failed to load cog {cog_name}: {e}")
                    failed_cogs.append(cog_name)

        self.logger.info(f"Loaded {len(loaded_cogs)} mod cogs: {loaded_cogs}")
        if failed_cogs:
            self.logger.warning(f"Failed to load: {failed_cogs}")

    async def sync_commands(self) -> None:
        try:
            synced = await self.tree.sync()
            self.logger.info(f"Synced {len(synced)} application commands globally")

            if Config.TEST_GUILD_ID:
                test_guild = discord.Object(id=Config.TEST_GUILD_ID)
                synced_guild = await self.tree.sync(guild=test_guild)
                self.logger.info(f"Synced {len(synced_guild)} application commands to test guild")

        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}")
            self.logger.error(traceback.format_exc())

    async def on_ready(self) -> None:
        self.logger.info("Mod Bot is ready!")
        self.logger.info(f"Logged in as: {self.user.name} (ID: {self.user.id})")
        self.logger.info(f"Connected to {len(self.guilds)} guilds")

        await self.change_presence(
            activity=discord.Game(name=f"Moderating | {len(self.guilds)} servers"),
            status=discord.Status.idle
        )

        if self.mod_channel_ids["actions"]:
            channel = self.get_channel(self.mod_channel_ids["actions"])
            if channel:
                await channel.send("🛡️ **Mod Bot Online**\nMonitoring Simora City...")

    async def on_application_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError
    ) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            if isinstance(error, discord.app_commands.MissingPermissions):
                await interaction.followup.send(
                    "❌ You don't have permission to use this mod command.",
                    ephemeral=True
                )
            elif isinstance(error, discord.app_commands.CheckFailure):
                await interaction.followup.send(
                    "❌ You don't meet the requirements for this command.",
                    ephemeral=True
                )
            else:
                self.logger.error(f"Mod command error: {error}")
                await interaction.followup.send(
                    "❌ An error occurred. Check logs.",
                    ephemeral=True
                )

        except Exception as e:
            self.logger.error(f"Error in error handler: {e}")

    async def close(self) -> None:
        try:
            self.logger.info("Shutting down Mod Bot...")

            if self.db:
                await self.db.close()
                self.logger.info("Database connection closed")

            if self.event_bus:
                await self.event_bus.close()
                self.logger.info("Event bus closed")

            await super().close()
            self.logger.info("Mod Bot shutdown complete")

        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")


def main() -> None:
    try:
        print("=" * 50)
        print("🛡️ SimCoin Mod Bot Starting...")
        print("=" * 50)

        bot = ModBot()
        bot.run(Config.MOD_BOT_TOKEN)

    except discord.LoginFailure:
        print("❌ Invalid Mod Bot token. Check MOD_BOT_TOKEN in config.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to start Mod Bot: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()