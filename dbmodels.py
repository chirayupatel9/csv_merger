from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Numeric, Text, Date
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from datetime import datetime
import os       
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Fetch variables
USER = os.getenv("POSTGRESQL_USER")
PASSWORD = os.getenv("POSTGRESQL_PASSWORD")
HOST = os.getenv("POSTGRESQL_HOST")
PORT = os.getenv("POSTGRESQL_PORT")
DBNAME = os.getenv("POSTGRESQL_DB")

# Construct the SQLAlchemy connection string
DATABASE_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}"
print(DATABASE_URL)
# Create the SQLAlchemy engine
engine = create_engine(DATABASE_URL)
# If using Transaction Pooler or Session Pooler, we want to ensure we disable SQLAlchemy client side pooling -
# https://docs.sqlalchemy.org/en/20/core/pooling.html#switching-pool-implementations
# engine = create_engine(DATABASE_URL, poolclass=NullPool)

# Test the connection
try:
    with engine.connect() as connection:
        print("Connection successful!")
except Exception as e:
    print(f"Failed to connect: {e}")
# Create SQLAlchemy Engine
try:
    engine = create_engine(DATABASE_URL)
    print("Engine created successfully")
except Exception as e:
    print(f"Error creating engine: {e}")
    raise e

# Base class for models
Base = declarative_base()

# --------------------- Models ---------------------
class Users(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50))
    username = Column(String(50))
    password = Column(String(100))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    tries = Column(Integer, default=1)
    last_login = Column(DateTime)
    email = Column(String(150))

class AccountTransaction(Base):
    __tablename__ = "accountTransaction"
    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    account_Id = Column(Integer)  # FIXED: Matches DDL
    description = Column(Text)
    vendor_id = Column(Integer, ForeignKey("vendor.vendor_id"))
    card_number = Column(String(100))
    posting_date = Column(DateTime)
    transaction_date = Column(DateTime)
    amount = Column(Numeric(10, 4))
    category = Column(String(100))
    payment_date = Column(DateTime)
    due_date = Column(DateTime)
    balance_as_of_date = Column(Numeric(10, 4))
    sale_type = Column(String(100))
    source_id = Column(Integer)
    created_by = Column(Integer, ForeignKey("users.user_id"))
    updated_by = Column(Integer, ForeignKey("users.user_id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Vendor(Base):
    __tablename__ = "vendor"
    vendor_id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_name = Column(String(50))
    vendor_code = Column(String(50))
    vendor_description = Column(String(100))
    vendor_address = Column(String(255))
    vendor_email = Column(String(55))
    vendor_phone = Column(String(20))
    vendor_label = Column(String(100))
    category_Id = Column(Integer)
    created_by = Column(Integer, ForeignKey("users.user_id"))
    updated_by = Column(Integer, ForeignKey("users.user_id"))


# Create all tables
Base.metadata.create_all(engine)

# Session factory
SessionLocal = sessionmaker(bind=engine)
