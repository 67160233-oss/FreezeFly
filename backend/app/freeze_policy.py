"""กฎการตรึงราคา: ระยะเวลา ค่าธรรมเนียม เวลาปิดขาย และการคิดเงินตอนออกตั๋ว (แหล่งเดียว)

หลักคิด:
1. ค่าธรรมเนียมคิดตามความเสี่ยงที่ AI ประเมิน (price_ai.py) เส้นทางที่ราคานิ่งจ่ายถูก เส้นทางผันผวนจ่ายแพง
2. ปิดขาย/ออกตั๋วก่อนเครื่องออก BOOKING_CUTOFF_HOURS ชั่วโมง และสิทธิ์ตรึงราคาต้องหมดก่อนปิดขายเสมอ
3. ตั๋วราคาต่ำกว่า MIN_FREEZABLE_PRICE ตรึงไม่ได้ (ค่าธรรมเนียมไม่คุ้มกับส่วนต่างที่อาจเกิด)
4. ตอนออกตั๋ว (ดู conversion_quote):
   - ราคาลง → ลูกค้าจ่ายราคาใหม่ที่ถูกกว่า
   - ราคาขึ้น → เราจ่ายส่วนต่างให้ ไม่เกิน COVERAGE_CAP_RATE ของราคาที่ล็อก ส่วนที่เกินเพดานลูกค้าเลือกจ่ายเอง
     หรือยกเลิกและรับค่าธรรมเนียมคืน
   - ค่าธรรมเนียมเป็นทุนสำหรับจ่ายส่วนต่างก่อน ส่วนที่ไม่ได้ใช้หักเป็นค่าตั๋ว
     ผลคือลูกค้าไม่จ่ายแพงกว่าราคาตลาด และเราขาดทุนเฉพาะเมื่อราคาขึ้นมากกว่าค่าธรรมเนียม
"""

from datetime import datetime, timedelta
from typing import List, Optional

from . import price_ai, pricing
from .utils import utcnow

FREEZE_OPTIONS = [
    {"hours": 24, "label": "24 ชั่วโมง"},
    {"hours": 72, "label": "3 วัน"},
    {"hours": 168, "label": "7 วัน"},
]
ALLOWED_HOURS = tuple(o["hours"] for o in FREEZE_OPTIONS)

BOOKING_CUTOFF_HOURS = 3
MIN_FREEZABLE_PRICE = 2500
COVERAGE_CAP_RATE = 0.20


def option_for(hours: int) -> Optional[dict]:
    return next((o for o in FREEZE_OPTIONS if o["hours"] == hours), None)


def booking_deadline(departure_time: datetime) -> datetime:
    """เวลาปิดขายตั๋วของเที่ยวบิน"""
    return departure_time - timedelta(hours=BOOKING_CUTOFF_HOURS)


def is_bookable(departure_time: datetime, now: Optional[datetime] = None) -> bool:
    return (now or utcnow()) < booking_deadline(departure_time)


def freeze_options_for(flight, now: Optional[datetime] = None) -> List[dict]:
    """ตัวเลือกระยะตรึงราคาของเที่ยวบิน พร้อมค่าธรรมเนียมจาก AI และเหตุผลถ้าเลือกไม่ได้"""
    now = now or utcnow()
    deadline = booking_deadline(flight.departure_time)
    price = pricing.current_price(flight, now)
    out = []
    for o in FREEZE_OPTIONS:
        expires_at = now + timedelta(hours=o["hours"])
        if now >= deadline:
            reason = "เที่ยวบินนี้ปิดการขายแล้ว"
        elif price < MIN_FREEZABLE_PRICE:
            reason = f"ตั๋วราคาต่ำกว่า ฿{MIN_FREEZABLE_PRICE:,} ไม่เปิดให้ตรึง เพราะค่าธรรมเนียมไม่คุ้มกับส่วนต่างที่อาจเกิด"
        elif expires_at > deadline:
            reason = "สิทธิ์จะหมดหลังเวลาปิดขายตั๋ว (เครื่องออกก่อน)"
        else:
            reason = None
        risk = price_ai.assess(flight, o["hours"], now) if reason is None else None
        out.append({
            "hours": o["hours"],
            "label": o["label"],
            "fee_rate": risk["fee_rate"] if risk else 0.0,
            "fee_amount": round(price * risk["fee_rate"], 0) if risk else 0.0,
            "rise_probability": risk["rise_probability"] if risk else None,
            "coverage_cap_amount": round(price * COVERAGE_CAP_RATE, 0),
            "expires_at": expires_at,
            "available": reason is None,
            "reason": reason,
        })
    return out


def conversion_quote(frozen_price: float, market_price: float, fee_paid: float,
                     cap_rate: float = COVERAGE_CAP_RATE) -> dict:
    """คิดเงินตอนออกตั๋วจากสิทธิ์ตรึงราคา (ฟังก์ชันล้วน ไม่แตะฐานข้อมูล)

    ticket_price  : ราคาตั๋วที่ลูกค้าต้องจ่าย (ก่อนหักค่าธรรมเนียม/ส่วนลด)
    covered       : ส่วนต่างที่เราจ่ายแทนลูกค้า (ไม่เกินเพดาน)
    excess        : ส่วนต่างที่เกินเพดาน ลูกค้าต้องจ่ายเองถ้ายังต้องการออกตั๋ว
    fee_credit    : ค่าธรรมเนียมส่วนที่ไม่ได้ใช้จ่ายส่วนต่าง หักออกจากค่าตั๋ว
    customer_total: เงินทั้งหมดที่ลูกค้าจ่าย รวมค่าธรรมเนียมที่จ่ายไปตอนตรึงแล้ว
    company_net   : กำไร/ขาดทุนของเราจากการคุ้มครองราคาครั้งนี้ (ไม่รวมค่าคอมมิชชัน)
    """
    cap_amount = round(frozen_price * cap_rate, 2)
    if market_price <= frozen_price:
        increase = covered = excess = 0.0
        ticket_price = market_price
    else:
        increase = market_price - frozen_price
        covered = min(increase, cap_amount)
        excess = increase - covered
        ticket_price = frozen_price + excess
    fee_credit = max(0.0, fee_paid - covered)
    amount_due = max(0.0, ticket_price - fee_credit)
    customer_total = fee_paid + amount_due
    return {
        "frozen_price": round(frozen_price, 2),
        "market_price": round(market_price, 2),
        "price_change": round(market_price - frozen_price, 2),
        "cap_amount": cap_amount,
        "covered": round(covered, 2),
        "excess": round(excess, 2),
        "exceeds_cap": excess > 0,
        "ticket_price": round(ticket_price, 2),
        "fee_paid": round(fee_paid, 2),
        "fee_credit": round(fee_credit, 2),
        "amount_due": round(amount_due, 2),
        "customer_total": round(customer_total, 2),
        "savings_vs_market": round(market_price - customer_total, 2),
        "company_net": round((fee_paid - fee_credit) - covered, 2),
    }