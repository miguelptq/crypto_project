import requests
import os
from dotenv import load_dotenv
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import sessionmaker, Session
from Models.coins import Coin, CoinHistoric
from db import get_engine
from Scripts.sendDiscordMessage import send_message
import pytz
from typing import List


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Load environment variables from .env file
ENVIROMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIROMENT == 'development':
    load_dotenv('.env.development', encoding="utf-8-sig")
elif ENVIROMENT == 'production':
    load_dotenv('.env.production', encoding="utf-8-sig")
else:
    load_dotenv(encoding="utf-8-sig")  # Default to a standard .env file
API_KEY = os.getenv("API_KEY")
API_HISTORIC_BASE_URL = os.getenv("API_HISTORIC_BASE_URL")
API_HISTORIC_BASE_URL_HOURLY = os.getenv("API_HISTORIC_BASE_URL_HOURLY")
CurrentStartDate = datetime.combine(datetime.today(), datetime.min.time())

CurrentStartDateTimeStamp = int(CurrentStartDate.timestamp())

LocalTz = pytz.timezone('Europe/London')
now_utc = datetime.now(pytz.utc)
now_local = now_utc.astimezone(LocalTz)


def get_session():
    return SessionLocal()

def make_api_request(url, params):
    """Make an API request with the given URL and parameters."""
    response = requests.get(url, params=params)
    result = response.json()
    return result
    

def save_historic_data_to_db(session: Session, coin_id: int, valid_entries: list):
    """
    Save valid historical data to the database in smaller batches.
    """
    batch = []
    for i, entry in enumerate(valid_entries):
        timestamp = datetime.utcfromtimestamp(entry["time"])
        local_timestamp = timestamp.astimezone(LocalTz)
        historic_data = CoinHistoric(
            coin_id=coin_id,
            high=entry["high"],
            low=entry["low"],
            open=entry["open"],
            close=entry["close"],
            timestamp=local_timestamp.timestamp(),
        )
        batch.append(historic_data)

        # If the batch size is reached, add them to the session and commit
        session.bulk_save_objects(batch)  # Efficient batch insert
        session.commit()
        batch.clear()  # Clear the batch after committing


def count_days_between_timestamps(startDate: int):
    # Convert Unix timestamps to datetime objects
    current_timestamp = CurrentStartDateTimeStamp
    difference = current_timestamp - startDate

    # Calculate the difference between the two dates
    difference = current_timestamp - startDate
    days = int(difference / (24 * 3600))

    # Return the number of days
    return days


def fetch_paginated_data_historic(
    session: Session,
    coin: Coin,
    fsym: str,
    tsym: str,
    limit: int,
    total_days: int,
    make_historic: bool = True,
):
    toTs = int(time.time())  # Current timestamp (most recent data)
    valid_entries_count = 0
    invalid_entry = 0
    while total_days > 0 and invalid_entry == 0:
        time.sleep(1)
        # Adjust limit for the last batch if remaining days are fewer than the limit
        days_to_fetch = min(limit, total_days)

        # Build the request URL
        params = {
            "fsym": fsym,
            "tsym": tsym,
            "limit": days_to_fetch - 1,  # API returns 'limit+1' data points
            "toTs": toTs,
            "api_key": API_KEY,
        }
        result = make_api_request(API_HISTORIC_BASE_URL, params)

        if result["Response"] == "Success":
            batch_data = result["Data"]["Data"]
            sorted_data = sorted(batch_data, key=lambda x: x["time"], reverse=True)
            # Check if any entry has all values (high, low, open, close) as 0
            valid_entries = []
            for entry in sorted_data:
                dt = datetime.utcfromtimestamp(entry["time"])
                utc_dt = dt.astimezone(pytz.UTC)
                utc_unix_time = int(utc_dt.timestamp())
                if (utc_unix_time != CurrentStartDateTimeStamp):
                    if (
                        entry["high"] == 0
                        and entry["low"] == 0
                        and entry["open"] == 0
                        and entry["close"] == 0
                    ):
                        invalid_entry += 1
                    else:
                        valid_entries_count += 1
                        valid_entries.append(entry)
            save_historic_data_to_db(session, coin.id, valid_entries)
            total_days -= days_to_fetch
            toTs = result["Data"]["TimeFrom"]

        else:
            print(f"Error fetching data: {result['Message']}")
            break
    count_inserted = session.query(CoinHistoric).filter_by(coin_id=coin.id).count()
    if count_inserted >= valid_entries_count:
        coin.history_check = True
        coin.last_time_tracked = CurrentStartDateTimeStamp
        try:
            session.commit()
            send_message(f"{coin.name} historic was inserted successfully!", coin.webhook_url, coin.name, 'historic')
        except Exception as e:
            session.rollback()
            print(f"Error commiting session: {e}")
         

