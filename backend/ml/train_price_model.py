"""สอนโมเดล AI ประเมินความเสี่ยงราคาตั๋ว แล้ว export เป็น backend/app/price_model.json

วิธีรัน (ที่โฟลเดอร์ backend):
    pip install -r ml/requirements-ml.txt
    python ml/train_price_model.py

โมเดลมี 2 ตัว:
1. payout  (regression)     : ถ้าตรึงราคาตอนนี้ ระยะ H ชั่วโมง เราต้องจ่ายส่วนต่างราคาเฉลี่ยกี่ % ของราคา
                              (คิดแบบระมัดระวัง: ลูกค้ามาออกตั๋วตอนราคาสูงสุดในช่วงนั้น และไม่เกินเพดาน 20%)
2. rise    (classification) : โอกาสที่ราคา ณ ตอนสิทธิ์หมดอายุ จะสูงกว่าตอนนี้ตั้งแต่ 3% ขึ้นไป

⚠️ ข้อมูลฝึกมาจากตัวจำลองราคา (app/pricing.py) ไม่ใช่ราคาตลาดจริง
โมเดลจึงพิสูจน์ว่าระบบทำงานครบวงจร แต่ยังไม่ได้พิสูจน์ความแม่นยำกับตลาดจริง
เมื่อมีข้อมูลราคาจริง ให้แทนที่ฟังก์ชัน build_dataset() แล้วรันสคริปต์นี้ใหม่
"""

import json
import random
import struct
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import pricing  # noqa: E402

FEATURES = ["days_to_departure", "horizon_days", "route_volatility", "is_peak", "price_ratio"]
HORIZONS_H = (24, 72, 168)
COVERAGE_CAP = 0.20
RISE_THRESHOLD = 0.03
BOOKING_CUTOFF_H = 3
SPLIT_DATE = datetime(2025, 7, 1)   # ฝึกด้วยเที่ยวบินก่อนวันนี้ ทดสอบกับเที่ยวบินหลังวันนี้
ROUTES = [("BKK", "CNX", 1800), ("BKK", "SIN", 6400), ("BKK", "HKG", 8500), ("BKK", "ICN", 12900), ("BKK", "HND", 18500)]


def build_dataset(seed: int = 7):
    rng = random.Random(seed)
    X, y_payout, y_rise, dep_dates = [], [], [], []
    start = datetime(2023, 1, 1)
    for day in range(365 * 3):
        for origin, dest, base in ROUTES:
            dep = start + timedelta(days=day, hours=rng.randint(0, 23))
            key = f"TRAIN-{origin}{dest}-{day}"
            for _ in range(12):
                at = dep - timedelta(hours=rng.uniform(26, 24 * 60))
                s0 = pricing.price_state(key, origin, dest, base, dep, at)
                p0 = s0["price"]
                for h in HORIZONS_H:
                    end = at + timedelta(hours=h)
                    if end > dep - timedelta(hours=BOOKING_CUTOFF_H):
                        continue
                    # ราคาเปลี่ยนวันละครั้ง: ตรวจทุกต้นวันในช่วงตรึง + ตอนหมดอายุ
                    opened = dep - timedelta(days=pricing.SALES_OPEN_DAYS)
                    checks, k = [end], pricing.day_index(dep, at) + 1
                    while (b := opened + timedelta(days=k)) < end:
                        checks.append(b)
                        k += 1
                    prices = [pricing.price_state(key, origin, dest, base, dep, c)["price"] for c in checks]
                    payout = min(max(0.0, max(prices) - p0) / p0, COVERAGE_CAP)
                    rise = pricing.price_state(key, origin, dest, base, dep, end)["price"] >= p0 * (1 + RISE_THRESHOLD)
                    X.append([s0["days_to_departure"], h / 24, s0["sigma"], float(s0["is_peak"]), s0["price_ratio"]])
                    y_payout.append(payout)
                    y_rise.append(int(rise))
                    dep_dates.append(dep)
    return np.array(X), np.array(y_payout), np.array(y_rise), np.array(dep_dates)


def export_gb(model, X_ref, classifier: bool) -> dict:
    """แปลง GradientBoosting เป็น JSON ที่คำนวณได้ด้วย Python ล้วน (ไม่ต้องติดตั้ง scikit-learn บนเซิร์ฟเวอร์)"""
    trees = []
    for est in model.estimators_[:, 0]:
        t = est.tree_
        trees.append({
            "l": t.children_left.tolist(), "r": t.children_right.tolist(), "f": t.feature.tolist(),
            "t": [float(v) for v in t.threshold], "v": [round(float(v), 6) for v in t.value[:, 0, 0]],
        })
    lr = float(model.learning_rate)
    raw = model.decision_function(X_ref[:1])[0] if classifier else model.predict(X_ref[:1])[0]
    tree_sum = sum(_tree_value(tr, X_ref[0]) for tr in trees)
    return {"learning_rate": lr, "init": float(raw - lr * tree_sum), "trees": trees, "output": "sigmoid" if classifier else "identity"}


