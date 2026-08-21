from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
import os

from . import models, schemas
from .database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FreezeFly - Flight & Price Freeze API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PromoCheckRequest(BaseModel):
    code: str
    price: float

def seed_mock_data(db: Session):
    if db.query(models.Flight).count() == 0:
        now = datetime.utcnow()
        sample_flights = [
            models.Flight(
                airline="Thai Airways",
                flight_number="TG600",
                origin="BKK",
                destination="HKG",
                departure_time=now + timedelta(days=1, hours=8),
                arrival_time=now + timedelta(days=1, hours=11, minutes=45),
                price=8500.0,
                seats_available=45
            ),
            models.Flight(
                airline="AirAsia",
                flight_number="FD302",
                origin="BKK",
                destination="CNX",
                departure_time=now + timedelta(days=2, hours=10),
                arrival_time=now + timedelta(days=2, hours=11, minutes=15),
                price=1800.0,
                seats_available=80
            ),
            models.Flight(
                airline="ANA",
                flight_number="NH848",
                origin="BKK",
                destination="HND",
                departure_time=now + timedelta(days=3, hours=1),
                arrival_time=now + timedelta(days=3, hours=8, minutes=50),
                price=18500.0,
                seats_available=20
            )
        ]
        db.add_all(sample_flights)

    if db.query(models.Promotion).count() == 0:
        sample_promos = [
            models.Promotion(
                code="NEWUSER2026",
                title="FREEZE ฟรีครั้งแรก",
                description="ฟรีค่าธรรมเนียมตรึงราคาเที่ยวบินทุกเส้นทางสูงสุด 48 ชั่วโมง สำหรับการใช้งานครั้งแรก"
            ),
            models.Promotion(
                code="HALFPRICE50",
                title="ลด 50% ค่าธรรมเนียมตรึงราคา",
                description="รับส่วนลดค่าธรรมเนียม FreezePrice ทันที 50% เมื่อจองเที่ยวบินต่างประเทศ"
            ),
            models.Promotion(
                code="ASIAFLY300",
                title="บินญี่ปุ่น/เกาหลี ลด ฿300",
                description="รับส่วนลดเพิ่มเมื่อชำระเงินออกตั๋วเที่ยวบินโซนเอเชียตะวันออกที่ผ่านการตรึงราคา"
            )
        ]
        db.add_all(sample_promos)

    db.commit()

@app.on_event("startup")
def startup_event():
    db = next(get_db())
    try:
        seed_mock_data(db)
    finally:
        db.close()

@app.get("/")
def root():
    return {"message": "FreezeFly API Service is Running"}

