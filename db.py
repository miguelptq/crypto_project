import psycopg2
from sqlalchemy import create_engine


# Connection settings
DB_NAME = "crypto_tracker_db"
DB_USER = "postgres"
DB_PASS = "123"
DB_HOST = "localhost"
DB_PORT = "5432"

# SQLAlchemy engine for TimescaleDB
def get_engine():
    connection_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_url, echo=False)
    return engine


# Raw psycopg2 connection for direct queries
def get_connection():
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
    )
    return conn
