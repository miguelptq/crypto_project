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
from dateutil.relativedelta import relativedelta

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

def get_month_start_dates(start_date, end_date):
    current_date = start_date.replace(day=1)
    month_start_dates = []
    
    while current_date <= end_date:
        month_start_dates.append(current_date)
        current_date += relativedelta(months=1)
    
    return month_start_dates

def get_first_open_and_last_close(session, coin_id, month_start_date):
    # Get the first day of the month
    first_day = month_start_date
    # Get the last day of the month
    last_day = month_start_date + relativedelta(months=1) - relativedelta(days=1)
    
    # Convert to Unix timestamps
    start_timestamp = int(first_day.timestamp())
    end_timestamp = int(last_day.timestamp())

    # Get first record (open of the month)
    first_record = session.query(CoinHistoric).filter(
        CoinHistoric.coin_id == coin_id,
        CoinHistoric.timestamp >= start_timestamp,
        CoinHistoric.timestamp < start_timestamp + 86400  # Start of the next day (midnight)
    ).order_by(CoinHistoric.timestamp.asc()).first()

    # Get last record (close of the month)
    last_record = session.query(CoinHistoric).filter(
        CoinHistoric.coin_id == coin_id,
        CoinHistoric.timestamp >= start_timestamp,
        CoinHistoric.timestamp <= end_timestamp,  # End of the last day of the month
        CoinHistoric.close > 0,
        CoinHistoric.open > 0
    ).order_by(CoinHistoric.timestamp.desc()).first()

    return first_record, last_record

def create_csv_with_open_close(session, coin_id, start_date_obj, end_date_obj, csv_filename):
    # Get all the start dates of each month
    month_start_dates = get_month_start_dates(start_date_obj, end_date_obj)

    # Create CSV file
    with open(csv_filename, mode='w', newline='') as csv_file:
        fieldnames = ['Month','Year', 'Open', 'Close', 'Percentage Change']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        # Write the header
        writer.writeheader()

        # Loop through each month and get the data
        for month_start_date in month_start_dates:
            first_record, last_record = get_first_open_and_last_close(
                session, coin_id, month_start_date
            )

            # Ensure that both records are found
            if first_record and last_record:
                open_value = first_record.open
                close_value = last_record.close

                # Calculate the percentage change
                percentage_change = ((close_value - open_value) / open_value) * 100

                # Write row to CSV
                writer.writerow({
                    'Month': month_start_date.strftime('%B'),
                    'Year': month_start_date.strftime('%Y'),
                    'Open': open_value,
                    'Close': close_value,
                    "Percentage Change": f"{percentage_change:.2f}%",
                })

def validate_coin(coin,session: Session):
    coin = session.query(Coin).filter(Coin.symbol== coin).first()
    return coin


# Sync and register the slash command


# Define the slash command
# Define a slash command with interval choices
@bot.tree.command(name="report", description="Sends a monthly report with open and close coin values.")
@app_commands.describe(coin="The coin to report (e.g., BTC, ETH)", start_date="Start date (mm/yyyy)", end_date="End date (mm/yyyy)", interval="Choose an interval")
@app_commands.choices(interval=[
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Monthly", value="monthly"),
    app_commands.Choice(name="Yearly", value="yearly")
])
async def report(interaction: discord.Interaction, coin: str, start_date: str, end_date: str, interval: app_commands.Choice[str]):
    """Sends a report with open and close coin values for the specified date range."""
    print("report command registered")  # Debugging line
    
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
                    existing_coin = validate_coin(coin.upper(),session)
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
        start_date_obj = datetime.strptime(start_date, "%m/%Y")
        end_date_obj = datetime.strptime(end_date, "%m/%Y")
    except ValueError:
        await interaction.followup.send("Invalid date format! Please use MM/YYYY.")
        return  # Ensure no further responses happen
    with session_scope() as session:
        existing_coin = validate_coin(coin.upper(),session)
        coin_id = existing_coin.id
    csv_filename = f'{coin.upper()}_{int(start_date_obj.timestamp())}_{int(end_date_obj.timestamp())}_monthly_open_close.csv'
    create_csv_with_open_close(session, coin_id, start_date_obj, end_date_obj, csv_filename)
    # Create the embed message
    embed = discord.Embed(
        title=f"📈 {interval.name} Coin Report for {coin.upper()}",
        description=f"Here are the {interval.name.lower()} open and close values for {coin.upper()} between {start_date} and {end_date}:",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )

    embed.set_footer(text="Data provided by Crypto Bot")

    await interaction.followup.send(embed=embed)  # Use followup here
    await interaction.followup.send(file=discord.File(csv_filename))  # Send CSV file as a followup
    os.remove(csv_filename)


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
    if ctx.author.id == DISCORD_OWNER_ID:
        guild = discord.Object(id=DISCORD_SERVER_ID)  # Replace with your guild ID
        try:
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} commands in the guild: {[cmd.name for cmd in synced]}")
        except Exception as e:
            print(f"Error syncing commands: {e}") 
    else:
        await ctx.reply("You are not the owner.")


@bot.command()
async def delete_commands(ctx: commands.Context):
    if ctx.author.id == DISCORD_OWNER_ID:
        guild = discord.Object(id=DISCORD_SERVER_ID)
        commands = await bot.tree.fetch_commands(guild=guild)
        for command in commands:
            await bot.tree.remove_command(command.name, guild=guild)
        await ctx.send("Commands have been deleted!")
    else:
        await ctx.reply("You are not the owner.")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    commands = [cmd.name for cmd in bot.tree.get_commands()]
    print(f"Available commands: {commands}")

# Run the bot
bot.run(DISCORD_TOKEN)