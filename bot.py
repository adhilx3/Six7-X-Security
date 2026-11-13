import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.database import init_db, migrate_from_json
from cogs.verification import VerifyView

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("security-bot")

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True          # required for join/leave events, account age checks, anti-nuke
intents.message_content = True  # required to scan message text for automod


class SecurityBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        # 1. Initialize SQLite storage and migrate legacy JSON if present
        await init_db()
        migrated = await migrate_from_json()
        if migrated:
            log.info(f"Migrated {migrated} guild configuration(s) from JSON to SQLite.")

        # 2. Load modular extensions
        for ext in (
            "cogs.antinuke",
            "cogs.moderation",
            "cogs.automod",
            "cogs.antiraid",
            "cogs.verification",
            "cogs.logging_cog",
            "cogs.config_cog",
        ):
            await self.load_extension(ext)
            log.info(f"Loaded extension: {ext}")

        # 4. Sync application slash commands
        synced = await self.tree.sync()
        log.info(f"Synced {len(synced)} slash command(s).")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="for threats 🛡️")
        )


async def main():
    if not TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and add your bot token."
        )
    bot = SecurityBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
