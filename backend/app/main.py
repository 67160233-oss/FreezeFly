import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas
from .database import SessionLocal, engine, get_db
from .promotions import PROMO_RULES, evaluate_promo
from .security import (
    create_access_token,
    get_current_user,
    get_optional_user,
    hash_password,
    is_hashed,
    verify_password,
)
from .utils import utcnow

logger = logging.getLogger("freezefly")

# hash หลอกไว้เทียบเวลาตอนไม่พบอีเมล ป้องกันการเดาว่าอีเมลไหนมีในระบบจากความเร็วตอบกลับ
_DUMMY_HASH = hash_password("freezefly-dummy-password")


# ------------------------------------------------------------ startup tasks
def seed_mock_data(db: Session) -> None:
    if db.query(models.Flight).count() == 0:
        now = utcnow()
        db.add_all(
            [
                models.Flight(
                    airline="Thai Airways",
                    flight_number="TG600",
                    origin="BKK",
                    destination="HKG",
                    departure_time=now + timedelta(days=1, hours=8),
                    arrival_time=now + timedelta(days=1, hours=11, minutes=45),
                    price=8500.0,
                    seats_available=45,
                ),
                models.Flight(
                    airline="AirAsia",
                    flight_number="FD302",
                    origin="BKK",
                    destination="CNX",
                    departure_time=now + timedelta(days=2, hours=10),
                    arrival_time=now + timedelta(days=2, hours=11, minutes=15),
                    price=1800.0,
                    seats_available=80,
                ),
                models.Flight(
                    airline="ANA",
                    flight_number="NH848",
                    origin="BKK",
                    destination="HND",
                    departure_time=now + timedelta(days=3, hours=1),
                    arrival_time=now + timedelta(days=3, hours=8, minutes=50),
                    price=18500.0,
                    seats_available=20,
                ),
            ]
        )

    # ซิงก์ชื่อ/คำอธิบายโปรโมชันให้ตรงกับกฎจริงใน promotions.py เสมอ
    existing = {p.code: p for p in db.query(models.Promotion).all()}
    for code, rule in PROMO_RULES.items():
        promo = existing.get(code)
        if promo is None:
            db.add(models.Promotion(code=code, title=rule.title, description=rule.description))
        else:
            promo.title = rule.title
            promo.description = rule.description

    db.commit()


def migrate_plaintext_passwords(db: Session) -> None:
    """แปลงรหัสผ่านเก่าที่ยังเป็นข้อความธรรมดาให้เป็น bcrypt hash (ทำครั้งเดียวตอนเปิดเซิร์ฟเวอร์)"""
    changed = 0
    for user in db.query(models.User).all():
        if not is_hashed(user.password):
            user.password = hash_password(user.password)
            changed += 1
    if changed:
        db.commit()
        logger.warning("แปลงรหัสผ่านแบบ plaintext เป็น bcrypt hash แล้ว %d บัญชี", changed)


@asynccontextmanager
async def lifespan(_: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_mock_data(db)
        migrate_plaintext_passwords(db)
    yield


app = FastAPI(title="FreezeFly - Flight & Price Freeze API", lifespan=lifespan)

_DEFAULT_ORIGINS = ",".join(
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5500",  # VS Code Live Server
        "http://127.0.0.1:5500",
        "null",  # เปิดไฟล์ HTML ตรง ๆ ด้วย file://
    ]
)
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,  # ใช้ Bearer token ใน header ไม่ได้ใช้ cookie
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------- helpers
def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _ensure_freeze_usable(db: Session, freeze: models.PriceFreeze) -> None:
    """สิทธิ์ตรึงราคาต้อง active และยังไม่เลยเวลา (เช็กเวลาจริงทุกครั้ง ไม่พึ่งสถานะที่อาจล้าหลัง)"""
    if freeze.status == "converted":
        raise _bad_request("สิทธิ์ตรึงราคานี้ถูกใช้งานไปแล้ว")
    if freeze.status == "active" and utcnow() > freeze.expires_at:
        freeze.status = "expired"
        db.commit()
    if freeze.status != "active":
        raise _bad_request("สิทธิ์ตรึงราคานี้หมดอายุแล้ว")


