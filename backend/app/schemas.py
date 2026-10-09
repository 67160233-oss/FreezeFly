from datetime import datetime, timezone
from typing import Annotated, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator

from .freeze_policy import ALLOWED_HOURS, FREEZE_OPTIONS


def _as_utc_iso(d: datetime) -> str:
    """ฐานข้อมูลเก็บเวลา UTC แบบไม่มีโซนเวลา ตอนส่งออกต้องติด +00:00 ไว้
    ไม่อย่างนั้นเบราว์เซอร์จะเข้าใจว่าเป็นเวลาท้องถิ่น (ในไทยจะคลาดไป 7 ชั่วโมง)"""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


UtcDatetime = Annotated[datetime, PlainSerializer(_as_utc_iso, return_type=str)]


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
    created_at: Optional[UtcDatetime] = None


# --- Flight Schemas ---
class FlightBase(BaseModel):
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure_time: UtcDatetime
    arrival_time: UtcDatetime
    price: float
    seats_available: int


class FlightCreate(FlightBase):
    pass


class FreezeOption(BaseModel):
    hours: int
    label: str
    fee_rate: float  # ค่าธรรมเนียมที่ AI ตั้งตามความเสี่ยง
    fee_amount: float
    rise_probability: Optional[float] = None  # โอกาสราคาขึ้น ≥3% ภายในระยะนี้ (ตาม AI)
    coverage_cap_amount: float = 0.0  # คุ้มครองส่วนต่างสูงสุด (บาท)
    expires_at: UtcDatetime
    available: bool
    reason: Optional[str] = None


class PriceAdvice(BaseModel):
    level: str  # rising | uncertain | stable | buy_now
    rise_probability: Optional[float] = None
    horizon_label: Optional[str] = None
    message: str


class FlightResponse(FlightBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # price = ราคาปัจจุบันที่ขยับทุกวัน (คอลัมน์ price ในฐานข้อมูลคือราคาฐาน)
    price: float = Field(validation_alias=AliasChoices("current_price", "price"))
    base_price: Optional[float] = None
    price_advice: Optional[PriceAdvice] = None
    is_bookable: bool = True
    booking_closes_at: Optional[UtcDatetime] = None
    freeze_options: List[FreezeOption] = []


# --- PriceFreeze Schemas ---
class PriceFreezeCreate(BaseModel):
    flight_id: int
    hours: int = 24  # ระยะเวลาตรึงราคา ต้องเป็นค่าใน freeze_policy.FREEZE_OPTIONS

    @field_validator("hours")
    @classmethod
    def _validate_hours(cls, v: int) -> int:
        if v not in ALLOWED_HOURS:
            labels = ", ".join(f"{o['hours']} ({o['label']})" for o in FREEZE_OPTIONS)
            raise ValueError(f"hours ต้องเป็นหนึ่งใน {labels}")
        return v


class PriceFreezeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    flight_id: int
    frozen_price: float
    freeze_fee: float
    created_at: UtcDatetime
    expires_at: UtcDatetime
    status: str
    refund_reason: Optional[str] = None
    coverage_cap_amount: float = 0.0
    flight: Optional[FlightResponse] = None


# --- Booking Schemas ---
class BookingCreate(BaseModel):
    flight_id: int
    freeze_id: Optional[int] = None
    passenger_name: str = Field(min_length=1, max_length=100)
    passenger_email: EmailStr
    promo_code: Optional[str] = Field(default=None, max_length=50)
    accept_excess: bool = False  # ยอมจ่ายส่วนที่ราคาขึ้นเกินเพดานความคุ้มครองเอง

    _clean_promo = field_validator("promo_code", mode="before")(_blank_to_none)


class ConvertRequest(BaseModel):
    """ข้อมูลตอนแปลงสิทธิ์ตรึงราคาเป็นตั๋ว
    ถ้าไม่ส่งชื่อ/อีเมลผู้โดยสารมา จะใช้ข้อมูลของบัญชีที่ล็อกอินอยู่แทน"""

    promo_code: Optional[str] = Field(default=None, max_length=50)
    passenger_name: Optional[str] = Field(default=None, max_length=100)
    passenger_email: Optional[EmailStr] = None
    accept_excess: bool = False  # ยอมจ่ายส่วนที่ราคาขึ้นเกินเพดานความคุ้มครองเอง

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
    total_price: float  # ราคาตั๋วที่ลูกค้าจ่าย หลังหักส่วนลด (ก่อนหักค่าธรรมเนียม)
    market_price: Optional[float] = None  # ราคาตลาด ณ ตอนออกตั๋ว
    protection_paid: float = 0.0  # ส่วนต่างราคาที่เราจ่ายแทนลูกค้า
    freeze_fee_paid: float = 0.0  # ค่าธรรมเนียมตรึงราคาที่จ่ายไปแล้ว
    fee_credit: Optional[float] = None  # ค่าธรรมเนียมส่วนที่หักเป็นค่าตั๋ว
    amount_due: float = 0.0  # ยอดที่ชำระตอนออกตั๋ว
    status: str
    created_at: UtcDatetime
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


class ConversionQuote(BaseModel):
    """ใบเสนอราคาก่อนออกตั๋วจากสิทธิ์ตรึงราคา (ดู freeze_policy.conversion_quote)"""

    frozen_price: float
    market_price: float
    price_change: float
    cap_amount: float
    covered: float
    excess: float
    exceeds_cap: bool
    ticket_price: float
    fee_paid: float
    fee_credit: float
    amount_due: float
    customer_total: float
    savings_vs_market: float