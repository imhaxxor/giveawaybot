import discord
from discord.ext import commands
import sqlite3
import asyncio
import re
from datetime import timedelta

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True  # Make sure reactions are enabled
bot = commands.Bot(command_prefix="!", intents=intents)

# Database setup
conn = sqlite3.connect('giveaway.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY,
                prize TEXT,
                message_id INTEGER,
                channel_id INTEGER,
                winner_id INTEGER,
                duration_remaining INTEGER
            )''')
conn.commit()

# Function to parse duration in seconds from strings like "1m", "5m", "1h", "2d"
def parse_duration(duration_str):
    match = re.match(r"(\d+)([smhd])", duration_str)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    
    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    elif unit == "d":
        return value * 86400  # 86400 seconds in a day
    return None

# Function to format the countdown timer
def format_duration(seconds):
    return str(timedelta(seconds=seconds))

# Command to start a giveaway
@bot.command(name="giveaway")
@commands.has_permissions(administrator=True)  # Make sure the command can only be executed by admins
async def giveaway(ctx, prize: str, duration: str):
    # Parse the duration
    duration_seconds = parse_duration(duration)
    if duration_seconds is None or duration_seconds > 8 * 86400:  # 8 days in seconds
        await ctx.send("Invalid duration format! Use formats like `1m` for 1 minute, `10s` for 10 seconds, `1h` for 1 hour, or `2d` for 2 days (max 8 days).")
        return
    # Send the "Giveaway" message above the embed
    await ctx.send("🎉 **Giveaway** 🎉")
    
    # Embed setup with giveaway details
    embed = discord.Embed(
        title=f"**{prize}**",
        description=f"<a:dot:1162288016434417674> React with 🎉 to enter!\n<a:dot:1162288016434417674> Ends in {format_duration(duration_seconds)}",
        color=discord.Color.red()
    )
    embed.set_image(url="https://i.pinimg.com/originals/ff/b1/e1/ffb1e1accc1921830a621663311f6066.gif")
    
    # Add footer to embed
    embed.set_footer(text="1 Winner", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
    
    # Send the embedded giveaway message
    message = await ctx.send(embed=embed)
    await message.add_reaction("🎉")
    
    # Store the giveaway details in the database
    c.execute("INSERT INTO giveaways (prize, message_id, channel_id, duration_remaining) VALUES (?, ?, ?, ?)",
              (prize, message.id, ctx.channel.id, duration_seconds))
    conn.commit()
    
    # Countdown timer
    while duration_seconds > 0:
        await asyncio.sleep(5)
        duration_seconds -= 5
        embed.description = f"<a:dot:1162288016434417674> React with 🎉 to enter!\n<a:dot:1162288016434417674> Ends in {format_duration(duration_seconds)}"
        await message.edit(embed=embed)
        
        # Update the remaining time in the database
        c.execute("UPDATE giveaways SET duration_remaining = ? WHERE message_id = ?", (duration_seconds, message.id))
        conn.commit()
    
    # Final update to indicate giveaway has ended
    embed.description = f"**{prize}**\n<a:dot:1162288016434417674> React with 🎉 to enter!\n<a:dot:1162288016434417674> **Giveaway Ended**"
    await message.edit(embed=embed)
    
    # Fetch message and gather users who reacted
    try:
        message = await ctx.fetch_message(message.id)
        users = []
        
        # Use async for to handle the async generator from `reaction.users`
        async for user in message.reactions[0].users():
            if not user.bot:  # Exclude the bot itself
                users.append(user)
        
        if not users:
            await ctx.send("No participants in the giveaway!")
            return
    except Exception as e:
        await ctx.send(f"Error fetching reactions: {e}")
        return
    
    # Specific winner ID
    winner_id = 1236514106287063041  # Replace this with the actual winner's Discord ID
    winner = ctx.guild.get_member(winner_id) or await bot.fetch_user(winner_id)  # Try to get the user even if they’re not in the server
    
    if winner and winner.id in [user.id for user in users]:
        try:
            # Update the embed with winner's information
            embed.description += f"\n**Winners**:\n <@{winner_id}>"
            await message.edit(embed=embed)

            # Send a winner announcement with a "jump to message" link
            giveaway_url = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{message.id}"
            embed_winner = discord.Embed(
                title="🎉 Congratulations! 🎉",
                description=f"<@{winner_id}> has won the giveaway for **{prize}**! [Jump to Giveaway]({giveaway_url})",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed_winner)
            
            # Update the database with the winner's ID
            c.execute("UPDATE giveaways SET winner_id = ? WHERE message_id = ?", (winner_id, message.id))
            conn.commit()
        except Exception as e:
            await ctx.send(f"Error announcing the winner: {e}")
    else:
        await ctx.send("The specified winner could not be found in the server or didn't participate.")

# Error handling for giveaway command
@giveaway.error
async def giveaway_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !giveaway <prize> <duration>")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use this command.")

# Function to resume giveaways if the bot restarts
async def resume_giveaways():
    c.execute("SELECT * FROM giveaways WHERE duration_remaining > 0")
    ongoing_giveaways = c.fetchall()
    
    for giveaway in ongoing_giveaways:
        message_id, channel_id, prize, duration_remaining = giveaway[2], giveaway[3], giveaway[1], giveaway[5]
        
        channel = bot.get_channel(channel_id)
        if channel is None:
            continue
        
        try:
            message = await channel.fetch_message(message_id)
            embed = discord.Embed(
                title=f"🎉 **{prize}** 🎉",
                description=f"<a:dot:1162288016434417674> React with 🎉 to enter!\n<a:dot:1162288016434417674> Ends in {format_duration(duration_remaining)}",
                color=discord.Color.red()
            )
            embed.set_image(url="https://i.pinimg.com/originals/ff/b1/e1/ffb1e1accc1921830a621663311f6066.gif")  # Set image again
            await message.edit(embed=embed)
            
            # Countdown logic
            while duration_remaining > 0:
                await asyncio.sleep(5)
                duration_remaining -= 5
                embed.description = f"<a:dot:1162288016434417674> React with 🎉 to enter!\n<a:dot:1162288016434417674> Ends in {format_duration(duration_remaining)}"
                await message.edit(embed=embed)

                # Update the remaining time in the database
                c.execute("UPDATE giveaways SET duration_remaining = ? WHERE message_id = ?", (duration_remaining, message.id))
                conn.commit()

            # Final update when giveaway ends
            embed.description = f"**{prize}**\n<a:dot:1162288016434417674> React with 🎉 to enter!\n<a:dot:1162288016434417674> **Giveaway Ended**"
            await message.edit(embed=embed)

            # Fetch users who reacted
            users = []
            async for user in message.reactions[0].users():
                if not user.bot:
                    users.append(user)

            if users:
                winner_id = 1236514106287063041  # Replace this with the actual winner's Discord ID
                winner = channel.guild.get_member(winner_id) or await bot.fetch_user(winner_id)

                if winner and winner.id in [user.id for user in users]:
                    # Update the embed with winner's information
                    embed.description += f"\n**Winners**: <@{winner_id}>"
                    await message.edit(embed=embed)

                    giveaway_url = f"https://discord.com/channels/{channel.id}/{message.id}"
                    embed_winner = discord.Embed(
                        title="🎉 Congratulations! 🎉",
                        description=f"<@{winner_id}> has won the giveaway for **{prize}**! [Jump to Giveaway]({giveaway_url})",
                        color=discord.Color.green()
                    )
                    await channel.send(embed=embed_winner)

                    # Update the database with the winner's ID
                    c.execute("UPDATE giveaways SET winner_id = ? WHERE message_id = ?", (winner_id, message.id))
                    conn.commit()
                else:
                    embed.description += "\n**Winners**: No Winners"
                    await message.edit(embed=embed)
            else:
                embed.description += "\n**Winners**: No Winners"
                await message.edit(embed=embed)

        except Exception as e:
            print(f"Error resuming giveaway: {e}")

# Start the bot
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    await resume_giveaways()

# Run the bot with your token
bot.run('MTI5NzQ0OTM5ODgzNzQ0ODc0NQ.GSOyCP.hMJDHrGQyI1Dt6ABtkhwSrruiJDaPpLWFpxjDc')
