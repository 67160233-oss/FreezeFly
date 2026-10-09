import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import freeze_policy, models, price_ai, pricing, schemas
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
# เที่ยวบินตัวอย่าง: (เลขเที่ยวบิน, สายการบิน, ต้นทาง, ปลายทาง, ออกอีกกี่ชั่วโมงนับจากตอนสร้าง, เวลาบิน (นาที), ราคา, ที่นั่ง)
DEMO_FLIGHTS = [
    ("TG600", "Thai Airways", "BKK", "HKG", 32, 225, 8500.0, 45),
    ("FD302", "AirAsia", "BKK", "CNX", 58, 75, 1800.0, 80),
    ("NH848", "ANA", "BKK", "HND", 73, 470, 18500.0, 20),
    ("KE652", "Korean Air", "BKK", "ICN", 24 * 9, 330, 12900.0, 30),
    ("TG403", "Thai Airways", "BKK", "SIN", 24 * 20, 145, 6400.0, 60),
    ("TG640", "Thai Airways", "BKK", "HKG", 24 * 35, 225, 8500.0, 50),
    ("NH806", "ANA", "BKK", "HND", 24 * 48, 360, 18500.0, 40),
]
# วนรอบทุก 8 สัปดาห์ เที่ยวบินตัวอย่างจึงกระจายตั้งแต่ใกล้วันบินจนถึงล่วงหน้าไกล
# (ค่าธรรมเนียมจาก AI ต่างกันชัดเจนตามระยะเวลาก่อนบิน)
DEMO_CYCLE = timedelta(days=56)


def refresh_demo_schedule(db: Session) -> None:
    """เที่ยวบินตัวอย่างวนเป็นรอบทุก 56 วัน เที่ยวไหนปิดขายไปแล้วจะเลื่อนไปรอบถัดไป
    หน้าเว็บจึงมีเที่ยวบินให้ทดลองเสมอ (ใช้กับข้อมูลจำลองเท่านั้น ระบบจริงจะดึงตารางบินจากสายการบิน)"""
    numbers = [f[0] for f in DEMO_FLIGHTS]
    now = utcnow()
    changed = False
    for flight in db.query(models.Flight).filter(models.Flight.flight_number.in_(numbers)).all():
        while not freeze_policy.is_bookable(flight.departure_time, now):
            flight.departure_time += DEMO_CYCLE
            flight.arrival_time += DEMO_CYCLE
            changed = True
    if changed:
        db.commit()


def seed_mock_data(db: Session) -> None:
    # เพิ่มเฉพาะเที่ยวบินที่ยังไม่มี (ฐานข้อมูลเดิมบน Render จะได้เส้นทาง ICN และ SIN เพิ่มโดยไม่กระทบข้อมูลเก่า)
    existing_numbers = {row[0] for row in db.query(models.Flight.flight_number).all()}
    now = utcnow()
    for number, airline, origin, dest, offset_h, duration_min, price, seats in DEMO_FLIGHTS:
        if number in existing_numbers:
            continue
        departure = now + timedelta(hours=offset_h)
        db.add(models.Flight(
            airline=airline, flight_number=number, origin=origin, destination=dest,
            departure_time=departure, arrival_time=departure + timedelta(minutes=duration_min),
            price=price, seats_available=seats,
        ))

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


# index=True บน Column ใน models.py จะมีผลเฉพาะตอนสร้างตารางใหม่ (fresh install) เท่านั้น
# ฐานข้อมูลที่ deploy ใช้งานจริงอยู่แล้วมีตารางอยู่ก่อน create_all() จะไม่ไปแก้ตารางเดิมให้
# จึงต้องรัน CREATE INDEX แยกตรงนี้ (เหมือน 03-create-index.sql ในแล็บ index: สร้าง index
# "หลังจาก" มีข้อมูลอยู่แล้ว) ชื่อ index ตั้งให้ตรงกับที่ SQLAlchemy จะตั้งให้เองจาก index=True
# (รูปแบบ ix_<table>_<column>) เพื่อไม่ให้ซ้ำซ้อนกันระหว่าง 2 ทาง
INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS ix_price_freezes_user_id ON price_freezes (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_price_freezes_flight_id ON price_freezes (flight_id)",
    "CREATE INDEX IF NOT EXISTS ix_bookings_user_id ON bookings (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_bookings_flight_id ON bookings (flight_id)",
]


