from __future__ import annotations

import re
from typing import Dict, Optional, Sequence, Union

import discord
from discord.ext import commands


def role_mention_cleanup(message: discord.Message) -> Union[str, None]:

    content = message.content

    if not content:
        return None

    assert isinstance(content, str), "Message.content got screwed somehow..."  # nosec

    if message.guild is None:
        return content

    transformations = {
        re.escape("<@&{0.id}>".format(role)): "@" + role.name
        for role in message.role_mentions
    }

    def repl(obj):
        return transformations.get(re.escape(obj.group(0)), "")

    pattern = re.compile("|".join(transformations.keys()))
    result = pattern.sub(repl, content)

    return result


def embed_from_msg(message: discord.Message) -> discord.Embed:
    channel = message.channel
    assert isinstance(channel, discord.TextChannel), "mypy"  # nosec
    guild = channel.guild
    content = role_mention_cleanup(message)
    author = message.author
    avatar = author.avatar_url
    footer = f"Said in {guild.name} #{channel.name}"

    try:
        color = author.color if author.color.value != 0 else None
    except AttributeError:  # happens if message author not in guild anymore.
        color = None
    em = discord.Embed(description=content, timestamp=message.created_at)
    if color:
        em.color = color

    em.set_author(name=f"{author.name} ▸", url=f"{message.jump_url}", icon_url=avatar)
    em.set_footer(icon_url=guild.icon_url, text=footer)
    if message.attachments:
        a = message.attachments[0]
        fname = a.filename
        url = a.url
        if fname.split(".")[-1] in ["png", "jpg", "gif", "jpeg"]:
            em.set_image(url=url)
        else:
            em.add_field(
                name="Message has an attachment", value=f"[{fname}]({url})", inline=True
            )
    return em


async def eligible_channels(ctx: commands.Context) -> Sequence[discord.TextChannel]:
    """
    Get's the eligible channels to check
    """

    ret = []

    guild = ctx.guild
    author = ctx.author
    channel = ctx.channel
    assert (  # nosec
        guild is not None
        and isinstance(author, discord.Member)
        and isinstance(channel, discord.TextChannel)
    ), "mypy... I'd love for a DMContext + GuildContext split actually"

    is_owner = await ctx.bot.is_owner(author)
    needed_perms = discord.Permissions()
    needed_perms.read_messages = True
    needed_perms.read_message_history = True
    guild_order = [g for g in ctx.bot.guilds if g != ctx.guild]
    guild_order.insert(0, guild)

    for g in ctx.bot.guilds:
        chans = [
            c
            for c in g.text_channels
            if c.permissions_for(g.me) >= needed_perms
            and (is_owner or c.permissions_for(author) >= needed_perms)
        ]
        if ctx.channel in chans:
            chans.remove(channel)
            chans.insert(0, channel)

        ret.extend(chans)

    return ret


async def find_msg_fallback(
    channels: Sequence[discord.TextChannel], idx: int
) -> Optional[discord.Message]:

    for channel in channels:
        try:
            m = await channel.fetch_message(idx)
        except discord.HTTPException:
            continue
        else:
            return m

    return None


# noinspection PyProtectedMember
async def find_messages(
    ctx: commands.Context,
    ids: Sequence[int],
    channels: Optional[Sequence[discord.TextChannel]] = None,
) -> Sequence[discord.Message]:

    channels = channels or await eligible_channels(ctx)

    # dict order preserved py3.6+
    accumulated: Dict[int, Optional[discord.Message]] = {i: None for i in ids}

    # This can find ineligible messages, but we strip later to avoid researching
    accumulated.update({m.id: m for m in ctx.bot.cached_messages if m.id in ids})

    for i in ids:
        if accumulated[i] is not None:
            continue
        m = await find_msg_fallback(channels, i)
        if m:
            accumulated[i] = m

    filtered = [m for m in accumulated.values() if m and m.channel in channels]
    return filtered
