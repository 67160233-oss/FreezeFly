from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

# --- User Schemas ---
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

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
    id: int

    class Config:
        from_attributes = True

# --- PriceFreeze Schemas ---
class PriceFreezeCreate(BaseModel):
    flight_id: int
    hours: int = 24  # ระยะเวลาตรึงราคา (24 หรือ 48 ชม.)

class PriceFreezeResponse(BaseModel):
    id: int
    user_id: int
    flight_id: int
    frozen_price: float
    freeze_fee: float
    created_at: datetime
    expires_at: datetime
    status: str
    flight: Optional[FlightResponse] = None

    class Config:
        from_attributes = True

# --- Booking Schemas ---
class BookingCreate(BaseModel):
    flight_id: int
    freeze_id: Optional[int] = None
    passenger_name: str
    passenger_email: EmailStr

class BookingResponse(BaseModel):
    id: int
    user_id: int
    flight_id: int
    freeze_id: Optional[int] = None
    passenger_name: str
    passenger_email: EmailStr
    total_price: float
    status: str
    created_at: datetime
    flight: Optional[FlightResponse] = None

    class Config:
        from_attributes = True