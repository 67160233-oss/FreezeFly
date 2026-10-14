"""จำลองเศรษฐศาสตร์ต่อการตรึงราคา 1 ครั้ง (ตัวเลขในสไลด์ 9 ของ pitch deck)

วิธีรัน (ที่โฟลเดอร์ backend ไม่ต้องติดตั้งอะไรเพิ่ม):
    python ml/simulate_unit_economics.py

ขั้นตอน:
1. สุ่มการตรึงราคา 6,000 ครั้ง ด้วยตัวจำลองราคา (app/pricing.py) และค่าธรรมเนียมจาก AI (app/price_ai.py)
   - เส้นทางที่ตั๋วเกิน ฿2,500: BKK→SIN, HKG, ICN, HND
   - ตรึงล่วงหน้า 5–60 วันก่อนบิน เลือกระยะ 24 ชม./3 วัน/7 วัน แบบสุ่มจากที่ระบบเปิดให้เลือก
   - ลูกค้ากลับมาออกตั๋วตอน 30–99% ของระยะที่ตรึง
2. คิดเงินตอนออกตั๋วด้วยกติกาคุ้มครองราคาจริง (freeze_policy.conversion_quote)
3. สมมติกรณีแย่ที่สุด: คนที่ราคาขึ้นมากที่สุดคือคนที่มาออกตั๋วก่อน (ใช้สิทธิ์เฉพาะตอนได้ประโยชน์)
4. แปลงทุกครั้งเป็น "บาทต่อการตรึง 1 ครั้ง ถ้าตั๋วราคา ฿10,000" เพื่อเทียบกันได้

ข้อจำกัด: ราคามาจากตัวจำลอง ไม่ใช่ราคาตลาดจริง และยังไม่รวมค่าคอมมิชชันกับต้นทุนดำเนินงาน
ใช้ seed คงที่ ทุกคนที่รันจะได้ตัวเลขชุดเดียวกัน
"""

import random
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import pricing  # noqa: E402
from app.freeze_policy import conversion_quote, freeze_options_for  # noqa: E402

N_FREEZES = 6_000
SEED = 11
TICKET = 10_000
CONVERSION_RATES = (50, 65, 80, 90, 95)
ROUTES = [("BKK", "SIN", 6400), ("BKK", "HKG", 8500), ("BKK", "ICN", 12900), ("BKK", "HND", 18500)]


def simulate():
    rng = random.Random(SEED)
    rows = []
    for i in range(N_FREEZES):
        origin, dest, base = rng.choice(ROUTES)
        now = datetime(2026, 1, 1) + timedelta(days=rng.uniform(0, 330))
        flight = types.SimpleNamespace(flight_number=f"U{i}", origin=origin, destination=dest, price=base,
                                       departure_time=now + timedelta(days=rng.uniform(5, 60)))
        options = [o for o in freeze_options_for(flight, now) if o["available"]]
        if not options:
            continue
        opt = rng.choice(options)
        frozen = pricing.current_price(flight, now)
        later = now + timedelta(hours=opt["hours"] * rng.uniform(0.3, 0.99))
        q = conversion_quote(frozen, pricing.current_price(flight, later), opt["fee_amount"])
        rows.append({
            "price": frozen,
            "fee": opt["fee_amount"],
            "covered": q["covered"],                              # ส่วนต่างที่เราจ่ายแทนลูกค้า
            "loss": max(0.0, q["covered"] - opt["fee_amount"]),   # ส่วนที่เกินค่าธรรมเนียม = ขาดทุนจริง
        })
    return rows


def scenario(rows, conv_pct):
    n = len(rows)
    worst_first = sorted(rows, key=lambda r: -r["covered"] / r["price"])  # คนที่ราคาขึ้นมากสุดมาออกตั๋วก่อน
    k = round(n * conv_pct / 100)
    converters, expired = worst_first[:k], worst_first[k:]
    kept = sum(r["fee"] / r["price"] for r in expired) / n * TICKET   # ค่าธรรมเนียมจากสิทธิ์ที่หมดอายุ
    loss = sum(r["loss"] / r["price"] for r in converters) / n * TICKET
    return round(kept), round(loss)


def main():
    rows = simulate()
    n = len(rows)
    avg_fee = sum(r["fee"] / r["price"] for r in rows) / n * 100
    rise = sum(r["covered"] > 0 for r in rows) / n * 100
    print(f"จำลองการตรึง {n:,} ครั้ง · ค่าธรรมเนียมเฉลี่ย {avg_fee:.1f}% · ราคาขึ้นระหว่างตรึง {rise:.1f}% ของกรณี\n")
    print(f"{'บาท / การตรึง (ตั๋ว ฿10,000)':32}" + "".join(f"{'ออก ' + str(c) + '%':>10}" for c in CONVERSION_RATES))
    results = {c: scenario(rows, c) for c in CONVERSION_RATES}
    print(f"{'ค่าธรรมเนียมที่เก็บได้':32}" + "".join(f"{results[c][0]:>10,}" for c in CONVERSION_RATES))
    print(f"{'ขาดทุนคุ้มครองราคา':32}" + "".join(f"{'(' + str(results[c][1]) + ')':>10}" for c in CONVERSION_RATES))
    print(f"{'กำไรสุทธิ':32}" + "".join(f"{results[c][0] - results[c][1]:>10,}" for c in CONVERSION_RATES))
    print(f"{'% ของราคาตั๋ว':32}" + "".join(f"{(results[c][0] - results[c][1]) / 100:>9.1f}%" for c in CONVERSION_RATES))

    breakeven = next((c for c in range(50, 101) if scenario(rows, c)[0] - scenario(rows, c)[1] <= 0), 100)
    print(f"\nจุดคุ้มทุน: กำไรเหลือ 0 เมื่ออัตราออกตั๋วถึง {breakeven}%")


if __name__ == "__main__":
    main()
