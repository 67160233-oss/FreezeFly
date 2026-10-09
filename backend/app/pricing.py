"""ตัวจำลองราคาตั๋วของสายการบิน (ใช้แทนราคาจริงจนกว่าจะเชื่อมต่อกับสายการบินได้)

ราคา ณ เวลาหนึ่ง = ราคาฐาน × เส้นโค้งการจองล่วงหน้า × ตัวคูณช่วงเทศกาล × ความผันผวนรายวัน

- เส้นโค้งการจองล่วงหน้า: ซื้อล่วงหน้านานราคาถูก ใกล้วันบินราคาขึ้นเร็ว
- ช่วงเทศกาล: ปีใหม่และสงกรานต์ ราคาสูงกว่าปกติ
- ความผันผวนรายวัน: แต่ละเส้นทางขยับไม่เท่ากัน และมีแนวโน้มกลับสู่ระดับปกติ (AR(1))

ผลลัพธ์ "กำหนดได้แน่นอน" (deterministic) เที่ยวบินเดียวกัน เวลาเดียวกัน ได้ราคาเท่ากันเสมอ
ราคาเปลี่ยนวันละครั้ง ไม่ต้องเก็บประวัติราคาไว้ในฐานข้อมูล
ถ้าวันหนึ่งเชื่อมต่อสายการบินจริง ให้เปลี่ยนแค่ฟังก์ชัน current_price() ในไฟล์นี้
"""

import hashlib
import math
import random
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

from .utils import utcnow

# ความผันผวนรายวันของแต่ละเส้นทาง (ส่วนเบี่ยงเบนมาตรฐานของการขยับต่อวัน)
ROUTE_VOLATILITY = {
    ("BKK", "CNX"): 0.02,
    ("BKK", "SIN"): 0.025,
    ("BKK", "HKG"): 0.03,
    ("BKK", "ICN"): 0.035,
    ("BKK", "HND"): 0.04,
}
DEFAULT_VOLATILITY = 0.03
MEAN_REVERSION = 0.8         # ความผันผวนวันนี้เหลือติดไปถึงพรุ่งนี้ 80% (ราคาแกว่งรอบระดับปกติราว ±3–7%)
SALES_OPEN_DAYS = 120        # เปิดขายตั๋วล่วงหน้า 120 วัน
PEAK_MULTIPLIER = 1.35

# ช่วงเทศกาล (เดือน, วัน) เริ่ม - สิ้นสุด นับตามวันที่เครื่องออก
PEAK_PERIODS = [
    ((12, 20), (12, 31)),   # ปีใหม่
    ((1, 1), (1, 5)),
    ((4, 8), (4, 17)),      # สงกรานต์
]


def route_volatility(origin: str, destination: str) -> float:
    return ROUTE_VOLATILITY.get((origin.upper(), destination.upper()), DEFAULT_VOLATILITY)


def booking_curve(days_to_departure: float) -> float:
    """ตัวคูณจากระยะเวลาก่อนบิน: ~0.85 เมื่อซื้อล่วงหน้ามาก, 1.0 ที่ 14 วัน, ~1.45 วันบิน"""
    return 0.85 + 0.6 * math.exp(-max(0.0, days_to_departure) / 10.0)


def is_peak(departure_time: datetime) -> bool:
    md = (departure_time.month, departure_time.day)
    return any(start <= md <= end for start, end in PEAK_PERIODS)


def _seed(*parts) -> int:
    return int(hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


@lru_cache(maxsize=4096)
def _noise_path(flight_key: str, departure_iso: str, sigma: float) -> tuple:
    """ค่าความผันผวนสะสมของทุกวันตั้งแต่เปิดขายจนถึงวันบิน (log scale)"""
    rng = random.Random(_seed(flight_key, departure_iso))
    x, path = 0.0, []
    for _ in range(SALES_OPEN_DAYS + 2):
        x = MEAN_REVERSION * x + rng.gauss(0.0, sigma)
        path.append(x)
    return tuple(path)


def day_index(departure_time: datetime, at: datetime) -> int:
    """ลำดับวันนับจากวันเปิดขาย (ราคาเปลี่ยนวันละครั้ง)"""
    opened = departure_time - timedelta(days=SALES_OPEN_DAYS)
    return max(0, min(SALES_OPEN_DAYS + 1, (at - opened).days))


def price_state(flight_key: str, origin: str, destination: str, base_price: float,
                departure_time: datetime, at: Optional[datetime] = None) -> dict:
    """ราคา ณ เวลา at พร้อมองค์ประกอบที่ AI ใช้เป็นข้อมูลนำเข้า"""
    at = at or utcnow()
    sigma = route_volatility(origin, destination)
    k = day_index(departure_time, at)
    noise = _noise_path(flight_key, departure_time.date().isoformat(), sigma)[k]
    # ราคาคงที่ตลอดทั้งวัน: ใช้จำนวนวันก่อนบิน ณ ต้นวันของ index นั้น
    day_start = departure_time - timedelta(days=SALES_OPEN_DAYS) + timedelta(days=k)
    days_left = (departure_time - day_start).total_seconds() / 86400
    peak = is_peak(departure_time)
    raw = base_price * booking_curve(days_left) * (PEAK_MULTIPLIER if peak else 1.0) * math.exp(noise)
    price = max(round(base_price * 0.6, -1), round(raw, -1))
    return {
        "price": float(price),
        "days_to_departure": max(0.0, (departure_time - at).total_seconds() / 86400),
        "sigma": sigma,
        "is_peak": peak,
        "price_ratio": math.exp(noise),   # ราคาตอนนี้สูง/ต่ำกว่าระดับปกติของวันนี้กี่เท่า
    }


def current_price(flight, at: Optional[datetime] = None) -> float:
    """ราคาปัจจุบันของเที่ยวบิน (flight.price ในฐานข้อมูลคือราคาฐาน)"""
    return price_state(flight.flight_number, flight.origin, flight.destination,
                       flight.price, flight.departure_time, at)["price"]
