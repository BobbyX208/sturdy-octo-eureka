import asyncio
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional
import subprocess
import os
from pathlib import Path

import discord
from discord.ext import commands

from config.settings import Config
from core.cooldowns import CooldownManager
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
from middleware.sim_context import SimContext


def git_pull():
    """Auto-pull latest changes from private repo using token in URL."""
    try:
        git_username = os.getenv("GIT_USERNAME")
        git_token = os.getenv("GIT_TOKEN")
        git_repo_url = os.getenv("GIT_REPO_URL", "https://github.com/yourusername/simcoin.git")
        
        repo_path = os.path.dirname(os.path.abspath(__file__))
        
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", repo_path],
            capture_output=True
        )
        
        if git_username and git_token:
            auth_url = git_repo_url.replace("https://", f"https://{git_username}:{git_token}@")
        else:
            auth_url = git_repo_url
        
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            cwd=repo_path
        )
        
        if result.returncode != 0:
            print("📦 Cloning repository...")
            clone_result = subprocess.run(
                ["git", "clone", auth_url, "."],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if clone_result.returncode != 0:
                print(f"❌ Clone failed: {clone_result.stderr}")
                return False
            print("✅ Repository cloned")
            return True
        
        print("🔄 Pulling latest changes...")
        pull_result = subprocess.run(
            ["git", "pull", auth_url],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        if pull_result.returncode != 0:
            print(f"⚠️ Pull failed: {pull_result.stderr}")
            return False
        
        if pull_result.stdout:
            print(pull_result.stdout)
        
        if "Already up to date" in pull_result.stdout:
            print("✅ Already up to date")
            return False
        
        print("✅ Updates pulled successfully")
        return True
        
    except Exception as e:
        print(f"❌ Git error: {e}")
        return False


class HotReloader:
    def __init__(self, bot):
        self.bot = bot
        self.watched_files = {}
        self.last_checked = {}
    
    async def watch_cogs(self):
        """Watch for file changes and auto-reload cogs"""
        cogs_dir = Path(__file__).parent / "cogs"
        
        while not self.bot.is_closed():
            for file in cogs_dir.glob("*.py"):
                if file.name.startswith("__"):
                    continue
                
                mod_time = file.stat().st_mtime
                cog_name = file.stem
                
                if cog_name in self.last_checked and self.last_checked[cog_name] != mod_time:
                    self.bot.logger.info(f"🔄 Detected change in {cog_name}.py, reloading...")
                    try:
                        await self.bot.reload_extension(f"cogs.{cog_name}")
                        self.bot.logger.info(f"✅ Reloaded {cog_name}")
                    except Exception as e:
                        self.bot.logger.error(f"❌ Failed to reload {cog_name}: {e}")
                
                self.last_checked[cog_name] = mod_time
            
            await asyncio.sleep(2)
    
    async def git_pull_loop(self):
        """Auto git pull every 60 seconds"""
        while not self.bot.is_closed():
            await asyncio.sleep(60)
            
            try:
                result = subprocess.run(
                    ["git", "pull", "--no-commit", "--no-ff"],
                    cwd=Path(__file__).parent,
                    capture_output=True,
                    text=True
                )
                
                if "Already up to date" not in result.stdout and result.returncode == 0:
                    self.bot.logger.info("📦 Git pull completed, reloading all cogs...")
                    
                    for cog in list(self.bot.extensions.keys()):
                        try:
                            await self.bot.reload_extension(cog)
                            self.bot.logger.info(f"✅ Reloaded {cog}")
                        except Exception as e:
                            self.bot.logger.error(f"❌ Failed to reload {cog}: {e}")
                    
                    self.bot.logger.info("✅ Hot reload complete")
                    
            except Exception as e:
                self.bot.logger.error(f"Git pull failed: {e}")


class SimCoinBot(commands.Bot):
    """Main SimCoin bot instance with service layer architecture."""
    
    def __init__(self):
        """Initialize the bot with intents and configuration."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=commands.when_mentioned_or(Config.COMMAND_PREFIX),
            intents=intents,
            help_command=None,
            activity=discord.Game(name="/start | Simora City"),
            status=discord.Status.online
        )
        
        self.logger = setup_logger("simcoin_bot")
        self.start_time = datetime.now(timezone.utc)
        
        self.db: Optional[DatabasePool] = None
        self.event_bus: Optional[EventBus] = None
        self.cache: Optional[CacheManager] = None
        self.services: Optional[ServiceContainer] = None
        self.hot_reloader: Optional[HotReloader] = None
        
    async def setup_hook(self) -> None:
        """Set up bot services, database connection, and load cogs."""
        try:
            self.logger.info("Starting bot setup hook...")
            
            self.logger.info("Connecting to database...")
            self.db = await DatabasePool.connect(Config.DATABASE_URL)
            self.logger.info("Database connection established")
            
            self.logger.info("Initializing cache...")
            self.cache = CacheManager()

            self.logger.info("Initializing cooldown...")
            self.cooldowns = CooldownManager(self.db, self.cache)
            
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
                economy=EconomyService(self.db, self.cache, self.event_bus, self.cooldowns),
                crime=CrimeService(self.db, self.cache, self.event_bus, self.cooldowns),
                market=MarketService(self.db, self.cache, self.event_bus),
                investment=InvestmentService(self.db, self.cache, self.event_bus, self.cooldowns),
                business=BusinessService(self.db, self.cache, self.event_bus),
                faction=FactionService(self.db, self.cache, self.event_bus),
                ai=ai_service,
                image=image_service,
                world=WorldService(self.db, ai_service, self.cache, self.event_bus)
            )
            self.logger.info("Service container initialized")
            
            await self.load_all_cogs()
            
            self.hot_reloader = HotReloader(self)
            asyncio.create_task(self.hot_reloader.watch_cogs())
            asyncio.create_task(self.hot_reloader.git_pull_loop())
            self.logger.info("Hot reloader started")
            
            self.logger.info("Syncing application commands...")
            await self.sync_commands()
            self.logger.info("Application commands synced")
            
            self.logger.info("Starting background tasks...")
            await self.start_background_tasks()

            self.ctx = SimContext(self.services, self.db, self.cache)
            
            self.logger.info("Bot setup completed successfully")
            
        except Exception as e:
            self.logger.error(f"Setup hook failed: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    async def load_all_cogs(self) -> None:
        """Auto-discover and load all cog files from the cogs directory."""
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
                module_path = f"cogs.{cog_name}"
                
                try:
                    module = importlib.import_module(module_path)
                    
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, commands.Cog) and attr is not commands.Cog:
                            await self.add_cog(attr(self))
                            loaded_cogs.append(cog_name)
                            self.logger.info(f"Loaded cog: {cog_name}")
                            break
                    else:
                        if hasattr(module, "setup"):
                            await module.setup(self)
                            loaded_cogs.append(cog_name)
                            self.logger.info(f"Loaded cog via setup: {cog_name}")
                        else:
                            self.logger.warning(f"No cog class or setup function found in {cog_name}")
                            failed_cogs.append(f"{cog_name} (no cog class)")
                            
                except Exception as e:
                    error_msg = f"Failed to load cog {cog_name}: {e}"
                    self.logger.error(error_msg)
                    self.logger.error(traceback.format_exc())
                    failed_cogs.append(f"{cog_name} ({str(e)})")
        
        self.logger.info(f"Loaded {len(loaded_cogs)} cogs: {', '.join(loaded_cogs)}")
        if failed_cogs:
            self.logger.warning(f"Failed to load {len(failed_cogs)} cogs: {', '.join(failed_cogs)}")
    
    async def sync_commands(self) -> None:
        """Sync application commands with Discord."""
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
    
    async def start_background_tasks(self) -> None:
        """Initialize and start all background tasks."""
        from core.tasks import BackgroundTaskManager
        
        try:
            self.task_manager = BackgroundTaskManager(self)
            await self.task_manager.start_all()
            self.logger.info("Background tasks started")
        except Exception as e:
            self.logger.error(f"Failed to start background tasks: {e}")
            self.logger.error(traceback.format_exc())
    
    async def on_ready(self) -> None:
        """Called when the bot is ready and connected to Discord."""
        try:
            self.logger.info(f"Bot is ready!")
            self.logger.info(f"Logged in as: {self.user.name} (ID: {self.user.id})")
            self.logger.info(f"Connected to {len(self.guilds)} guilds")
            self.logger.info(f"Latency: {round(self.latency * 1000)}ms")
            
            await self.change_presence(
                activity=discord.Game(name=f"/start | {len(self.guilds)} servers"),
                status=discord.Status.online
            )
            
        except Exception as e:
            self.logger.error(f"Error in on_ready: {e}")
            self.logger.error(traceback.format_exc())
    
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Global error handler for prefix commands."""
        try:
            if isinstance(error, commands.CommandNotFound):
                return
            
            elif isinstance(error, commands.MissingPermissions):
                await ctx.send(f"❌ You don't have permission to use this command: {error}")
                
            elif isinstance(error, commands.BotMissingPermissions):
                await ctx.send(f"❌ I don't have the required permissions: {error}")
                
            elif isinstance(error, commands.CommandOnCooldown):
                remaining = round(error.retry_after, 1)
                await ctx.send(f"⏰ Command on cooldown. Try again in {remaining} seconds.")
                
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f"❌ Missing required argument: {error.param.name}")
                
            elif isinstance(error, commands.BadArgument):
                await ctx.send(f"❌ Invalid argument: {error}")
                
            else:
                self.logger.error(f"Unhandled command error in {ctx.command}: {error}")
                self.logger.error(traceback.format_exc())
                await ctx.send("❌ An unexpected error occurred. The developers have been notified.")
                
        except Exception as e:
            self.logger.error(f"Error in on_command_error: {e}")
            self.logger.error(traceback.format_exc())
    
    async def on_application_command_error(
        self, 
        interaction: discord.Interaction, 
        error: discord.app_commands.AppCommandError
    ) -> None:
        """Global error handler for slash commands."""
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            if isinstance(error, discord.app_commands.CommandOnCooldown):
                remaining = round(error.retry_after, 1)
                await interaction.followup.send(
                    f"⏰ Command on cooldown. Try again in {remaining} seconds.",
                    ephemeral=True
                )
                
            elif isinstance(error, discord.app_commands.MissingPermissions):
                await interaction.followup.send(
                    f"❌ You don't have permission to use this command: {error}",
                    ephemeral=True
                )
                
            elif isinstance(error, discord.app_commands.BotMissingPermissions):
                await interaction.followup.send(
                    f"❌ I don't have the required permissions: {error}",
                    ephemeral=True
                )
                
            elif isinstance(error, discord.app_commands.CheckFailure):
                await interaction.followup.send(
                    "❌ You don't meet the requirements to use this command.",
                    ephemeral=True
                )
                
            else:
                self.logger.error(f"Unhandled application command error: {error}")
                self.logger.error(traceback.format_exc())
                await interaction.followup.send(
                    "❌ An unexpected error occurred. The developers have been notified.",
                    ephemeral=True
                )
                
        except Exception as e:
            self.logger.error(f"Error in on_application_command_error: {e}")
            self.logger.error(traceback.format_exc())
            
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An unexpected error occurred.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An unexpected error occurred.",
                        ephemeral=True
                    )
            except:
                pass
    
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Called when the bot joins a new guild."""
        try:
            self.logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
            self.logger.info(f"Guild members: {guild.member_count}")
            
            if self.event_bus:
                await self.event_bus.fire("guild.joined", {
                    "guild_id": guild.id,
                    "guild_name": guild.name,
                    "member_count": guild.member_count
                })
            
            await self.change_presence(
                activity=discord.Game(name=f"/start | {len(self.guilds)} servers"),
                status=discord.Status.online
            )
            
        except Exception as e:
            self.logger.error(f"Error in on_guild_join: {e}")
            self.logger.error(traceback.format_exc())
    
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Called when the bot is removed from a guild."""
        try:
            self.logger.info(f"Removed from guild: {guild.name} (ID: {guild.id})")
            
            if self.event_bus:
                await self.event_bus.fire("guild.left", {
                    "guild_id": guild.id,
                    "guild_name": guild.name
                })
            
            await self.change_presence(
                activity=discord.Game(name=f"/start | {len(self.guilds)} servers"),
                status=discord.Status.online
            )
            
        except Exception as e:
            self.logger.error(f"Error in on_guild_remove: {e}")
            self.logger.error(traceback.format_exc())
    
    async def close(self) -> None:
        """Clean shutdown of the bot and all services."""
        try:
            self.logger.info("Shutting down bot...")
            
            if hasattr(self, 'task_manager') and self.task_manager:
                await self.task_manager.stop_all()
                self.logger.info("Background tasks stopped")
            
            if self.db:
                await self.db.close()
                self.logger.info("Database connection closed")
            
            if self.event_bus:
                await self.event_bus.close()
                self.logger.info("Event bus closed")
            
            if self.services and hasattr(self.services, 'ai'):
                await self.services.ai.close()
                self.logger.info("AI service closed")
            
            await super().close()
            self.logger.info("Bot shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            self.logger.error(traceback.format_exc())
    
    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        """Global error handler for all events."""
        self.logger.error(f"Error in event {event_method}")
        self.logger.error(traceback.format_exc())


def main() -> None:
    """Main entry point for the bot."""
    try:
        print("=" * 50)
        print("🚀 SimCoin Bot Starting...")
        print("=" * 50)
        
        updated = git_pull()
        
        if updated:
            print("\n⚠️ Updates were pulled!")
            print("   If dependencies changed, run: pip install -r requirements.txt")
            print("   Consider restarting to ensure all changes are applied.\n")
        
        bot = SimCoinBot()
        bot.run(Config.DISCORD_TOKEN)
        
    except discord.LoginFailure:
        print("❌ Invalid Discord token. Please check your DISCORD_TOKEN in config.")
        sys.exit(1)
        
    except discord.PrivilegedIntentsRequired:
        print("❌ Privileged intents required but not enabled in Discord Developer Portal.")
        print("   Please enable Server Members Intent and Message Content Intent.")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()