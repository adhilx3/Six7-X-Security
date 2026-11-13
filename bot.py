import asyncio
import logging
import os
import time

import discord
from discord.ext import commands
from dotenv import load_dotenv
import uvicorn

from utils.database import init_db, migrate_from_json
from cogs.verification import VerifyView
from web.app import create_app

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
        self.start_time: float = time.time()
        self.web_server: uvicorn.Server = None
        self.web_task: asyncio.Task = None

    async def setup_hook(self):
        self.start_time = time.time()

        # 1. Initialize SQLite storage and migrate legacy JSON if present
        await init_db()
        migrated = await migrate_from_json()
        if migrated:
            log.info(f"Migrated {migrated} guild configuration(s) from JSON to SQLite.")

        # 2. Launch embedded web dashboard
        port = int(os.getenv("PORT", 8080))
        web_app = create_app(self)
        config = uvicorn.Config(
            web_app,
            host="0.0.0.0",
            port=port,
            loop="asyncio",
            log_level="warning"
        )
        self.web_server = uvicorn.Server(config)
        self.web_task = asyncio.create_task(self.web_server.serve())
        log.info(f"Web Dashboard online at http://0.0.0.0:{port}")

        # 3. Load modular extensions
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

    async def close(self):
        if self.web_server:
            self.web_server.should_exit = True
        await super().close()

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="for threats 🛡️")
        )


Six7Bot = SecurityBot


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