def fetch_paginated_data_historic_hourly(
    session: Session,
    coin: Coin,
    fsym: str,
    tsym: str,
    make_historic: bool = True,
) -> None:
    to_ts = int(datetime.now(pytz.utc).timestamp())
    valid_entries: List[dict] = []
    try:
        # Get the current daily historic entry
        coin_historic = session.query(CoinHistoric).filter(
            (CoinHistoric.coin_id == coin.id) & 
            (CoinHistoric.timestamp == CurrentStartDateTimeStamp)
        ).first()
        last_saved_hour = None
        now = datetime.now(pytz.utc)
        previous_day = now - timedelta(days=1)
        previous_day_local = now_local - timedelta(days=1)
        previous_day_start = previous_day.replace(hour=0,minute=0,second=0)
        previous_day_unixtime_stamp = int(previous_day_start.timestamp())

        # Initialize or load the hourly_historic field as a list
        if coin_historic and coin_historic.hourly_historic:
            hourly_historic_data = coin_historic.hourly_historic
            last_saved_hour = max([entry["hour"] for entry in hourly_historic_data])
        else:
            
            # Initialize as a new entry
            hourly_historic_data = []
            last_saved_hour = None
            coin_historic = CoinHistoric(
                coin_id=coin.id,
                high=0,
                low=0,
                open=0,
                close=0,
                timestamp=CurrentStartDateTimeStamp,
                hourly_historic=hourly_historic_data  # Initialize with an empty list
            )
            session.add(coin_historic)  # Add the new record to the session
        # Determine the Unix timestamp for the last saved hour
        if last_saved_hour is not None:
            last_saved_datetime = now_local.replace(hour=last_saved_hour, minute=0, second=0, microsecond=0) + timedelta(hours=1)
            start_from_unix = int(last_saved_datetime.timestamp())
        else:
            start_from_unix = CurrentStartDateTimeStamp
        

        # Calculate the Unix timestamp for the start of the previous hour
        start_of_hour = now.replace(minute=0, second=0, microsecond=0)
        unix_start_of_previous_hour = int(start_of_hour.timestamp())

        # Prepare parameters for the API request to get hourly data
        params = {
            "fsym": fsym,
            "tsym": tsym,
            "limit": 24,
            "api_key": API_KEY,
            "toTs": unix_start_of_previous_hour,
        }
        
        # Make the API request for hourly data
        result = make_api_request(API_HISTORIC_BASE_URL_HOURLY, params)
        if result["Response"] == "Success":
            hourly_data = result["Data"]["Data"]
            sorted_data = sorted(hourly_data, key=lambda x: x["time"])
            # Collect valid hourly entries
            last_entry_time = 0
            for entry in sorted_data:
                entry_time_dt = datetime.utcfromtimestamp(entry["time"]).replace(tzinfo=pytz.utc)
                utc_time_entry = entry_time_dt.astimezone(LocalTz)
                entry_unix_time = int(utc_time_entry.timestamp())
                current_time = datetime.now()
                start_of_current_time = current_time.replace(minute=0,second=0)
                limit_hour_unix = int(start_of_current_time.timestamp())
                if entry_unix_time >= start_from_unix and entry_unix_time < limit_hour_unix and(last_saved_hour is None or utc_time_entry.hour != last_saved_hour):
                    if (utc_time_entry.hour) == 23:
                        params = {
                            "fsym": fsym,
                            "tsym": tsym,
                            "limit": 4,  # API returns 'limit+1' data points
                            "api_key": API_KEY,
                        }

                        result = make_api_request(API_HISTORIC_BASE_URL, params)
                        if result["Response"] == "Success":
                            data = result["Data"]["Data"]
                            for entry in data:
                                if(entry["time"] == previous_day_unixtime_stamp):
                                    coin_historic.close = entry['close']
                                    coin_historic.open = entry['open']
                                    coin_historic.high = entry['high']
                                    coin_historic.low = entry['low']
                                    if coin_historic.open != 0:
                                        percentage_change = ((coin_historic.close - coin_historic.open)/( coin_historic.open)*100)
                                    else:
                                        percentage_change = 0
                                    if coin_historic.open > coin_historic.close:
                                        send_message(f"Daily Resume -> Open: {coin_historic.open}, Close: {coin_historic.close}.Price dropped {percentage_change:.2f}%", coin.webhook_url, coin.name, 'historic', True, 'red', daily=True)
                                    elif coin_historic.open < coin_historic.close:
                                        send_message(f"Daily Resume -> Open: {coin_historic.open}, Close: {coin_historic.close}. Price increased {percentage_change:.2f}%", coin.webhook_url, coin.name, 'historic', True, 'green', daily=True)
                                    else:
                                        send_message(f"Daily Resume -> Open: {coin_historic.open}, Close: {coin_historic.close}. No change in price!", coin.webhook_url, coin.name, 'historic', True, 'yellow', daily=True)
                    hour_entry = {
                        "hour": utc_time_entry.hour,
                        "high": entry["high"],
                        "low": entry["low"],
                        "open": entry["open"],
                        "close": entry["close"],
                    }
                    last_entry_time = utc_time_entry
                    valid_entries.append(hour_entry)
            # Append new valid hourly entries to the hourly_historic list
            if valid_entries:
                last_entry = valid_entries[-1]
                if last_entry["open"] != 0:
                    percentage_change = ((last_entry["close"] - last_entry["open"]) /( last_entry["open"])*100)
                else:
                    percentage_change = 0
                if last_entry["open"] > last_entry["close"]:
                    send_message(f"Open: {last_entry['open']}, Close: {last_entry['close']}. Price dropped {percentage_change:.2f}%", coin.webhook_url, coin.name, 'historic', True, 'red',hour=last_entry_time.hour)
                elif last_entry["open"] < last_entry["close"]:
                    send_message(f"Open: {last_entry['open']}, Close: {last_entry['close']}. Price increased {percentage_change:.2f}%", coin.webhook_url, coin.name, 'historic', True, 'green',hour=last_entry_time.hour)
                else:
                    send_message(f"Open: {last_entry['open']}, Close: {last_entry['close']}. No change in price", coin.webhook_url, coin.name, 'historic', True, 'yellow',hour=utc_time_entry.hour)
                coin_historic.hourly_historic.extend(valid_entries)
                session.flush()  # Ensure pending changes are sent to the DB
                try:
                    session.commit()
                    print(f"Committed hourly data to the database for {coin.symbol}.")
                except Exception as e:
                    session.rollback()
                    print(f"Error committing session: {e}")
            else:
                print(f"No new hourly data to update for {coin.symbol}.")
        else:
            print(f"Error fetching hourly data: {result['Message']}")
    
    except Exception as e:
        print(f"An error occurred: {e}")
        session.rollback()  # Rollback any changes if an exception occurs

    
def main(coin: Coin, hourly = False):
    
    try:
        session = get_session()
        coin = session.query(Coin).filter(Coin.id == coin.id).first()
        symbol = coin.symbol
        tsym = "USD"
        limit = 1500
    
        total_days = count_days_between_timestamps(coin.last_time_tracked)
        if hourly:
            fetch_paginated_data_historic_hourly(
                session, coin, symbol, tsym,True
            )
        else:
            fetch_paginated_data_historic(
                session, coin, symbol, tsym, limit, total_days, True
            )
    finally:
        session.close()         
    


if __name__ == "__main__":
    main()
