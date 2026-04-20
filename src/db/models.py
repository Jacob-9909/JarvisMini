from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    slack_channel_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    config = relationship("UserConfig", back_populates="user", uselist=False, cascade="all, delete-orphan")
    scan_history = relationship("ScanHistory", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("NotificationLog", back_populates="user", cascade="all, delete-orphan")

class UserConfig(Base):
    __tablename__ = "user_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # Target URL specific for this user
    target_booking_url = Column(String)
    
    # Web credentials
    target_user_id = Column(String, nullable=True)
    target_user_password = Column(String, nullable=True)
    
    # Priority configurations
    anniversary_date = Column(String, nullable=True) # "YYYY-MM-DD"
    buffer_days = Column(Integer, default=3)
    target_zone = Column(String, nullable=True) # e.g. "A구역"
    
    user = relationship("User", back_populates="config")

class ScanHistory(Base):
    __tablename__ = "scan_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    target_site = Column(String, index=True)
    scan_timestamp = Column(DateTime, default=datetime.utcnow)
    found_slots = Column(JSON, default=list) # Found available slots
    is_notified = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="scan_history")
    
class NotificationLog(Base):
    __tablename__ = "notification_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    site = Column(String, index=True)
    slot_id = Column(String) # Unique identifier for the slot (e.g. date-zone)
    notified_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String) # "SUCCESS", "FAILED", "CANCELLED"
    
    user = relationship("User", back_populates="notifications")
