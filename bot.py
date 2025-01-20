import discord
from discord.ext import commands, tasks

import re

########
import datetime, pytz
tz = pytz.timezone("America/Chicago")
reset_time = datetime.time(hour=00, minute=00, tzinfo=tz)
reminder_time = datetime.time(hour=12, minute=00, tzinfo=tz)
deadline_time = datetime.time(hour=13, minute=00, tzinfo=tz)
#######

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)

allow_all = discord.AllowedMentions.all()
allow_none = discord.AllowedMentions.none()

user_scores = {}
high = low = None
lock = False
day = None

# chl_announce = 1330747987626037353
chl_announce = 1330716328843284604
@tasks.loop(time=reminder_time)
async def remind() -> None:
    channel = bot.get_channel(chl_announce)
    await channel.send(
            "@everyone Reminder to submit your scores in time! You have one hour left.",
            allowed_mentions=allow_all)

@tasks.loop(time=deadline_time)
async def deadline() -> None:
    global lock
    channel = bot.get_channel(chl_announce)
    lock = True
    winners, losers = get_standings()
    await channel.send(
            "We have our results! <@&1330706546069471252> are:\n"
            f"{chr(10).join(get_user_mentions(winners))}\n"
            "They will be choosing guesses for <@&1330710429642653696>:\n"
            f"{chr(10).join(get_user_mentions(losers))}\n",
            allowed_mentions=allow_all)

@tasks.loop(time=reset_time)
async def reset() -> None:
    global high, low, user_scores, lock
    high = low = None
    user_scores = {}
    lock = False


@bot.event
async def setup_hook():
    reset.start()
    remind.start()
    deadline.start()

@bot.listen('on_message')
async def handle_score(message):
    global high, low, user_scores, lock, day
    if message.author == bot.user:
        return
    if message.channel.id != chl_announce:
        return

    match = re.search(r'^Wordle (1,[0-9]{3}) ([1-6X])/6', message.content)
    if match is None:
        return

    channel = bot.get_channel(chl_announce)
    msg_day = int(match.group(1).replace(',', ''))
    if day is None:
        day = msg_day
    elif day != msg_day:
        return await channel.send(
                f"<@{message.author.id}>, that's not the day we're on - submit your score for Wordle {day} if you have one",
                allowed_mentions=allow_all)

    score = match.group(2)
    match = re.search(rf'{score}/6\*', message.content)
    hard = match is not None
    if hard:
        await message.add_reaction('\U0001F975')
        await message.add_reaction('\U0001F913')

    score = int(score) if score.isnumeric() else 7
    user_scores[message.author.id] = (score, not lock)

    if lock is True:
        return await channel.send(
                f"<@{message.author.id}> Your score has been recorded to the leaderboard, but today's round has ended at 1 PM CST.",
                allowed_mentions=allow_all)

    if high is None:
        high = low = score
    elif score < high:
        high = score
    elif score > low:
        low = score

    await channel.send(
            f"Score recorded for <@{message.author.id}>: {score if score <= 6 else 'X'}/6",
            allowed_mentions=allow_none)

def get_standings():
    global high, low, user_scores
    winners, losers = [], []
    for user, (score, valid) in user_scores.items():
        if not valid:
            continue
        if score == high:
            winners.append(user)
        elif score == low:
            losers.append(user)
    return winners, losers

def get_user_mentions(user_list):
    return list(map(lambda id: f'<@{id}>', user_list))

@bot.command()
async def standings(ctx):
    global high, low
    winners, losers = get_standings()
    if len(winners) == 0:
        return await ctx.send("No submissions yet for today (CST)!")
    if high == 7:
        return await ctx.send(
                "All submissions are X/6 - we're yet to crack the case :mag:",
                allowed_mentions=allow_none)

    standings = (f"Current leaders ({high}/6):\n"
        f"{chr(10).join(get_user_mentions(winners))}\n")

    if high != low:
        standings +=("\n"
            f"On the drawing block ({low if low <= 6 else 'X'}/6):\n"
            f"{chr(10).join(get_user_mentions(losers))}\n")
    await ctx.send(standings, allowed_mentions=allow_none)

import os, dotenv
dotenv.load_dotenv()
bot.run(os.getenv('DISCORD_BOT_TOKEN'))