def apply_indexes(db: Session) -> None:
    for stmt in INDEX_STATEMENTS:
        db.execute(text(stmt))
    db.commit()


# create_all() สร้างตารางใหม่ได้ แต่ไม่เพิ่มคอลัมน์ใหม่ให้ตารางที่มีอยู่แล้ว
# ฐานข้อมูลเดิมจึงต้องเพิ่มคอลัมน์เอง (ข้อมูลและบัญชีผู้ใช้เดิมไม่หาย)
COLUMN_MIGRATIONS = [
    ("bookings", "market_price", "FLOAT"),
    ("bookings", "protection_paid", "FLOAT DEFAULT 0"),
    ("bookings", "fee_credit", "FLOAT"),
    ("price_freezes", "refund_reason", "VARCHAR"),
]


def apply_column_migrations() -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in COLUMN_MIGRATIONS:
            if column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                logger.warning("เพิ่มคอลัมน์ %s.%s ให้ฐานข้อมูลเดิมแล้ว", table, column)


@asynccontextmanager
async def lifespan(_: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    apply_column_migrations()
    with SessionLocal() as db:
        apply_indexes(db)
        seed_mock_data(db)
        refresh_demo_schedule(db)
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


class _SoldOut(Exception):
    """ที่นั่งหมดระหว่างออกตั๋ว (ใช้แยกกรณีนี้ออกจาก error อื่นใน transaction)"""


def _refund_freeze(db: Session, freeze: models.PriceFreeze, reason: str = "soldout") -> float:
    """คืนค่าธรรมเนียมเต็มจำนวนในกรณีที่ลูกค้าไม่ได้ผิด:
    soldout = ที่นั่งเต็มก่อนออกตั๋ว, price_cap = ราคาขึ้นเกินเพดานความคุ้มครองแล้วลูกค้าเลือกยกเลิก
    (ระบบชำระเงินยังเป็นแบบจำลอง จึงบันทึกเป็นสถานะ refunded ให้ระบบจ่ายเงินดำเนินการต่อ)"""
    db.query(models.PriceFreeze).filter(
        models.PriceFreeze.id == freeze.id, models.PriceFreeze.status == "active"
    ).update({"status": "refunded", "refund_reason": reason}, synchronize_session=False)
    db.commit()
    db.refresh(freeze)
    return freeze.freeze_fee


def _soldout_refund_message(fee: float) -> str:
    return f"ขออภัย ที่นั่งเที่ยวบินนี้เต็มแล้ว ระบบคืนค่าธรรมเนียมตรึงราคา ฿{fee:,.0f} ให้คุณเต็มจำนวน"


def _ensure_freeze_usable(db: Session, freeze: models.PriceFreeze) -> None:
    """สิทธิ์ตรึงราคาต้อง active และยังไม่เลยเวลา (เช็กเวลาจริงทุกครั้ง ไม่พึ่งสถานะที่อาจล้าหลัง)"""
    if freeze.status == "converted":
        raise _bad_request("สิทธิ์ตรึงราคานี้ถูกใช้งานไปแล้ว")
    if freeze.status == "refunded":
        why = "ราคาขึ้นเกินเพดานความคุ้มครอง" if freeze.refund_reason == "price_cap" else "ที่นั่งเต็ม"
        raise _bad_request(f"สิทธิ์นี้ถูกยกเลิกเพราะ{why} และคืนค่าธรรมเนียมแล้ว")
    if freeze.status == "active" and utcnow() <= freeze.expires_at and freeze.flight.seats_available <= 0:
        raise _bad_request(_soldout_refund_message(_refund_freeze(db, freeze)))
    if freeze.status == "active" and not freeze_policy.is_bookable(freeze.flight.departure_time):
        freeze.status = "expired"
        db.commit()
        raise _bad_request("เที่ยวบินนี้ปิดการขายแล้ว สิทธิ์ตรึงราคาจึงใช้ไม่ได้")
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
    accept_excess: bool = False,
) -> models.Booking:
    """ขั้นตอนออกตั๋วเดียวสำหรับทุกเส้นทาง: คิดราคา -> ใช้สิทธิ์ freeze -> ตัดที่นั่ง -> บันทึก
    ทำใน transaction เดียว ถ้าขั้นไหนพลาดจะ rollback ทั้งหมด"""
    market_price = pricing.current_price(flight)
    if freeze:
        quote = freeze_policy.conversion_quote(freeze.frozen_price, market_price, freeze.freeze_fee)
        if quote["exceeds_cap"] and not accept_excess:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=(
                f"ราคาตลาดขึ้นเป็น ฿{market_price:,.0f} เกินเพดานความคุ้มครอง ฿{quote['cap_amount']:,.0f} "
                f"ต้องจ่ายส่วนเกินเอง ฿{quote['excess']:,.0f} หรือยกเลิกสิทธิ์เพื่อรับค่าธรรมเนียมคืนเต็มจำนวน"))
        ticket_price, protection, fee_credit = quote["ticket_price"], quote["covered"], quote["fee_credit"]
    else:
        ticket_price, protection, fee_credit = market_price, 0.0, 0.0

    discount = 0.0
    promo_used: Optional[str] = None
    if promo_code and promo_code.strip():
        result = evaluate_promo(db, promo_code, ticket_price, user=user, flight=flight)
        discount, promo_used = result.discount, result.code
    final_price = round(max(0.0, ticket_price - discount), 2)

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
            raise _SoldOut()

        booking = models.Booking(
            user_id=user.id,
            flight_id=flight.id,
            freeze_id=freeze.id if freeze else None,
            passenger_name=passenger_name,
            passenger_email=passenger_email,
            total_price=final_price,
            market_price=market_price,
            protection_paid=protection,
            fee_credit=fee_credit,
            status="confirmed",
        )
        db.add(booking)
        db.flush()

        if promo_used:
            db.add(
                models.PromoRedemption(user_id=user.id, code=promo_used, booking_id=booking.id)
            )
        db.commit()
    except _SoldOut:
        db.rollback()
        if freeze:
            raise _bad_request(_soldout_refund_message(_refund_freeze(db, freeze)))
        raise _bad_request("ขออภัย ที่นั่งเที่ยวบินนี้เต็มแล้ว")
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise _bad_request("คุณใช้โค้ดส่วนลดนี้ไปแล้ว (โค้ดใช้ได้ครั้งเดียวต่อบัญชี)")

    db.refresh(booking)
    return booking


