"""ใช้โมเดล AI (price_model.json) ประเมินความเสี่ยงราคา ตั้งค่าธรรมเนียม และแนะนำลูกค้า

คำนวณด้วย Python ล้วน ไม่ต้องติดตั้ง scikit-learn บนเซิร์ฟเวอร์
โมเดลสอนด้วย ml/train_price_model.py จากข้อมูลตัวจำลองราคา (ยังไม่ใช่ราคาตลาดจริง)
ถ้าไฟล์โมเดลหายหรือเสีย จะใช้สูตรสำรองแทน ระบบจึงไม่ล่ม
"""

import json
import logging
import math
import struct
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from . import pricing
from .utils import utcnow

logger = logging.getLogger("freezefly.price_ai")
MODEL_PATH = Path(__file__).with_name("price_model.json")

FEE_MIN, FEE_MAX = 0.03, 0.15
FEE_LOADING, FEE_MARGIN = 1.25, 0.015   # ค่าธรรมเนียม = ส่วนต่างที่คาดว่าต้องจ่าย × 1.25 + 1.5% (ต้องตรงกับสคริปต์ฝึก)
RISE_HIGH, RISE_LOW = 0.60, 0.30        # เกณฑ์คำแนะนำ: โอกาสขึ้น ≥60% แนะนำตรึง, ≤30% ราคานิ่ง


@lru_cache(maxsize=1)
def _model() -> Optional[dict]:
    try:
        return json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("โหลดโมเดล AI ไม่ได้ (%s) ใช้สูตรสำรองแทน", e)
        return None


def model_info() -> dict:
    m = _model()
    return {"version": m["version"], "metrics": m["metrics"]} if m else {"version": "fallback", "metrics": {}}


def _f32(v: float) -> float:
    # scikit-learn เทียบค่าแบบ float32 ต้องทำแบบเดียวกันผลถึงจะตรง
    return struct.unpack("f", struct.pack("f", float(v)))[0]


def _predict(part: dict, x: list) -> float:
    x = [_f32(v) for v in x]
    total = 0.0
    for t in part["trees"]:
        n = 0
        while t["l"][n] != -1:
            n = t["l"][n] if x[t["f"][n]] <= t["t"][n] else t["r"][n]
        total += t["v"][n]
    raw = part["init"] + part["learning_rate"] * total
    return 1 / (1 + math.exp(-raw)) if part["output"] == "sigmoid" else raw


def fee_rate_from_payout(payout_frac: float) -> float:
    return min(FEE_MAX, max(FEE_MIN, payout_frac * FEE_LOADING + FEE_MARGIN))


def assess(flight, horizon_h: int, now: Optional[datetime] = None) -> dict:
    """ถ้าตรึงราคาเที่ยวบินนี้ตอนนี้ ระยะ horizon_h ชั่วโมง ความเสี่ยงเป็นอย่างไร"""
    now = now or utcnow()
    s = pricing.price_state(flight.flight_number, flight.origin, flight.destination,
                            flight.price, flight.departure_time, now)
    m = _model()
    if m:
        x = [s["days_to_departure"], horizon_h / 24, s["sigma"], float(s["is_peak"]), s["price_ratio"]]
        payout = min(m["coverage_cap"], max(0.0, _predict(m["payout"], x)))
        rise = _predict(m["rise"], x)
    else:
        # สูตรสำรอง: ความผันผวนตามเวลา + ราคาที่ขึ้นตามเส้นโค้งการจอง
        d = s["days_to_departure"]
        drift = pricing.booking_curve(d - horizon_h / 24) / pricing.booking_curve(d) - 1
        payout = min(0.20, s["sigma"] * math.sqrt(horizon_h / 24) * 0.6 + max(0.0, drift))
        rise = 0.5
    return {
        "price": s["price"],
        "payout_frac": payout,
        "rise_probability": round(rise, 3),
        "fee_rate": round(fee_rate_from_payout(payout), 3),
    }


def advice(flight, booking_deadline: datetime, now: Optional[datetime] = None, can_freeze: bool = True) -> dict:
    """คำแนะนำสำหรับลูกค้า (บอกตรงๆ แม้คำแนะนำจะเป็น "ยังไม่ต้องตรึง")
    can_freeze=False: เที่ยวบินนี้ตรึงไม่ได้ (เช่น ราคาต่ำกว่าขั้นต่ำ) ห้ามแนะนำให้ตรึง"""
    now = now or utcnow()
    hours_left = (booking_deadline - now).total_seconds() / 3600
    if hours_left < 24:
        return {"level": "buy_now", "rise_probability": None, "horizon_label": None,
                "message": "ใกล้เวลาบินแล้ว ราคามักขึ้นต่อเนื่องจนวันบิน ถ้าตัดสินใจแล้วแนะนำให้ซื้อเลย"}
    h, label = (72, "3 วัน") if hours_left >= 72 else (24, "24 ชั่วโมง")
    p = assess(flight, h, now)["rise_probability"]
    if not can_freeze:
        if p <= RISE_LOW:
            return {"level": "stable", "rise_probability": p, "horizon_label": label,
                    "message": f"ราคาค่อนข้างนิ่ง (โอกาสขึ้น {p:.0%} ภายใน {label}) ยังไม่ต้องรีบซื้อ"}
        return {"level": "buy_now", "rise_probability": p, "horizon_label": label,
                "message": f"ราคาอาจขึ้น (โอกาส {p:.0%} ภายใน {label}) เที่ยวบินนี้ตรึงราคาไม่ได้ ถ้าตัดสินใจแล้วแนะนำซื้อเลย"}
    if p >= RISE_HIGH:
        level, msg = "rising", f"ราคามีแนวโน้มขึ้น (โอกาส {p:.0%} ภายใน {label}) แนะนำให้ตรึงราคาไว้"
    elif p <= RISE_LOW:
        level, msg = "stable", f"ราคาค่อนข้างนิ่ง (โอกาสขึ้น {p:.0%} ภายใน {label}) ยังไม่จำเป็นต้องตรึง"
    else:
        level, msg = "uncertain", f"ราคาอาจขยับได้ (โอกาสขึ้น {p:.0%} ภายใน {label}) ตรึงไว้ถ้ายังไม่พร้อมตัดสินใจ"
    return {"level": level, "rise_probability": p, "horizon_label": label, "message": msg}
