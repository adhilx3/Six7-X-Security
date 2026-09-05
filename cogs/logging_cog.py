import datetime

import discord
from discord.ext import commands

from utils.storage import get_guild_config


async def send_log(bot: commands.Bot, guild: discord.Guild, embed: discord.Embed):
    """Utility other cogs can import to push an embed to the configured log channel."""
    config = get_guild_config(guild.id)
    channel_id = config.get("log_channel_id")
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


class LoggingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=False)
        content = message.content or "*[no text content / embed / attachment]*"
        if len(content) > 1000:
            content = content[:1000] + "..."
        embed.add_field(name="Content", value=content, inline=False)
        await send_log(self.bot, message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.guild is None or before.content == after.content:
            return
        embed = discord.Embed(
            title="✏️ Message Edited",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="Author", value=f"{before.author} ({before.author.id})", inline=False)
        embed.add_field(name="Channel", value=before.channel.mention, inline=False)
        before_content = (before.content or "*empty*")[:512]
        after_content = (after.content or "*empty*")[:512]
        embed.add_field(name="Before", value=before_content, inline=False)
        embed.add_field(name="After", value=after_content, inline=False)
        await send_log(self.bot, before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        account_age = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days
        embed = discord.Embed(
            title="📥 Member Joined",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="Member", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="Account Age", value=f"{account_age} days", inline=True)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        if account_age < 7:
            embed.add_field(name="⚠️ Warning", value="This is a very new account.", inline=False)
        await send_log(self.bot, member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="📤 Member Left / Removed",
            color=discord.Color.dark_grey(),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="Member", value=f"{member} ({member.id})", inline=False)
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            embed.add_field(name="Roles", value=", ".join(roles), inline=False)
        await send_log(self.bot, member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🔨 Member Banned",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
        await send_log(self.bot, guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🔓 Member Unbanned",
            color=discord.Color.teal(),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
        await send_log(self.bot, guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