def _create_booking(
    db: Session,
    *,
    user: models.User,
    flight: models.Flight,
    freeze: Optional[models.PriceFreeze],
    passenger_name: str,
    passenger_email: str,
    promo_code: Optional[str],
) -> models.Booking:
    """ขั้นตอนออกตั๋วเดียวสำหรับทุกเส้นทาง: คิดราคา -> ใช้สิทธิ์ freeze -> ตัดที่นั่ง -> บันทึก
    ทำใน transaction เดียว ถ้าขั้นไหนพลาดจะ rollback ทั้งหมด"""
    base_price = freeze.frozen_price if freeze else flight.price

    discount = 0.0
    promo_used: Optional[str] = None
    if promo_code and promo_code.strip():
        result = evaluate_promo(db, promo_code, base_price, user=user, flight=flight)
        discount, promo_used = result.discount, result.code
    final_price = round(max(0.0, base_price - discount), 2)

    try:
        if freeze:
            # เคลมสิทธิ์แบบ atomic กันการกดแปลงซ้ำพร้อมกัน
            claimed = (
                db.query(models.PriceFreeze)
                .filter(models.PriceFreeze.id == freeze.id, models.PriceFreeze.status == "active")
                .update({"status": "converted"}, synchronize_session=False)
            )
            if claimed != 1:
                raise _bad_request("สิทธิ์ตรึงราคานี้ถูกใช้งานไปแล้ว")

        reserved = (
            db.query(models.Flight)
            .filter(models.Flight.id == flight.id, models.Flight.seats_available > 0)
            .update(
                {models.Flight.seats_available: models.Flight.seats_available - 1},
                synchronize_session=False,
            )
        )
        if reserved != 1:
            raise _bad_request("ขออภัย ที่นั่งเที่ยวบินนี้เต็มแล้ว")

        booking = models.Booking(
            user_id=user.id,
            flight_id=flight.id,
            freeze_id=freeze.id if freeze else None,
            passenger_name=passenger_name,
            passenger_email=passenger_email,
            total_price=final_price,
            status="confirmed",
        )
        db.add(booking)
        db.flush()

        if promo_used:
            db.add(
                models.PromoRedemption(user_id=user.id, code=promo_used, booking_id=booking.id)
            )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise _bad_request("คุณใช้โค้ดส่วนลดนี้ไปแล้ว (โค้ดใช้ได้ครั้งเดียวต่อบัญชี)")

    db.refresh(booking)
    return booking


@app.get("/")
def root():
    return {"message": "FreezeFly API Service is Running"}


