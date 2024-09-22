from Scripts.sendDiscordMessage import send_message
from db import get_engine
import requests
import discord
from discord import app_commands
from discord.ext import commands
import csv
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import sessionmaker, Session
import time
from Models.coins import Coin, CoinHistoric
import asyncio
from dotenv import load_dotenv
import os
from Scripts.get_historic_coin_data import main as get_coin_historic
from Scripts.add_coin import add_coin
from contextlib import contextmanager

# Load environment variables from .env file
ENVIROMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIROMENT == 'development':
    load_dotenv('.env.development', encoding="utf-8-sig")
elif ENVIROMENT == 'production':
    load_dotenv('.env.production', encoding="utf-8-sig")
else:
    load_dotenv(encoding="utf-8-sig")  # Default to a standard .env file

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
API_COIN_INFO_BASE_URL = os.getenv("API_COIN_INFO_BASE_URL")
DISCORD_OWNER_ID= int(os.getenv("DISCORD_OWNER_ID"))
DISCORD_SERVER_ID= int(os.getenv("DISCORD_SERVER_ID"))
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Set up the bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
intents.message_content = True  # Ensure this is enabled if you want to handle commands

@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_csv(filename, data):
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Date", "Open", "Close"])
        for row in data:
            writer.writerow([row['date'], row['open'], row['close']])

def validate_coin(coin,session: Session):
    coin = session.query(Coin).filter(Coin.symbol== coin).first()
    return coin


csv_filename = f"coin_data_{datetime.now().strftime('%Y-%m-%d')}.csv"
coin_name = "BTC"
historic_data = [
    {"date": "2023-09-15", "open": "45,000", "close": "46,500"},
    {"date": "2023-09-16", "open": "46,500", "close": "47,200"},
    {"date": "2023-09-17", "open": "47,200", "close": "46,800"},
    {"date": "2023-09-18", "open": "46,800", "close": "48,000"},
    {"date": "2023-09-19", "open": "48,000", "close": "47,500"},
    {"date": "2023-09-20", "open": "47,500", "close": "48,200"},
    {"date": "2023-09-21", "open": "48,200", "close": "49,000"},
]
create_csv(csv_filename, historic_data)


# Sync and register the slash command

""" guild = discord.Object(id=1230133817537331331)  # Replace with your guild ID
try:
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} commands in the guild: {[cmd.name for cmd in synced]}")
except Exception as e:
    print(f"Error syncing commands: {e}") """


# Define the slash command
# Define a slash command with interval choices
@bot.tree.command(name="daily_report", description="Sends a daily report with open and close coin values.")
@app_commands.describe(coin="The coin to report (e.g., BTC, ETH)", start_date="Start date (dd/mm/yyyy)", end_date="End date (dd/mm/yyyy)", interval="Choose an interval")
@app_commands.choices(interval=[
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Monthly", value="monthly"),
    app_commands.Choice(name="Yearly", value="yearly")
])
async def daily_report(interaction: discord.Interaction, coin: str, start_date: str, end_date: str, interval: app_commands.Choice[str]):
    """Sends a daily report with open and close coin values for the specified date range."""
    print("daily_report command registered")  # Debugging line
    
    await interaction.response.defer(thinking=True)  # Defer the response

    with session_scope() as session:
        coin_obj = validate_coin(coin.upper(), session)
        if not coin_obj:
            await interaction.followup.send(f"The coin `{coin}` is not in the database. Would you like to add it? (Respond with 'yes' or 'no')")
            
            def check(msg):
                return msg.author == interaction.user and msg.channel == interaction.channel and msg.content.lower() in ['yes', 'no']
            try:
                msg = await bot.wait_for('message', check=check, timeout=30.0)
                if msg.content.lower() == 'yes':
                    await interaction.followup.send(f"Please provide the webhook URL for {coin}:")
                    
                    # Check for the webhook URL
                    def webhook_check(msg):
                        return msg.author == interaction.user and msg.channel == interaction.channel

                    webhook_msg = await bot.wait_for('message', check=webhook_check, timeout=30.0)
                    webhook_url = webhook_msg.content
                    
                    # Add the coin with the provided webhook
                    add_coin(coin.upper(), webhook_url)  # Pass session here if needed
                    existing_coin = validate_coin(coin,session)
                    if existing_coin:
                        await interaction.followup.send(f"{coin.upper()} was added successfully!")
                    else:
                        await interaction.followup.send(f"{coin} was not added.")
                else:
                    await interaction.followup.send(f"{coin} was not added.")
                return  # Ensure no further responses happen
            except asyncio.TimeoutError:
                await interaction.followup.send("You took too long to respond!")
                return  # Ensure no further responses happen

    # Convert the date strings to datetime objects
    try:
        start_date_obj = datetime.strptime(start_date, "%d/%m/%Y")
        end_date_obj = datetime.strptime(end_date, "%d/%m/%Y")
    except ValueError:
        await interaction.followup.send("Invalid date format! Please use DD/MM/YYYY.")
        return  # Ensure no further responses happen
    
    # Create the embed message
    embed = discord.Embed(
        title=f"📈 {interval.name} Coin Report for {coin.upper()}",
        description=f"Here are the {interval.name.lower()} open and close values for {coin.upper()} between {start_date} and {end_date}:",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )

    for day in historic_data:
        embed.add_field(
            name=f"Date: {day['date']}",
            value=f"**Open:** {day['open']} | **Close:** {day['close']}",
            inline=False
        )

    embed.set_footer(text="Data provided by Crypto Bot")

    await interaction.followup.send(embed=embed)  # Use followup here
    await interaction.followup.send(file=discord.File(csv_filename))  # Send CSV file as a followup


@bot.tree.command(name="add_crypto", description="Add a new cryptocurrency to the database.")
@app_commands.describe(symbol="The symbol of the cryptocurrency (e.g., BTC, ETH)", webhook="Webhook URL for notifications")
async def add_crypto(interaction: discord.Interaction, symbol: str, webhook: str):
    print("add_crypto command registered")  # Check if this prints when you start the bot
    await interaction.response.defer(thinking=True)

    with session_scope() as session:
        existing_coin = validate_coin(symbol.upper(), session)
        if existing_coin:
            await interaction.followup.send(f"The cryptocurrency `{symbol.upper()}` is already in the database.")
            return
        
        add_coin(symbol.upper(), webhook)  # Ensure this function handles adding to the session
        existing_coin = validate_coin(symbol.upper(), session)
        if existing_coin:
            await interaction.followup.send(f"The cryptocurrency `{symbol.upper()}` has been added successfully.")
        else:
            await interaction.followup.send(f"The cryptocurrency `{symbol.upper()}` does not exist.")

@bot.command()
async def sync(ctx: commands.Context):
    print(DISCORD_OWNER_ID)
    print(ctx.author.id)
    if ctx.author.id == DISCORD_OWNER_ID:
        guild = discord.Object(id=DISCORD_SERVER_ID)  # Replace with your guild ID
        try:
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} commands in the guild: {[cmd.name for cmd in synced]}")
        except Exception as e:
            print(f"Error syncing commands: {e}") 
    else:
        await ctx.reply("You are not the owner.")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    commands = [cmd.name for cmd in bot.tree.get_commands()]
    print(f"Available commands: {commands}")

# Run the bot
bot.run(DISCORD_TOKEN)