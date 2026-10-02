from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base
from .utils import utcnow


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)  # เก็บเป็น bcrypt hash เท่านั้น
    created_at = Column(DateTime, default=utcnow)

    freezes = relationship("PriceFreeze", back_populates="user")
    bookings = relationship("Booking", back_populates="user")


class Flight(Base):
    __tablename__ = "flights"

    id = Column(Integer, primary_key=True, index=True)
    airline = Column(String, nullable=False)
    flight_number = Column(String, nullable=False)
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    departure_time = Column(DateTime, nullable=False)
    arrival_time = Column(DateTime, nullable=False)
    price = Column(Float, nullable=False)
    seats_available = Column(Integer, default=100)

    freezes = relationship("PriceFreeze", back_populates="flight")
    bookings = relationship("Booking", back_populates="flight")


class PriceFreeze(Base):
    __tablename__ = "price_freezes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    flight_id = Column(Integer, ForeignKey("flights.id"), nullable=False)
    frozen_price = Column(Float, nullable=False)
    freeze_fee = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String, default="active")  # active, converted, expired

    user = relationship("User", back_populates="freezes")
    flight = relationship("Flight", back_populates="freezes")
    booking = relationship("Booking", back_populates="freeze", uselist=False)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    flight_id = Column(Integer, ForeignKey("flights.id"), nullable=False)
    freeze_id = Column(Integer, ForeignKey("price_freezes.id"), nullable=True)
    passenger_name = Column(String, nullable=False)
    passenger_email = Column(String, nullable=False)
    total_price = Column(Float, nullable=False)  # ราคาตั๋วทั้งใบหลังหักส่วนลด
    status = Column(String, default="confirmed")  # confirmed, cancelled
    created_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="bookings")
    flight = relationship("Flight", back_populates="bookings")
    freeze = relationship("PriceFreeze", back_populates="booking")

    @property
    def freeze_fee_paid(self) -> float:
        """ค่าธรรมเนียมตรึงราคาที่ลูกค้าจ่ายไปแล้ว (นับเป็นส่วนหนึ่งของราคาตั๋ว)"""
        return float(self.freeze.freeze_fee) if self.freeze else 0.0

    @property
    def amount_due(self) -> float:
        """ยอดที่ต้องชำระเพิ่ม = ราคาตั๋วหลังส่วนลด - ค่าธรรมเนียมที่จ่ายไปแล้ว"""
        return round(max(0.0, self.total_price - self.freeze_fee_paid), 2)


class ContactMessage(Base):
    __tablename__ = "contact_messages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    subject = Column(String)
    message = Column(String)


class Promotion(Base):
    __tablename__ = "promotions"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True)
    title = Column(String)
    description = Column(String)


class PromoRedemption(Base):
    """บันทึกการใช้โค้ดส่วนลด ป้องกันการใช้ซ้ำเกิน 1 ครั้งต่อบัญชี
    (เป็นตารางใหม่ create_all จะสร้างให้เอง ไม่ต้อง migrate DB เดิม)"""

    __tablename__ = "promo_redemptions"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_user_promo"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(String, nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)