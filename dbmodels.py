from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Numeric, Text, Date
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from datetime import datetime
# Database Configuration
DATABASE_URL = "postgresql://postgres:Password#123@localhost:5432/bk_db"

# Create SQLAlchemy Engine
engine = create_engine(DATABASE_URL)

# Base class for models
Base = declarative_base()

# --------------------- Models ---------------------

class TransactionType(Base):
    __tablename__ = "TransactionType"
    tran_type_id = Column(Integer, primary_key=True, autoincrement=True)
    tran_type = Column(String(20))
    tran_code = Column(Integer)
    tran_desc = Column(String(50))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class AccountTypes(Base):
    __tablename__ = "accountTypes"
    accountType_id = Column(Integer, primary_key=True)
    accountType = Column(String(45))


class Attachments(Base):
    __tablename__ = "attachments"
    attachment_id = Column(Integer, primary_key=True, autoincrement=True)
    attachment_name = Column(String(100))
    attachment_path = Column(String(255))
    attachment_type = Column(String(100))
    created_by = Column(Integer, ForeignKey("users.user_id"))
    updated_by = Column(Integer, ForeignKey("users.user_id"))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class Users(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50))
    username = Column(String(50))
    password = Column(String(50))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    tries = Column(Integer, default=1)
    last_login = Column(DateTime)
    email = Column(String(150))
    defaultOrgId = Column(Integer, ForeignKey("organization.org_id"))

class Banks(Base):
    __tablename__ = "banks"
    bank_id = Column(Integer, primary_key=True)
    bank_Name = Column(String(45))
    contact_number = Column(String(45))
    description = Column(String(45))


class Accounts(Base):
    __tablename__ = "accounts"

    account_Id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organization.org_id"))
    account_Name = Column(String(255))
    account_code = Column(String(45), nullable=False)
    account_Number = Column(String(255))
    account_owner = Column(String(255))
    due_date = Column(Date)
    bank_id = Column(Integer, ForeignKey("banks.bank_id"))
    accountType_id = Column(Integer, ForeignKey("accountTypes.accountType_id"))


class Cards(Base):
    __tablename__ = "cards"

    card_Id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.account_Id"))
    card_number = Column(String(45), unique=True)
    card_owner = Column(String(45))
    description = Column(String(100))


class Categories(Base):
    __tablename__ = "categories"
    category_id = Column(Integer, primary_key=True)
    category_Name = Column(String(45))


class Frequency(Base):
    __tablename__ = "frequency"

    freq_Id = Column(Integer, primary_key=True, autoincrement=True)  # Explicit primary key
    freq_Name = Column(String(50))
    freq_Code = Column(String(10))
    freq_Desc = Column(Text)
    freq_Start = Column(DateTime)
    freq_End = Column(DateTime)


class Headers(Base):
    __tablename__ = "headers"
    h_id = Column(Integer, primary_key=True, autoincrement=True)
    bank_name = Column(String(255))
    read_line = Column(Integer, default=0)
    headers = Column(String(255))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class Logs(Base):
    __tablename__ = "logs"
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    log_type = Column(String(20))
    severity = Column(Integer)
    log = Column(String(50))
    org_id = Column(Integer, ForeignKey("organization.org_id"))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class RoleOrg(Base):
    __tablename__ = "roleOrg"
    roleOrgId = Column(Integer, primary_key=True)
    roleId = Column(String(45))
    orgId = Column(String(45))
    updatedBy = Column(String(45))
    updated = Column(DateTime)
    createdBy = Column(String(45))
    created = Column(DateTime)


class Roles(Base):
    __tablename__ = "roles"
    role_id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(50))
    description = Column(String(100))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)




class AccountTransaction(Base):
    __tablename__ = "accountTransaction"

    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organization.org_id"))
    account_id = Column(Integer, ForeignKey("accounts.account_Id"))
    description = Column(Text)
    vendor_id = Column(Integer, ForeignKey("vendor.vendor_id"))
    tran_type_id = Column(Integer, ForeignKey("TransactionType.tran_type_id"))
    card_number = Column(String(100))
    posting_date = Column(DateTime)
    transaction_date = Column(DateTime)
    amount = Column(Numeric(10, 4))
    category = Column(String(100), ForeignKey("categories.category_id"))
    payment_date = Column(DateTime)
    due_date = Column(DateTime)
    balance_as_of_date = Column(Numeric(10, 4))
    sale_type = Column(String(100))
    source_id = Column(Integer)
    created_by = Column(Integer, ForeignKey("users.user_id"))
    updated_by = Column(Integer, ForeignKey("users.user_id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Organization(Base):
    __tablename__ = "organization"
    org_id = Column(Integer, primary_key=True, autoincrement=True)
    org_name = Column(String(50))
    org_code = Column(String(50))
    org_description = Column(String(100))
    org_address = Column(String(100))
    org_phone = Column(String(20))
    org_email = Column(String(50))
    org_ein = Column(String(25))
    created_by = Column(Integer, ForeignKey("users.user_id"))
    updated_by = Column(Integer, ForeignKey("users.user_id"))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class UploadFiles(Base):
    __tablename__ = "upload_files"
    file_id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String(100))
    file_path = Column(String(255))
    file_type = Column(String(100))
    read_flag = Column(String(10))
    created_by = Column(Integer, ForeignKey("users.user_id"))
    updated_by = Column(Integer, ForeignKey("users.user_id"))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class UserRole(Base):
    __tablename__ = "user_role"
    user_role_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    role_id = Column(Integer, ForeignKey("roles.role_id"))
    updated_at = Column(DateTime)
    created_at = Column(DateTime)


class Vendor(Base):
    __tablename__ = "vendor"
    vendor_id = Column(Integer, primary_key=True, autoincrement=True)
    freq_Id = Column(Integer, ForeignKey("frequency.freq_Id"))
    vendor_name = Column(String(50))
    vendor_code = Column(String(50))
    vendor_description = Column(String(100))
    vendor_address = Column(String(255))
    vendor_email = Column(String(55))
    vendor_phone = Column(String(20))
    vendor_label = Column(String(100))
    category_Id = Column(Integer, ForeignKey("categories.category_id"))
    created_by = Column(Integer, ForeignKey("users.user_id"))
    updated_by = Column(Integer, ForeignKey("users.user_id"))


# Create all tables
Base.metadata.create_all(engine)

# Session factory
SessionLocal = sessionmaker(bind=engine)