# --------------------------------------------------- 1. Authentication
@app.post(
    "/auth/register",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == user.username).first():
        raise _bad_request("Username นี้ถูกใช้งานแล้ว")
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise _bad_request("อีเมลนี้ถูกใช้งานแล้ว")

    new_user = models.User(
        username=user.username,
        email=user.email,
        password=hash_password(user.password),
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _bad_request("Username หรืออีเมลนี้ถูกใช้งานแล้ว")
    db.refresh(new_user)
    return new_user


@app.post("/auth/login")
def login_user(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    password_ok = verify_password(credentials.password, user.password if user else _DUMMY_HASH)
    if not user or not password_ok:
        raise HTTPException(status_code=401, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    return {
        "message": "เข้าสู่ระบบสำเร็จ",
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
    }


# ------------------------------------------------------------ 2. Flights
@app.get("/flights", response_model=List[schemas.FlightResponse])
def search_flights(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Flight)
    if origin:
        query = query.filter(models.Flight.origin.ilike(f"%{origin}%"))
    if destination:
        query = query.filter(models.Flight.destination.ilike(f"%{destination}%"))
    return query.all()


@app.get("/flights/{flight_id}", response_model=schemas.FlightResponse)
def get_flight(
    flight_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    flight = db.get(models.Flight, flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลเที่ยวบินนี้")
    return flight


# ------------------------------------------------------- 3. Price Freeze
@app.post(
    "/freeze/create",
    response_model=schemas.PriceFreezeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_price_freeze(
    freeze_data: schemas.PriceFreezeCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    flight = db.get(models.Flight, freeze_data.flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลเที่ยวบิน")
    if flight.seats_available <= 0:
        raise _bad_request("ขออภัย ที่นั่งเที่ยวบินนี้เต็มแล้ว")

    fee_percentage = 0.05 if freeze_data.hours <= 24 else 0.08
    new_freeze = models.PriceFreeze(
        user_id=current_user.id,
        flight_id=flight.id,
        frozen_price=flight.price,
        freeze_fee=round(flight.price * fee_percentage, 2),
        expires_at=utcnow() + timedelta(hours=freeze_data.hours),
        status="active",
    )
    db.add(new_freeze)
    db.commit()
    db.refresh(new_freeze)
    return new_freeze


@app.get("/freeze/user/{user_id}", response_model=List[schemas.PriceFreezeResponse])
def get_user_freezes(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงข้อมูลของผู้ใช้อื่น")

    freezes = db.query(models.PriceFreeze).filter(models.PriceFreeze.user_id == user_id).all()
    now = utcnow()
    changed = False
    for freeze in freezes:
        if freeze.status == "active" and now > freeze.expires_at:
            freeze.status = "expired"
            changed = True
    if changed:
        db.commit()
    return freezes


@app.post("/freeze/convert/{freeze_id}", response_model=schemas.BookingResponse)
def convert_freeze_to_booking(
    freeze_id: int,
    data: Optional[schemas.ConvertRequest] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = data or schemas.ConvertRequest()

    freeze = db.get(models.PriceFreeze, freeze_id)
    if not freeze:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลรายการตรึงราคา")
    if freeze.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ใช้งานรายการตรึงราคาของผู้ใช้อื่น")

    _ensure_freeze_usable(db, freeze)

    return _create_booking(
        db,
        user=current_user,
        flight=freeze.flight,
        freeze=freeze,
        passenger_name=data.passenger_name or current_user.username,
        passenger_email=str(data.passenger_email or current_user.email),
        promo_code=data.promo_code,
    )


# --------------------------------------------------------- 4. Bookings
@app.post(
    "/bookings/create",
    response_model=schemas.BookingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_booking(
    booking_data: schemas.BookingCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    flight = db.get(models.Flight, booking_data.flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลเที่ยวบิน")

    freeze = None
    if booking_data.freeze_id:
        freeze = db.get(models.PriceFreeze, booking_data.freeze_id)
        if not freeze or freeze.user_id != current_user.id:
            raise _bad_request("สิทธิ์ตรึงราคาไม่ถูกต้อง")
        if freeze.flight_id != flight.id:
            raise _bad_request("สิทธิ์ตรึงราคานี้ไม่ได้ใช้กับเที่ยวบินที่เลือก")
        _ensure_freeze_usable(db, freeze)

    return _create_booking(
        db,
        user=current_user,
        flight=flight,
        freeze=freeze,
        passenger_name=booking_data.passenger_name,
        passenger_email=str(booking_data.passenger_email),
        promo_code=booking_data.promo_code,
    )


@app.get("/bookings/user/{user_id}", response_model=List[schemas.BookingResponse])
def get_user_bookings(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงข้อมูลของผู้ใช้อื่น")
    return db.query(models.Booking).filter(models.Booking.user_id == user_id).all()


# ------------------------------------------- 5. Promotions & Contact
@app.get("/promotions", response_model=List[schemas.PromotionResponse])
def get_promotions(db: Session = Depends(get_db)):
    return db.query(models.Promotion).all()


@app.post("/promotions/validate")
def validate_promotion(
    data: schemas.PromoCheckRequest,
    current_user: Optional[models.User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    flight = db.get(models.Flight, data.flight_id) if data.flight_id else None
    result = evaluate_promo(db, data.code, data.price, user=current_user, flight=flight)
    return {
        "valid": True,
        "code": result.code,
        "discount_amount": result.discount,
        "final_price": result.final_price,
        "title": result.promo.title,
    }


@app.post("/contact", status_code=status.HTTP_201_CREATED)
def create_contact_message(data: schemas.ContactCreate, db: Session = Depends(get_db)):
    db.add(
        models.ContactMessage(
            name=data.name.strip(),
            email=str(data.email),
            subject=data.subject.strip(),
            message=data.message.strip(),
        )
    )
    db.commit()
    return {"status": "success", "message": "บันทึกข้อความติดต่อเรียบร้อยแล้ว"}