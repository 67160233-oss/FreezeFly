from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import models

# สนามบินโซนเอเชียตะวันออก (ใช้ตรวจเงื่อนไขของ ASIAFLY300)
EAST_ASIA_AIRPORTS = {
    "HND", "NRT", "KIX", "NGO", "FUK", "CTS", "OKA",  # ญี่ปุ่น
    "ICN", "GMP", "PUS", "CJU",  # เกาหลีใต้
    "HKG", "MFM", "TPE", "KHH",  # ฮ่องกง มาเก๊า ไต้หวัน
    "PEK", "PKX", "PVG", "SHA", "CAN", "SZX", "CTU",  # จีน
}


@dataclass(frozen=True)
class PromoRule:
    kind: str  # "fixed" = ลดเป็นบาท, "percent" = ลดเป็นเปอร์เซ็นต์ของราคาตั๋ว
    value: float
    title: str
    description: str
    new_users_only: bool = False  # เฉพาะบัญชีที่ยังไม่เคยออกตั๋ว
    east_asia_only: bool = False  # เฉพาะเที่ยวบินที่ต้นทางหรือปลายทางอยู่โซนเอเชียตะวันออก


# กฎส่วนลดทั้งหมดอยู่ที่นี่ที่เดียว (ทุกโค้ดใช้ได้ครั้งเดียวต่อบัญชี)
PROMO_RULES = {
    "NEWUSER2026": PromoRule(
        kind="fixed",
        value=100.0,
        title="สมาชิกใหม่ ลด ฿100",
        description="ส่วนลดค่าตั๋ว ฿100 สำหรับสมาชิกใหม่ที่ยังไม่เคยออกตั๋ว (ใช้ได้ครั้งเดียวต่อบัญชี)",
        new_users_only=True,
    ),
    "HALFPRICE50": PromoRule(
        kind="percent",
        value=50.0,
        title="ลด 50% ค่าตั๋ว",
        description="รับส่วนลด 50% ของราคาตั๋วเมื่อออกตั๋ว (ใช้ได้ครั้งเดียวต่อบัญชี)",
    ),
    "ASIAFLY300": PromoRule(
        kind="fixed",
        value=300.0,
        title="บินเอเชียตะวันออก ลด ฿300",
        description="ส่วนลดค่าตั๋ว ฿300 สำหรับเที่ยวบินโซนเอเชียตะวันออก เช่น ญี่ปุ่น เกาหลี ฮ่องกง (ใช้ได้ครั้งเดียวต่อบัญชี)",
        east_asia_only=True,
    ),
}


@dataclass(frozen=True)
class PromoResult:
    promo: models.Promotion
    code: str
    discount: float
    final_price: float


def normalize_code(code: str) -> str:
    return code.strip().upper()


def compute_discount(rule: PromoRule, price: float) -> float:
    raw = price * rule.value / 100 if rule.kind == "percent" else rule.value
    return round(min(raw, price), 2)  # ห้ามลดเกินราคาตั๋ว


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def evaluate_promo(
    db: Session,
    code: str,
    price: float,
    user: Optional[models.User] = None,
    flight: Optional[models.Flight] = None,
) -> PromoResult:
    """ตรวจโค้ดและคำนวณส่วนลด (ใช้ร่วมกันทั้งตอน validate และตอนออกตั๋วจริง)
    ถ้าไม่ผ่านเงื่อนไขใด ๆ จะ raise 400 พร้อมเหตุผล
    เงื่อนไขที่ต้องรู้ผู้ใช้/เที่ยวบิน จะตรวจเมื่อมีข้อมูลนั้นส่งเข้ามาเท่านั้น
    ส่วนตอนออกตั๋วจริงจะมีข้อมูลครบเสมอ"""
    code = normalize_code(code)

    promo = db.query(models.Promotion).filter(models.Promotion.code == code).first()
    if not promo:
        raise _bad_request("ไม่พบโค้ดส่วนลดนี้ หรือโค้ดไม่ถูกต้อง")

    rule = PROMO_RULES.get(code)
    if rule is None:
        raise _bad_request("โค้ดนี้ยังไม่เปิดให้ใช้งาน")

    if user is not None:
        used = (
            db.query(models.PromoRedemption)
            .filter(
                models.PromoRedemption.user_id == user.id,
                models.PromoRedemption.code == code,
            )
            .first()
        )
        if used:
            raise _bad_request("คุณใช้โค้ดนี้ไปแล้ว (โค้ดใช้ได้ครั้งเดียวต่อบัญชี)")

        if rule.new_users_only:
            has_booking = (
                db.query(models.Booking).filter(models.Booking.user_id == user.id).first()
            )
            if has_booking:
                raise _bad_request("โค้ดนี้สำหรับสมาชิกใหม่ที่ยังไม่เคยออกตั๋วเท่านั้น")

    if rule.east_asia_only and flight is not None:
        airports = {flight.origin.upper(), flight.destination.upper()}
        if not airports & EAST_ASIA_AIRPORTS:
            raise _bad_request("โค้ดนี้ใช้ได้กับเที่ยวบินโซนเอเชียตะวันออกเท่านั้น")

    discount = compute_discount(rule, price)
    return PromoResult(
        promo=promo,
        code=code,
        discount=discount,
        final_price=round(price - discount, 2),
    )