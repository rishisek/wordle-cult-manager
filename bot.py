import discord, asyncio
from discord.ext import commands, tasks

import sqlite3
import re
import random

import os, dotenv
dotenv.load_dotenv()

########
import datetime, pytz
tz = pytz.timezone("America/Chicago")
reset_time = datetime.time(hour=00, minute=00, tzinfo=tz)
reminder_time = datetime.time(hour=12, minute=00, tzinfo=tz)
deadline_time = datetime.time(hour=13, minute=00, tzinfo=tz)
#######

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)

@bot.event
async def on_ready():
    global guild, win_role, lose_role, chl_announce, chl_scores
    guild = bot.get_guild(int(os.getenv("SERVER_ID")))
    win_role = guild.get_role(int(os.getenv("ROLE_ID_WIN")))
    lose_role = guild.get_role(int(os.getenv("ROLE_ID_LOSE")))
    chl_announce = bot.get_channel(int(os.getenv("CHANNEL_ID_ANNOUNCEMENTS")))
    chl_scores = bot.get_channel(int(os.getenv("CHANNEL_ID_SCORES")))

con = sqlite3.connect("wordlecult.db")
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS scores(user, day, score, is_hard, is_timely, UNIQUE(user, day))")

allow_all = discord.AllowedMentions.all()
allow_none = discord.AllowedMentions.none()

high = low = None
lock = False
with open('day.txt') as f:
    day = int(f.read().strip())

@tasks.loop(time=reminder_time)
async def remind() -> None:
    await chl_announce.send(
            "@everyone Reminder to submit your scores in time! You have one hour left.",
            allowed_mentions=allow_all)

@tasks.loop(time=deadline_time)
async def deadline() -> None:
    global lock
    lock = True
    winners, losers = get_standings()

    for w in winners:
        await chl_announce.guild.get_member(w).add_roles(win_role)
    for l in losers:
        await chl_announce.guild.get_member(l).add_roles(lose_role)

    await chl_announce.send(
            f"We have our results! <@&{win_role.id}> are:\n"
            f"{chr(10).join(get_user_mentions(winners))}\n"
            f"They will be choosing guesses for <@&{lose_role.id}>:\n"
            f"{chr(10).join(get_user_mentions(losers))}\n",
            allowed_mentions=allow_all)

@tasks.loop(time=reset_time)
async def reset() -> None:
    global high, low, lock, day
    high = low = None
    lock = False
    with open('day.txt', 'r+') as f:
        day = int(f.read().strip())
    day += 1
    open('day.txt', 'w').close()
    with open('day.txt', 'w') as f:
        f.write(str(day))

    for m in win_role.members:
        await m.remove_roles(win_role)
    for m in lose_role.members:
        await m.remove_roles(lose_role)

@bot.event
async def setup_hook():
    global day, high, low
    cur.row_factory = None
    high, low = cur.execute(f'SELECT MIN(score), MAX(score) FROM scores WHERE day = {day}').fetchone()
    if low == -1:
        low = 7
    reset.start()
    remind.start()
    deadline.start()


@bot.listen('on_message')
async def handle_score(message):
    global high, low, lock, day
    if message.author == bot.user:
        return
    if message.channel != chl_scores:
        return

    match = re.search(r'^Wordle (1,[0-9]{3}) ([1-6X])/6', message.content)
    if match is None:
        return

    msg_day = int(match.group(1).replace(',', ''))
    if msg_day < day:
        return await chl_scores.send(
            f"<@{message.author.id}> Stuck in the past? We're on Wordle {day}.",
            allowed_mentions=allow_all)
    elif msg_day > day + 1:
        return await chl_scores.send(
            f"<@{message.author.id}> Whoa, slow down. We're on Wordle {day}.",
            allowed_mentions=allow_all)
    elif msg_day == day + 1:
        await chl_scores.send(
            f"<@{message.author.id}> I'm writing that down, but we're still on Wordle {day}. "
            "You'll see your score on the leaderboard when we catch up :thumbs_up:",
            allowed_mentions=allow_all)

    score = match.group(2)
    match = re.search(rf'{score}/6\*', message.content)
    hard = match is not None
    if hard:
        await message.add_reaction('\U0001F975')
        await message.add_reaction('\U0001F913')

    score = int(score) if score.isnumeric() else 7
    try:
        cur.execute(f"INSERT INTO scores VALUES ({message.author.id}, {msg_day}, {score}, {hard}, {not lock})")
        con.commit()
    except sqlite3.IntegrityError:
        return await chl_scores.send(
            f"<@{message.author.id}> No second chances! "
            f"We can all see your score already: `$board {message.author.name}`",
                allowed_mentions=allow_all)

    if lock is True:
        return await chl_scores.send(
            f"<@{message.author.id}> Sure, I'll write that down, but you're late "
            "- we had to finish up for today without you :/",
                allowed_mentions=allow_all)

    if high is None:
        high = low = score
    elif score < high:
        high = score
    elif score > low:
        low = score

    await chl_scores.send(
            f"{random.choice(['Gotcha', 'Cool,', 'kk'])} <@{message.author.id}>: {score if score <= 6 else 'X'}/6",
            allowed_mentions=allow_none)

def get_standings():
    global high, low, day
    if high is None:
        return [], []
    cur.row_factory = lambda cursor, row: row[0]
    winners = cur.execute(f'SELECT user FROM scores WHERE day = {day} AND score = {high}').fetchall()
    losers = cur.execute(f'SELECT user FROM scores WHERE day = {day} AND score = {low}').fetchall()
    return winners, losers

def get_user_mentions(user_list):
    return list(map(lambda id: f'<@{id}>', user_list))

def get_bot_score_response():
    random.seed(day)
    distrib = {
        "Me? A 1/6, like always. There's a reason I don't put myself on the leaderboard, you know.": 2,
        "The perfect 1/6. My gift from the Old Ones :squid:": 2,
        ("ok don't tell anyone... im an X for today. "
        "kind of embarrassing huh. no shot im writing that down.\n\n"
         "talk and i'll find you."): 1
    }
    options = []
    for resp, wt in distrib.items():
        for _ in range(wt):
            options.append(resp)
    return random.choice(options)

@bot.command()
async def leaderboard(ctx, *args):
    global high, low

    if len(args) > 1:
        return await ctx.send("Nope - try `$leaderboard` or `$leaderboard <username>`.")
    if len(args) == 1:
        user = ctx.guild.get_member_named(args[0])
        if user is None:
            return await ctx.send("Who? :thinking:")
        elif user == bot.user:
            random.seed(day)
            return await ctx.send(get_bot_score_response())
        cur.row_factory = lambda cursor, row: row[0]
        score = cur.execute(f'SELECT score FROM scores WHERE day = {day} and user = {user.id}').fetchone()
        if score is None:
            return await ctx.send(f"Hell if I know, haven't seen <@{user.id}> today :timer:", allowed_mentions=allow_none)
        return await ctx.send(f"{args[0]} is a {score if score > 0 else 'X'}/6 today.")

    winners, losers = get_standings()
    if len(winners) == 0:
        return await ctx.send("No clue yet :shrug:")
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

bot.run(os.getenv('DISCORD_BOT_TOKEN'))