def _f32(v):
    # scikit-learn แปลงข้อมูลนำเข้าเป็น float32 ก่อนเทียบกับจุดแบ่ง ต้องทำแบบเดียวกันผลถึงจะตรงกัน
    return struct.unpack("f", struct.pack("f", float(v)))[0]


def _tree_value(tree, x):
    x = [_f32(v) for v in x]
    n = 0
    while tree["l"][n] != -1:
        n = tree["l"][n] if x[tree["f"][n]] <= tree["t"][n] else tree["r"][n]
    return tree["v"][n]


def predict_json(m, x):
    raw = m["init"] + m["learning_rate"] * sum(_tree_value(t, x) for t in m["trees"])
    return 1 / (1 + np.exp(-raw)) if m["output"] == "sigmoid" else raw


def fee_rate_from_payout(payout_frac: float) -> float:
    # ต้องตรงกับ app/price_ai.py
    return min(0.15, max(0.03, payout_frac * 1.25 + 0.015))


def main():
    print("สร้างข้อมูลฝึกจากตัวจำลองราคา ...")
    X, yp, yr, deps = build_dataset()
    train, test = deps < SPLIT_DATE, deps >= SPLIT_DATE
    print(f"ตัวอย่างทั้งหมด {len(X):,} (ฝึก {train.sum():,} / ทดสอบ {test.sum():,})")

    params = dict(n_estimators=150, max_depth=4, learning_rate=0.08, subsample=0.8, random_state=0)
    reg = GradientBoostingRegressor(**params).fit(X[train], yp[train])
    clf = GradientBoostingClassifier(**params).fit(X[train], yr[train])

    # ---------- วัดผลกับข้อมูลทดสอบที่โมเดลไม่เคยเห็น เทียบกับวิธีเดาแบบง่าย ----------
    Xt, ypt, yrt = X[test], yp[test], yr[test]
    pred_p, prob_r = reg.predict(Xt), clf.predict_proba(Xt)[:, 1]
    mean_by_h = {h: yp[train][X[train][:, 1] == h / 24].mean() for h in HORIZONS_H}
    base_mean = np.array([mean_by_h[int(round(x[1] * 24))] for x in Xt])
    majority = int(yr[train].mean() >= 0.5)

    fees_ai = np.array([fee_rate_from_payout(p) for p in pred_p])
    fixed = {24: 0.05, 72: 0.07, 168: 0.10}
    fees_fixed = np.array([fixed[int(round(x[1] * 24))] for x in Xt])
    metrics = {
        "data_source": "simulated (app/pricing.py)",
        "train_samples": int(train.sum()), "test_samples": int(test.sum()),
        "test_period": f"เที่ยวบินตั้งแต่ {SPLIT_DATE.date()} เป็นต้นไป",
        "payout_mae_model": round(float(mean_absolute_error(ypt, pred_p)), 5),
        "payout_mae_baseline_zero": round(float(mean_absolute_error(ypt, np.zeros_like(ypt))), 5),
        "payout_mae_baseline_mean": round(float(mean_absolute_error(ypt, base_mean)), 5),
        "rise_auc_model": round(float(roc_auc_score(yrt, prob_r)), 4),
        "rise_accuracy_model": round(float(accuracy_score(yrt, prob_r >= 0.5)), 4),
        "rise_accuracy_baseline_majority": round(float((yrt == majority).mean()), 4),
        "rise_rate_test": round(float(yrt.mean()), 4),
        "fee_shortfall_rate_ai": round(float((ypt > fees_ai).mean()), 4),
        "fee_shortfall_rate_fixed": round(float((ypt > fees_fixed).mean()), 4),
        "avg_fee_ai": round(float(fees_ai.mean()), 4),
        "avg_fee_fixed": round(float(fees_fixed.mean()), 4),
        "avg_net_ai": round(float((fees_ai - ypt).mean()), 4),
        "avg_net_fixed": round(float((fees_fixed - ypt).mean()), 4),
    }

    model = {
        "version": datetime.now().strftime("%Y%m%d-%H%M"),
        "features": FEATURES, "horizons_h": list(HORIZONS_H),
        "coverage_cap": COVERAGE_CAP, "rise_threshold": RISE_THRESHOLD,
        "payout": export_gb(reg, Xt, classifier=False),
        "rise": export_gb(clf, Xt, classifier=True),
        "metrics": metrics,
    }

    # ตรวจว่าตัวคำนวณแบบ JSON ให้ผลเท่ากับ scikit-learn
    sample = Xt[:: max(1, len(Xt) // 2000)]
    d_p = max(abs(predict_json(model["payout"], x) - v) for x, v in zip(sample, reg.predict(sample)))
    d_r = max(abs(predict_json(model["rise"], x) - v) for x, v in zip(sample, clf.predict_proba(sample)[:, 1]))
    assert d_p < 1e-4 and d_r < 1e-4, f"ผลจาก JSON ไม่ตรงกับ scikit-learn ({d_p}, {d_r})"
    metrics["json_max_diff"] = float(max(d_p, d_r))

    out = ROOT / "app" / "price_model.json"
    out.write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"บันทึกโมเดล → {out} ({out.stat().st_size / 1024:.0f} KB)")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
