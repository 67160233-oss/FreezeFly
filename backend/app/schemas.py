from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _blank_to_none(v):
    """ช่องฟอร์มที่ส่งมาเป็นสตริงว่าง ให้ถือว่าไม่ได้กรอก"""
    if isinstance(v, str) and not v.strip():
        return None
    return v


# --- User Schemas ---
class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    created_at: Optional[datetime] = None


# --- Flight Schemas ---
class FlightBase(BaseModel):
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    price: float
    seats_available: int


class FlightCreate(FlightBase):
    pass


class FlightResponse(FlightBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# --- PriceFreeze Schemas ---
class PriceFreezeCreate(BaseModel):
    flight_id: int
    hours: int = 24  # ระยะเวลาตรึงราคา: 24 หรือ 48 ชั่วโมงเท่านั้น

    @field_validator("hours")
    @classmethod
    def _validate_hours(cls, v: int) -> int:
        if v not in (24, 48):
            raise ValueError("hours ต้องเป็น 24 หรือ 48 เท่านั้น")
        return v


class PriceFreezeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    flight_id: int
    frozen_price: float
    freeze_fee: float
    created_at: datetime
    expires_at: datetime
    status: str
    flight: Optional[FlightResponse] = None


# --- Booking Schemas ---
class BookingCreate(BaseModel):
    flight_id: int
    freeze_id: Optional[int] = None
    passenger_name: str = Field(min_length=1, max_length=100)
    passenger_email: EmailStr
    promo_code: Optional[str] = Field(default=None, max_length=50)

    _clean_promo = field_validator("promo_code", mode="before")(_blank_to_none)


class ConvertRequest(BaseModel):
    """ข้อมูลตอนแปลงสิทธิ์ตรึงราคาเป็นตั๋ว
    ถ้าไม่ส่งชื่อ/อีเมลผู้โดยสารมา จะใช้ข้อมูลของบัญชีที่ล็อกอินอยู่แทน"""

    promo_code: Optional[str] = Field(default=None, max_length=50)
    passenger_name: Optional[str] = Field(default=None, max_length=100)
    passenger_email: Optional[EmailStr] = None

    _clean = field_validator(
        "promo_code", "passenger_name", "passenger_email", mode="before"
    )(_blank_to_none)


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    flight_id: int
    freeze_id: Optional[int] = None
    passenger_name: str
    passenger_email: EmailStr
    total_price: float  # ราคาตั๋วทั้งใบหลังหักส่วนลด
    freeze_fee_paid: float = 0.0  # ค่าธรรมเนียมตรึงราคาที่จ่ายไปแล้ว
    amount_due: float = 0.0  # ยอดที่ต้องชำระเพิ่ม (total_price - freeze_fee_paid)
    status: str
    created_at: datetime
    flight: Optional[FlightResponse] = None


# --- Promotion Schemas ---
class PromotionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class PromoCheckRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    price: float = Field(gt=0)
    # ส่ง flight_id มาด้วยจะตรวจเงื่อนไขเฉพาะเที่ยวบิน (เช่น โซนเอเชีย) ได้ตรงขึ้น
    flight_id: Optional[int] = None


# --- Contact Schemas ---
class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    subject: str = Field(default="", max_length=200)
    message: str = Field(min_length=1, max_length=5000)