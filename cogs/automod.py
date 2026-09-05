import datetime
import re
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

from utils.storage import get_guild_config
from cogs.logging_cog import send_log

INVITE_RE = re.compile(r"(discord\.gg/|discord(?:app)?\.com/invite/)([a-zA-Z0-9-]+)")


def is_exempt(member: discord.Member, config: dict) -> bool:
    if member.guild_permissions.administrator:
        return True
    if member.id in config.get("whitelist_user_ids", []):
        return True
    member_role_ids = {r.id for r in member.roles}
    if member_role_ids.intersection(config.get("whitelist_role_ids", [])):
        return True
    return False


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> user_id -> deque of message timestamps, for spam detection
        self.message_history: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))

    async def _take_action(self, message: discord.Message, reason: str, delete: bool = True):
        if delete:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

        embed = discord.Embed(
            title="🚨 AutoMod Action",
            description=reason,
            color=discord.Color.red(),
        )
        embed.add_field(name="User", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=False)
        if message.content:
            embed.add_field(name="Content", value=message.content[:1000], inline=False)
        await send_log(self.bot, message.guild, embed)

    async def _check_spam(self, message: discord.Message, config: dict) -> bool:
        settings = config["automod"]
        history = self.message_history[message.guild.id][message.author.id]
        now = time.time()
        history.append(now)

        window = settings["spam_time_window"]
        while history and now - history[0] > window:
            history.popleft()

        if len(history) >= settings["spam_message_count"]:
            history.clear()
            await self._take_action(
                message,
                f"Sent {settings['spam_message_count']}+ messages within {window}s (spam).",
            )
            try:
                await message.author.timeout(
                    discord.utils.utcnow() + datetime.timedelta(minutes=10),
                    reason="Auto-mod: spam",
                )
            except (discord.Forbidden, AttributeError, TypeError):
                pass
            return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        config = get_guild_config(message.guild.id)
        if not config["automod"]["enabled"]:
            return
        if is_exempt(message.author, config):
            return

        settings = config["automod"]

        # 1. Banned words
        if settings["banned_words"]:
            content_lower = message.content.lower()
            for word in settings["banned_words"]:
                if word.lower() in content_lower:
                    await self._take_action(message, f"Used a banned word: `{word}`")
                    return

        # 2. Invite links
        if settings["block_invites"]:
            match = INVITE_RE.search(message.content)
            if match:
                invite_code = match.group(2)
                if invite_code not in settings.get("invite_whitelist", []):
                    await self._take_action(message, "Posted a Discord invite link.")
                    return

        # 3. Mass mentions
        mention_count = len(message.mentions) + len(message.role_mentions)
        if mention_count >= settings["max_mentions"]:
            await self._take_action(message, f"Mass mention ({mention_count} mentions).")
            return

        # 4. Excessive caps (only check messages of meaningful length)
        letters = [c for c in message.content if c.isalpha()]
        if len(letters) >= 10:
            caps_percent = sum(1 for c in letters if c.isupper()) / len(letters) * 100
            if caps_percent >= settings["max_caps_percent"]:
                await self._take_action(message, f"Excessive caps ({caps_percent:.0f}%).")
                return

        # 5. Spam / rate limiting
        await self._check_spam(message, config)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
