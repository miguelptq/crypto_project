﻿import requests
import os
from dotenv import load_dotenv
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from Models.coins import *
import time
from db import get_engine
from Scripts.sendDiscordMessage import send_message


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Load environment variables from .env file
ENVIROMENT = os.getenv('ENVIRONMENT', 'development')
print(ENVIROMENT)
if ENVIROMENT == 'development':
    load_dotenv('.env.development', encoding="utf-8-sig")
elif ENVIROMENT == 'production':
    load_dotenv('.env.production', encoding="utf-8-sig")
else:
    load_dotenv(encoding="utf-8-sig")  # Default to a standard .env file
API_KEY = os.getenv("API_KEY")
API_COIN_INFO_BASE_URL = os.getenv("API_COIN_INFO_BASE_URL")


def get_content_created(symbol):
    """Fetch content_created from an API"""
    apiUrl = f"{API_COIN_INFO_BASE_URL}{symbol}&api_key={API_KEY}"

    response = requests.get(apiUrl)

    data = response.json()
    name = data["Data"][symbol]["FullName"]
    date_obj = datetime.strptime(data["Data"][symbol]["AssetLaunchDate"], "%Y-%m-%d")
    ContentCreatedOn = int(time.mktime(date_obj.timetuple()))
    FinalData = {"name": name, "ContentCreatedOn": ContentCreatedOn}
    return FinalData


def add_coin():
    """Prompt user for coin data and add it to the database"""
    symbol = input("Enter the coin symbol: ").strip().upper()
    webhook = input("Discord Webhook: ")

    # Fetch content_created from API
    try:
        data = get_content_created(symbol)
    except Exception as e:
        print(f"Error fetching content_created: {e}")
        return
    name = data["name"]
    ContentCreatedOn = data["ContentCreatedOn"]
    # Add coin to the database
    session = SessionLocal()
    new_coin = Coin(
        symbol=symbol,
        name=name,
        content_created=ContentCreatedOn,
        last_time_tracked=ContentCreatedOn,
        webhook_url = webhook
    )
    session.add(new_coin)
    session.commit()
    session.close()
    """ send_message(f"{name} was added successfully!", webhook, name, 'plus') """


add_coin()