@app.get("/ai/model-info")
def ai_model_info():
    """รุ่นของโมเดล AI และผลการทดสอบ (เปิดเผยเพื่อความโปร่งใส)"""
    return price_ai.model_info()


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
    refresh_demo_schedule(db)
    sales_open_after = utcnow() + timedelta(hours=freeze_policy.BOOKING_CUTOFF_HOURS)
    query = db.query(models.Flight).filter(models.Flight.departure_time > sales_open_after)
    if origin:
        query = query.filter(models.Flight.origin.ilike(f"%{origin}%"))
    if destination:
        query = query.filter(models.Flight.destination.ilike(f"%{destination}%"))
    return query.order_by(models.Flight.departure_time).all()


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

    now = utcnow()
    options = freeze_policy.freeze_options_for(flight, now)
    chosen = next(o for o in options if o["hours"] == freeze_data.hours)  # schema ตรวจแล้วว่าเป็นค่าที่อนุญาต
    if not chosen["available"]:
        usable = [o["label"] for o in options if o["available"]]
        hint = f" · ระยะที่เลือกได้สำหรับเที่ยวบินนี้: {', '.join(usable)}" if usable else ""
        raise _bad_request(f"ตรึงราคา {chosen['label']} ไม่ได้: {chosen['reason']}{hint}")

    # ราคาที่ล็อกและค่าธรรมเนียมมาจากการคำนวณเดียวกัน ณ เวลาเดียวกัน
    new_freeze = models.PriceFreeze(
        user_id=current_user.id,
        flight_id=flight.id,
        frozen_price=pricing.current_price(flight, now),
        freeze_fee=chosen["fee_amount"],
        expires_at=chosen["expires_at"],
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
        if freeze.status != "active":
            continue
        if now > freeze.expires_at or not freeze_policy.is_bookable(freeze.flight.departure_time, now):
            freeze.status = "expired"
            changed = True
        elif freeze.flight.seats_available <= 0:
            freeze.status = "refunded"
            freeze.refund_reason = "soldout"
            changed = True
    if changed:
        db.commit()
    return freezes


def _get_own_freeze(db: Session, freeze_id: int, user: models.User) -> models.PriceFreeze:
    freeze = db.get(models.PriceFreeze, freeze_id)
    if not freeze:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลรายการตรึงราคา")
    if freeze.user_id != user.id:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ใช้งานรายการตรึงราคาของผู้ใช้อื่น")
    return freeze


@app.get("/freeze/{freeze_id}/quote", response_model=schemas.ConversionQuote)
def get_conversion_quote(
    freeze_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ถ้าออกตั๋วตอนนี้ ราคาตลาดเป็นเท่าไหร่ เราคุ้มครองเท่าไหร่ และลูกค้าต้องจ่ายเท่าไหร่"""
    freeze = _get_own_freeze(db, freeze_id, current_user)
    _ensure_freeze_usable(db, freeze)
    return freeze_policy.conversion_quote(freeze.frozen_price, pricing.current_price(freeze.flight), freeze.freeze_fee)


@app.post("/freeze/{freeze_id}/cancel", response_model=schemas.PriceFreezeResponse)
def cancel_freeze_with_refund(
    freeze_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ยกเลิกพร้อมรับค่าธรรมเนียมคืน ได้เฉพาะเมื่อราคาขึ้นเกินเพดานความคุ้มครอง (เราคุ้มครองตามที่สัญญาไม่ได้)"""
    freeze = _get_own_freeze(db, freeze_id, current_user)
    _ensure_freeze_usable(db, freeze)
    quote = freeze_policy.conversion_quote(freeze.frozen_price, pricing.current_price(freeze.flight), freeze.freeze_fee)
    if not quote["exceeds_cap"]:
        raise _bad_request("ยกเลิกพร้อมรับค่าธรรมเนียมคืนได้เฉพาะเมื่อราคาตลาดขึ้นเกินเพดานความคุ้มครอง "
                           "ถ้าไม่ต้องการตั๋วแล้ว ปล่อยให้สิทธิ์หมดอายุได้เลย (ค่าธรรมเนียมไม่คืน)")
    _refund_freeze(db, freeze, reason="price_cap")
    return freeze


@app.post("/freeze/convert/{freeze_id}", response_model=schemas.BookingResponse)
def convert_freeze_to_booking(
    freeze_id: int,
    data: Optional[schemas.ConvertRequest] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = data or schemas.ConvertRequest()
    freeze = _get_own_freeze(db, freeze_id, current_user)
    _ensure_freeze_usable(db, freeze)

    return _create_booking(
        db,
        user=current_user,
        flight=freeze.flight,
        freeze=freeze,
        passenger_name=data.passenger_name or current_user.username,
        passenger_email=str(data.passenger_email or current_user.email),
        promo_code=data.promo_code,
        accept_excess=data.accept_excess,
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
    if not freeze_policy.is_bookable(flight.departure_time):
        raise _bad_request(f"เที่ยวบินนี้ปิดการขายแล้ว (ปิดก่อนเครื่องออก {freeze_policy.BOOKING_CUTOFF_HOURS} ชั่วโมง)")

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
        accept_excess=booking_data.accept_excess,
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