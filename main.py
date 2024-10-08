﻿from db import get_connection, get_engine
import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timezone, timedelta
from Models.coins import Coin, CoinHistoric
from sqlalchemy import Table, Column, Integer, String, MetaData, Float, TIMESTAMP, desc
from Scripts.get_historic_coin_data import main as get_coin_historic
import pytz
import logging


logging.basicConfig(level=logging.INFO)
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
LocalTz = pytz.timezone('Europe/London')

""" logging.basicConfig(level=logging.INFO) """


def process_all_cryptos():
    session = SessionLocal()
    now_utc = datetime.now(pytz.utc)
    now_local = now_utc.astimezone(LocalTz)
    CurrentStartDate = now_local.replace(hour=0,minute=0,second=0)
    PreviousDate = CurrentStartDate- timedelta(days=1)
    PreviousDateUnix = int(PreviousDate.timestamp())
    logging.info("Running process_all_cryptos...")
    try:
        coins_list = session.query(Coin).all()
        if coins_list:
            for coin in coins_list:
                last_row_historic = session.query(CoinHistoric).filter(CoinHistoric.coin_id == coin.id).order_by(desc(CoinHistoric.timestamp)).first()
                if last_row_historic is None or coin.history_check == False or last_row_historic.timestamp < PreviousDateUnix:
                    get_coin_historic(coin, False)
                else:
                    get_coin_historic(coin, True)
        logging.info(f"Current Start Date: {CurrentStartDate}")
        logging.info(f"Previous Start Date: {PreviousDate}")
        logging.info(f"Coin: {coin.symbol}, Last Historic Timestamp: {last_row_historic.timestamp}")
    finally:
        session.close()
        


if __name__ == "__main__":
    scheduler = BackgroundScheduler(debug=True)
    scheduler.add_job(process_all_cryptos, 'cron', minute=1, second=0)
    scheduler.start()

    print("Press Ctrl+C to stop the scheduler")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
        print("Scheduler stopped")
    