"""ทดสอบกติกาคุ้มครองราคาของ FreezeFly (freeze_policy.conversion_quote)

คำสัญญาที่ทดสอบ:
  1. ลูกค้าที่ออกตั๋วจากสิทธิ์ตรึงราคา จ่ายรวม (ค่าธรรมเนียม + ยอดตอนออกตั๋ว) ไม่เกินราคาตลาด
  2. บริษัทขาดทุนจากการคุ้มครองราคาไม่เกินเพดาน 20% ของราคาที่ล็อก
  3. ราคาลง ลูกค้าได้ราคาใหม่

วิธีรัน (ที่โฟลเดอร์ backend ไม่ต้องติดตั้งอะไรเพิ่ม):
    python -m unittest discover tests -v
หรือ
    python tests/test_price_protection.py

ใช้ seed คงที่ ทุกคนที่รันจะได้ 50,000 สถานการณ์ชุดเดียวกันและผลเหมือนกัน
"""

import random
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import price_ai, pricing  # noqa: E402
from app.freeze_policy import COVERAGE_CAP_RATE, conversion_quote, freeze_options_for  # noqa: E402

N_CASES = 50_000
SEED = 1
TOL = 0.01  # ยอมคลาดเคลื่อนจากการปัดเศษได้ไม่เกิน 1 สตางค์


class TestPriceProtectionRandomized(unittest.TestCase):
    """สุ่มสถานการณ์ราคา 50,000 แบบ แล้วตรวจคำสัญญาทุกกรณี"""

    @classmethod
    def setUpClass(cls):
        rng = random.Random(SEED)
        cls.cases = []
        for _ in range(N_CASES):
            frozen = rng.uniform(2_500, 30_000)            # ราคาที่ล็อกไว้
            market = frozen * rng.uniform(0.6, 1.6)        # ราคาตลาดตอนออกตั๋ว: ลง 40% ถึงขึ้น 60%
            fee = frozen * rng.uniform(0.03, 0.15)         # ค่าธรรมเนียม 3–15% (ช่วงที่ AI ตั้งได้)
            cls.cases.append((frozen, market, fee, conversion_quote(frozen, market, fee)))

    def test_case_count(self):
        self.assertEqual(len(self.cases), N_CASES)

    def test_customer_never_pays_more_than_market(self):
        bad = [c for c in self.cases if c[3]["customer_total"] > c[3]["market_price"] + TOL]
        self.assertEqual(bad, [], f"ลูกค้าจ่ายเกินราคาตลาด {len(bad)} กรณี")

    def test_company_loss_never_exceeds_cap(self):
        # เทียบกับ 20% ของราคาที่ล็อกโดยตรง ไม่ใช้ cap_amount ที่ฟังก์ชันคืนมา (ถ้าฟังก์ชันคิดเพดานผิด จะได้จับได้)
        bad = [c for c in self.cases if c[3]["company_net"] < -COVERAGE_CAP_RATE * c[0] - TOL]
        self.assertEqual(bad, [], f"บริษัทขาดทุนเกินเพดาน {len(bad)} กรณี")

    def test_price_drop_gives_new_price(self):
        drops = [c for c in self.cases if c[1] < c[0]]
        self.assertGreater(len(drops), 0)
        for frozen, market, fee, q in drops:
            self.assertAlmostEqual(q["customer_total"], round(market, 2), delta=TOL)

    def test_customer_pays_at_most_locked_price_plus_fee_within_cap(self):
        for frozen, market, fee, q in self.cases:
            if not q["exceeds_cap"]:
                self.assertLessEqual(q["customer_total"], frozen + fee + TOL)

    def test_money_adds_up(self):
        """ลูกค้าจ่าย - บริษัทได้/เสีย = ราคาตลาดที่ต้องส่งให้สายการบินเสมอ"""
        for frozen, market, fee, q in self.cases:
            self.assertAlmostEqual(q["customer_total"] - q["company_net"], q["market_price"], delta=0.05)
            self.assertGreaterEqual(q["amount_due"], 0)
            self.assertLessEqual(q["fee_credit"], q["fee_paid"] + TOL)

    def test_guarantee_precondition(self):
        """การันตีข้อ 1 กรณีราคาเกินเพดานใช้ได้ เพราะค่าธรรมเนียมสูงสุด (15%) ต่ำกว่าเพดาน (20%)"""
        self.assertLess(price_ai.FEE_MAX, COVERAGE_CAP_RATE)


class TestPriceProtectionExamples(unittest.TestCase):
    """ตัวอย่างในสไลด์: ล็อก ฿10,000 ค่าธรรมเนียม ฿700 เพดาน ฿2,000"""

    def check(self, market, total, company):
        q = conversion_quote(10_000, market, 700)
        self.assertAlmostEqual(q["customer_total"], total, places=2)
        self.assertAlmostEqual(q["company_net"], company, places=2)
        return q

    def test_unchanged(self):
        self.check(10_000, 10_000, 0)

    def test_price_down(self):
        self.check(9_000, 9_000, 0)

    def test_small_rise_absorbed_by_fee(self):
        q = self.check(10_300, 10_300, 0)
        self.assertEqual(q["amount_due"], 9_600)

    def test_rise_above_fee(self):
        self.check(11_500, 10_700, -800)

    def test_rise_above_cap(self):
        q = self.check(13_000, 11_700, -1_300)
        self.assertTrue(q["exceeds_cap"])
        self.assertEqual(q["covered"], 2_000)
        self.assertEqual(q["excess"], 1_000)

    def test_exactly_at_cap(self):
        q = self.check(12_000, 10_700, -1_300)
        self.assertFalse(q["exceeds_cap"])


class TestEndToEndWithSimulatorAndAI(unittest.TestCase):
    """ใช้ตัวจำลองราคาและค่าธรรมเนียมจาก AI ของระบบจริง: ตรึงราคา รอ แล้วออกตั๋ว"""

    def test_simulated_freezes(self):
        rng = random.Random(SEED)
        routes = [("BKK", "SIN", 6400), ("BKK", "HKG", 8500), ("BKK", "ICN", 12900), ("BKK", "HND", 18500)]
        checked = 0
        for i in range(2_000):
            origin, dest, base = rng.choice(routes)
            now = datetime(2026, 1, 1) + timedelta(days=rng.uniform(0, 330))
            flight = types.SimpleNamespace(flight_number=f"TEST{i}", origin=origin, destination=dest, price=base,
                                           departure_time=now + timedelta(days=rng.uniform(5, 60)))
            options = [o for o in freeze_options_for(flight, now) if o["available"]]
            if not options:
                continue
            opt = rng.choice(options)
            self.assertLessEqual(opt["expires_at"], flight.departure_time - timedelta(hours=3))  # หมดก่อนปิดขายเสมอ
            frozen = pricing.current_price(flight, now)
            later = now + timedelta(hours=opt["hours"] * rng.uniform(0.1, 0.99))
            q = conversion_quote(frozen, pricing.current_price(flight, later), opt["fee_amount"])
            self.assertLessEqual(q["customer_total"], q["market_price"] + TOL)
            self.assertGreaterEqual(q["company_net"], -COVERAGE_CAP_RATE * frozen - TOL)
            checked += 1
        self.assertGreater(checked, 1_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)