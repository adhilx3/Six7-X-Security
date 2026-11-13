import datetime
import hashlib
import re
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

from utils.database import get_automod_config
from cogs.logging_cog import send_log

INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.gg/|discord(?:app)?\.com/invite/|discord\.me/|discord\.io/)([a-zA-Z0-9-]+)",
    re.IGNORECASE,
)

LEGIT_DOMAINS = (
    "https://discord.com/",
    "https://discord.gg/",
    "https://www.discord.com/",
    "https://www.discord.gg/",
    "https://steamcommunity.com/",
    "https://www.steamcommunity.com/",
)

SCAM_REGEXES = [
    re.compile(
        r"https?://(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:discorcl|dlscord|disord|discordapp|nitro-gift|discord-nitro|steamcommunity-tradeoffer)[^\s]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://(?:www\.)?[a-zA-Z0-9-]+\.(?:gift|xyz|top|site|club|ru|info|online|link)/(?:nitro|claim|free|airdrop)[^\s]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://(?:www\.)?steamcommunity[^\s/]*-(?:gift|trade|promo)[^\s]*",
        re.IGNORECASE,
    ),
]

DANGEROUS_EXTENSIONS = {".exe", ".scr", ".bat", ".cmd", ".vbs", ".msi", ".ps1", ".jar"}

LEET_MAP = str.maketrans({
    "@": "a",
    "$": "s",
    "!": "i",
    "0": "o",
    "1": "l",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "8": "b",
})


def normalize_text(text: str) -> str:
    return text.translate(LEET_MAP)


def is_word_match(content: str, banned_words: list[str]) -> bool:
    if not banned_words:
        return False
    norm = normalize_text(content)
    for word in banned_words:
        escaped = re.escape(word.lower())
        pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
        if pattern.search(content) or pattern.search(norm):
            return True
    return False


def is_scam_link(content: str) -> bool:
    for word in content.split():
        if word.startswith("http://") or word.startswith("https://"):
            if any(word.lower().startswith(legit) for legit in LEGIT_DOMAINS):
                continue
            for pattern in SCAM_REGEXES:
                if pattern.search(word):
                    return True
    return False


def is_dangerous_attachment(attachments: list) -> str | None:
    for att in attachments:
        filename = getattr(att, "filename", "")
        for ext in DANGEROUS_EXTENSIONS:
            if filename.lower().endswith(ext):
                return filename
    return None


def is_exempt(member: discord.Member, config: dict) -> bool:
    if getattr(member.guild_permissions, "administrator", False):
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
        self.db_path = getattr(bot, "db_path", None)
        # guild_id -> user_id -> deque of message timestamps
        self.message_history: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))
        # guild_id -> user_id -> deque of (hash, timestamp)
        self.duplicate_history: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))

    async def _take_action(
        self,
        message: discord.Message,
        reason: str,
        timeout_duration: datetime.timedelta = None,
        delete: bool = True,
    ):
        if delete:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

        if timeout_duration and hasattr(message.author, "timeout"):
            try:
                until = datetime.datetime.now(datetime.timezone.utc) + timeout_duration
                await message.author.timeout(until, reason=f"AutoMod: {reason}")
            except (discord.Forbidden, discord.HTTPException):
                pass

        embed = discord.Embed(
            title="🚨 AutoMod Action",
            description=reason,
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="User", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Channel", value=getattr(message.channel, "mention", str(message.channel)), inline=False)
        if message.content:
            embed.add_field(name="Content", value=message.content[:1000], inline=False)
        await send_log(self.bot, message.guild, embed)

    async def _check_spam(self, message: discord.Message, settings: dict) -> bool:
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
                f"Sent {settings['spam_message_count']}+ messages within {window}s (rate spam).",
                timeout_duration=datetime.timedelta(minutes=10),
            )
            return True
        return False

    async def _check_duplicates(self, message: discord.Message) -> bool:
        if not message.content or len(message.content.strip()) < 4:
            return False
        content_hash = hashlib.sha256(message.content.strip().lower().encode("utf-8")).hexdigest()
        now = time.time()
        history = self.duplicate_history[message.guild.id][message.author.id]
        history.append((content_hash, now))

        # Check within 10 seconds window
        while history and now - history[0][1] > 10:
            history.popleft()

        same_hashes = sum(1 for h, _ in history if h == content_hash)
        if same_hashes >= 3:
            history.clear()
            await self._take_action(
                message,
                "Repeated duplicate messages (copypasta spam).",
                timeout_duration=datetime.timedelta(minutes=10),
            )
            return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if getattr(message.author, "bot", False) or message.guild is None:
            return

        config = await get_automod_config(message.guild.id, db_path=self.db_path)
        if not config["enabled"]:
            return
        if is_exempt(message.author, config):
            return

        # 1. Dangerous attachment check
        if config.get("block_attachments", 1) and message.attachments:
            dangerous_file = is_dangerous_attachment(message.attachments)
            if dangerous_file:
                await self._take_action(message, f"Uploaded dangerous executable file: `{dangerous_file}`")
                try:
                    await message.author.send(
                        f"Your file `{dangerous_file}` was removed from **{message.guild.name}** for security reasons (executable files are not permitted)."
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

        # 2. Phishing / Scam links check
        if config.get("block_scams", 1) and is_scam_link(message.content):
            await self._take_action(
                message,
                "Posted a known phishing/scam or token stealer link.",
                timeout_duration=datetime.timedelta(hours=1),
            )
            return

        # 3. Banned words filter (regex word boundaries)
        if config.get("banned_words") and is_word_match(message.content, config["banned_words"]):
            await self._take_action(message, "Used a prohibited word/phrase.")
            return

        # 4. Invite links
        if config.get("block_invites", 1):
            match = INVITE_RE.search(message.content)
            if match:
                invite_code = match.group(1)
                if invite_code not in config.get("invite_whitelist", []):
                    await self._take_action(message, "Posted an unauthorized Discord invite link.")
                    return

        # 5. Mass mentions
        mention_count = len(message.mentions) + len(message.role_mentions)
        if mention_count >= config.get("max_mentions", 5):
            await self._take_action(message, f"Mass mention ({mention_count} mentions).")
            return

        # 6. Excessive caps
        letters = [c for c in message.content if c.isalpha()]
        if len(letters) >= 10:
            caps_percent = sum(1 for c in letters if c.isupper()) / len(letters) * 100
            if caps_percent >= config.get("max_caps_percent", 70):
                await self._take_action(message, f"Excessive caps ({caps_percent:.0f}%).")
                return

        # 7. Duplicate copypasta spam
        if config.get("block_duplicates", 1) and await self._check_duplicates(message):
            return

        # 8. Rate spam
        await self._check_spam(message, config)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if getattr(message.author, "bot", False) or message.guild is None:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        created_at = getattr(message, "created_at", None)
        if not created_at:
            return

        delta_seconds = (now - created_at).total_seconds()
        if delta_seconds < 15 and (message.mentions or message.role_mentions):
            targets = [m.mention for m in message.mentions] + [r.mention for r in message.role_mentions]
            embed = discord.Embed(
                title="👻 Ghostping Detected",
                description=f"{message.author.mention} mentioned user(s)/role(s) and deleted the message {int(delta_seconds)}s later.",
                color=discord.Color.purple(),
                timestamp=now,
            )
            embed.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=True)
            embed.add_field(name="Channel", value=getattr(message.channel, "mention", str(message.channel)), inline=True)
            embed.add_field(name="Mentioned", value=", ".join(targets[:10]), inline=False)
            if message.content:
                embed.add_field(name="Content", value=message.content[:1000], inline=False)
            await send_log(self.bot, message.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
