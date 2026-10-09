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

from . import freeze_policy, price_ai, pricing
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
    # ไม่ใส่ index ที่ origin/destination โดยตั้งใจ: /flights ค้นด้วย ILIKE('%...%')
    # ซึ่งมี wildcard นำหน้า ทำให้ btree index ใช้งานไม่ได้อยู่ดี (ดู 04-pitfalls.sql ข้อ 4.3)
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    departure_time = Column(DateTime, nullable=False)
    arrival_time = Column(DateTime, nullable=False)
    price = Column(Float, nullable=False)  # ราคาฐาน ราคาที่ขายจริงขยับทุกวัน ดู current_price
    seats_available = Column(Integer, default=100)

    freezes = relationship("PriceFreeze", back_populates="flight")
    bookings = relationship("Booking", back_populates="flight")

    # ค่าที่คำนวณจากกฎใน freeze_policy.py ส่งไปให้หน้าเว็บใช้ตัดสินใจว่าจะแสดงปุ่มอะไร
    @property
    def booking_closes_at(self):
        return freeze_policy.booking_deadline(self.departure_time)

    @property
    def is_bookable(self) -> bool:
        return freeze_policy.is_bookable(self.departure_time)

    @property
    def current_price(self) -> float:
        return pricing.current_price(self)

    @property
    def base_price(self) -> float:
        return self.price

    @property
    def freeze_options(self):
        return freeze_policy.freeze_options_for(self)

    @property
    def price_advice(self) -> dict:
        can_freeze = any(o["available"] for o in self.freeze_options)
        return price_ai.advice(self, freeze_policy.booking_deadline(self.departure_time), can_freeze=can_freeze)


class PriceFreeze(Base):
    __tablename__ = "price_freezes"

    id = Column(Integer, primary_key=True, index=True)
    # index=True: /freeze/user/{user_id} กรองด้วยคอลัมน์นี้ตรงๆ ทุกครั้ง
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    flight_id = Column(Integer, ForeignKey("flights.id"), nullable=False, index=True)
    frozen_price = Column(Float, nullable=False)
    freeze_fee = Column(Float, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    # ไม่ใส่ index ที่ status โดยตั้งใจ: มีแค่ 3 ค่า (active/converted/expired) cardinality ต่ำ
    # เกินไป planner มักเลือก sequential scan อยู่ดี (ดู 04-pitfalls.sql ข้อ 4.4)
    status = Column(String, default="active")  # active, converted, expired, refunded
    refund_reason = Column(String, nullable=True)  # soldout = ที่นั่งเต็ม, price_cap = ราคาขึ้นเกินเพดานความคุ้มครอง

    user = relationship("User", back_populates="freezes")
    flight = relationship("Flight", back_populates="freezes")
    booking = relationship("Booking", back_populates="freeze", uselist=False)

    @property
    def coverage_cap_amount(self) -> float:
        return round(self.frozen_price * freeze_policy.COVERAGE_CAP_RATE, 0)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    # index=True: /bookings/user/{user_id} กรองด้วยคอลัมน์นี้ตรงๆ ทุกครั้ง
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    flight_id = Column(Integer, ForeignKey("flights.id"), nullable=False, index=True)
    freeze_id = Column(Integer, ForeignKey("price_freezes.id"), nullable=True)
    passenger_name = Column(String, nullable=False)
    passenger_email = Column(String, nullable=False)
    total_price = Column(Float, nullable=False)  # ราคาตั๋วที่ลูกค้าจ่าย หลังหักส่วนลด (ก่อนหักค่าธรรมเนียม)
    market_price = Column(Float, nullable=True)  # ราคาตลาดของสายการบิน ณ ตอนออกตั๋ว
    protection_paid = Column(Float, default=0.0)  # ส่วนต่างราคาที่เราจ่ายแทนลูกค้า
    fee_credit = Column(Float, nullable=True)  # ค่าธรรมเนียมส่วนที่หักเป็นค่าตั๋ว
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
        """ยอดที่ต้องชำระตอนออกตั๋ว = ราคาตั๋วหลังส่วนลด - ค่าธรรมเนียมส่วนที่หักเป็นค่าตั๋ว
        (การจองก่อนมีระบบคุ้มครองราคาไม่มี fee_credit จึงหักค่าธรรมเนียมเต็มจำนวนแบบเดิม)"""
        credit = self.fee_credit if self.fee_credit is not None else self.freeze_fee_paid
        return round(max(0.0, self.total_price - credit), 2)


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