# --- 1. Authentication Endpoints ---
@app.post("/auth/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username นี้ถูกใช้งานแล้ว")
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="อีเมลนี้ถูกใช้งานแล้ว")
    
    new_user = models.User(username=user.username, email=user.email, password=user.password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/auth/login")
def login_user(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or user.password != credentials.password:
        raise HTTPException(status_code=401, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    return {
        "message": "เข้าสู่ระบบสำเร็จ",
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "access_token": f"fake-jwt-token-for-{user.id}"
    }

# --- 2. Flight Endpoints ---
@app.get("/flights", response_model=List[schemas.FlightResponse])
def search_flights(user_id: Optional[int] = None, origin: Optional[str] = None, destination: Optional[str] = None, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนค้นหาเที่ยวบิน")
    
    query = db.query(models.Flight)
    if origin:
        query = query.filter(models.Flight.origin.ilike(f"%{origin}%"))
    if destination:
        query = query.filter(models.Flight.destination.ilike(f"%{destination}%"))
    return query.all()

@app.get("/flights/{flight_id}", response_model=schemas.FlightResponse)
def get_flight(flight_id: int, user_id: Optional[int] = None, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนดึงข้อมูลเที่ยวบิน")
    flight = db.query(models.Flight).filter(models.Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลเที่ยวบินนี้")
    return flight

# --- 3. Price Freeze Endpoints ---
@app.post("/freeze/create", response_model=schemas.PriceFreezeResponse, status_code=status.HTTP_201_CREATED)
def create_price_freeze(user_id: int, freeze_data: schemas.PriceFreezeCreate, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนทำรายการ")
        
    flight = db.query(models.Flight).filter(models.Flight.id == freeze_data.flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลเที่ยวบิน")

    fee_percentage = 0.05 if freeze_data.hours <= 24 else 0.08
    freeze_fee = round(flight.price * fee_percentage, 2)
    expires_at = datetime.utcnow() + timedelta(hours=freeze_data.hours)

    new_freeze = models.PriceFreeze(
        user_id=user_id,
        flight_id=flight.id,
        frozen_price=flight.price,
        freeze_fee=freeze_fee,
        expires_at=expires_at,
        status="active"
    )
    db.add(new_freeze)
    db.commit()
    db.refresh(new_freeze)
    return new_freeze

@app.get("/freeze/user/{user_id}", response_model=List[schemas.PriceFreezeResponse])
def get_user_freezes(user_id: int, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนเข้าถึงข้อมูล")
    freezes = db.query(models.PriceFreeze).filter(models.PriceFreeze.user_id == user_id).all()
    now = datetime.utcnow()
    for freeze in freezes:
        if freeze.status == "active" and now > freeze.expires_at:
            freeze.status = "expired"
    db.commit()
    return freezes

@app.post("/freeze/convert/{freeze_id}", response_model=schemas.BookingResponse)
def convert_freeze_to_booking(freeze_id: int, data: dict, db: Session = Depends(get_db)):
    freeze = db.query(models.PriceFreeze).filter(models.PriceFreeze.id == freeze_id).first()
    if not freeze:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลรายการตรึงราคา")
    
    if freeze.status.lower() != "active":
        raise HTTPException(status_code=400, detail="สิทธิ์ตรึงราคานี้หมดอายุหรือถูกใช้งานไปแล้ว")

    final_price = freeze.frozen_price
    promo_code = data.get("promo_code")
    if promo_code:
        code_input = promo_code.strip().upper()
        promo = db.query(models.Promotion).filter(models.Promotion.code == code_input).first()
        if promo:
            discount = 0.0
            if code_input == "NEWUSER2026":
                discount = 100.0
            elif code_input == "HALFPRICE50":
                discount = final_price * 0.5
            elif code_input == "ASIAFLY300":
                discount = 300.0
            else:
                discount = 100.0
            final_price = max(0.0, final_price - discount)

    new_booking = models.Booking(
        user_id=freeze.user_id,
        flight_id=freeze.flight_id,
        freeze_id=freeze.id,
        passenger_name=data.get("passenger_name", "Passenger"),
        passenger_email=data.get("passenger_email", "email@example.com"),
        total_price=final_price,
        status="confirmed"
    )
    
    freeze.status = "converted"
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    return new_booking

# --- 4. Booking Endpoints ---
@app.post("/bookings/create", response_model=schemas.BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(user_id: int, booking_data: schemas.BookingCreate, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนทำรายการ")
        
    flight = db.query(models.Flight).filter(models.Flight.id == booking_data.flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลเที่ยวบิน")

    final_price = flight.price
    if booking_data.freeze_id:
        freeze = db.query(models.PriceFreeze).filter(models.PriceFreeze.id == booking_data.freeze_id, models.PriceFreeze.user_id == user_id).first()
        if not freeze or freeze.status != "active":
            raise HTTPException(status_code=400, detail="สิทธิ์ตรึงราคาไม่ถูกต้องหรือหมดอายุแล้ว")
        final_price = freeze.frozen_price
        freeze.status = "converted"

    new_booking = models.Booking(
        user_id=user_id,
        flight_id=flight.id,
        freeze_id=booking_data.freeze_id,
        passenger_name=booking_data.passenger_name,
        passenger_email=booking_data.passenger_email,
        total_price=final_price,
        status="confirmed"
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    return new_booking

@app.get("/bookings/user/{user_id}", response_model=List[schemas.BookingResponse])
def get_user_bookings(user_id: int, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนเข้าถึงข้อมูล")
    return db.query(models.Booking).filter(models.Booking.user_id == user_id).all()

# --- 5. Promotions & Contact Endpoints ---
@app.get("/promotions")
def get_promotions(db: Session = Depends(get_db)):
    return db.query(models.Promotion).all()

@app.post("/promotions/validate")
def validate_promotion(data: PromoCheckRequest, db: Session = Depends(get_db)):
    code_input = data.code.strip().upper()
    promo = db.query(models.Promotion).filter(models.Promotion.code == code_input).first()
    
    if not promo:
        raise HTTPException(status_code=400, detail="ไม่พบโค้ดส่วนลดนี้ หรือโค้ดไม่ถูกต้อง")
    
    discount = 0.0
    if code_input == "NEWUSER2026":
        discount = 100.0
    elif code_input == "HALFPRICE50":
        discount = round(data.price * 0.5, 2)
    elif code_input == "ASIAFLY300":
        discount = 300.0
    else:
        discount = 100.0

    discount = min(discount, data.price)
    final_price = round(data.price - discount, 2)

    return {
        "valid": True,
        "code": code_input,
        "discount_amount": discount,
        "final_price": final_price,
        "title": promo.title
    }

@app.post("/contact", status_code=status.HTTP_201_CREATED)
def create_contact_message(data: dict, db: Session = Depends(get_db)):
    new_msg = models.ContactMessage(
        name=data.get("name"),
        email=data.get("email"),
        subject=data.get("subject"),
        message=data.get("message")
    )
    db.add(new_msg)
    db.commit()
    return {"status": "success", "message": "บันทึกข้อความติดต่อเรียบร้อยแล้ว"}

if os.path.exists("."):
    app.mount("/", StaticFiles(directory=".", html=True), name="static")