from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Float, Numeric, JSON
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from db import get_engine


engine = get_engine()
Base = declarative_base()


class Coin(Base):
    __tablename__ = "coins"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    content_created = Column(Integer, nullable=False)
    last_time_tracked = Column(Integer, nullable=False)
    history_check = Column(Boolean, default=False, nullable=True)
    webhook_url = Column(String, nullable=False)

    historics = relationship("CoinHistoric", back_populates="coin")


class CoinHistoric(Base):
    __tablename__ = "coin_historic"
    id = Column(Integer, primary_key=True, autoincrement=True)
    coin_id = Column(
        Integer, ForeignKey("coins.id"), nullable=False
    )  # Foreign key to coins table
    high = Column(Numeric, nullable=False)
    low = Column(Numeric, nullable=False)
    open = Column(Numeric, nullable=False)
    close = Column(Numeric, nullable=False)
    timestamp = Column(Integer, nullable=False)
    hourly_historic = Column(MutableList.as_mutable(JSON), default=[])

    # Define relationship with Coin
    coin = relationship("Coin", back_populates="historics")


Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
