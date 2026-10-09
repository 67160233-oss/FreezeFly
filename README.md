# ✈️ FreezeFly (FreezePriceProject)

**FreezeFly** คือเว็บแอปพลิเคชันระบบค้นหาเที่ยวบิน ตรึงราคาตั๋วเครื่องบินล่วงหน้า (Price Freeze) เพื่อป้องกันราคาปรับขึ้น และจัดการการออกตั๋วเครื่องบินพร้อมระบบโค้ดส่วนลด (Promotion Code)

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)

```text
FreezePriceProject/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── freeze_policy.py  # กฎตรึงราคา: ระยะเวลา เวลาปิดขาย เพดานความคุ้มครอง และการคิดเงินตอนออกตั๋ว
│   │   ├── pricing.py        # ตัวจำลองราคาตั๋ว (ราคาขยับทุกวัน) แทนราคาจริงจากสายการบิน
│   │   ├── price_ai.py       # ใช้โมเดล AI ประเมินความเสี่ยงราคา ตั้งค่าธรรมเนียม และแนะนำลูกค้า
│   │   ├── price_model.json  # โมเดล AI ที่สอนแล้ว (คำนวณด้วย Python ล้วน)
│   │   ├── database.py       # การเชื่อมต่อฐานข้อมูล SQLite (SQLAlchemy)
│   │   ├── main.py           # REST API Routes และ Business Logic หลัก
│   │   ├── models.py         # ORM Database Models
│   │   ├── promotions.py     # กฎและการตรวจโค้ดส่วนลด (แหล่งเดียว)
│   │   ├── schemas.py        # Pydantic Schemas สำหรับ Validation
│   │   ├── security.py       # bcrypt, JWT และ dependency ตรวจสิทธิ์
│   │   └── utils.py          # ฟังก์ชันช่วยเหลือทั่วไป
│   ├── data/
│   │   └── sql_app.db        # SQLite Database (สร้างอัตโนมัติ, ไม่ commit ขึ้น Git)
│   ├── .dockerignore
│   ├── ml/
│   │   ├── train_price_model.py  # สคริปต์สร้างข้อมูลและสอนโมเดล AI
│   │   ├── requirements-ml.txt   # ไลบรารีที่ใช้ตอนสอนเท่านั้น (scikit-learn)
│   │   └── MODEL_CARD.md         # โมเดลทำอะไรได้/ไม่ได้ และผลการทดสอบ
│   ├── Dockerfile            # Docker configuration สำหรับ Backend
│   └── requirements.txt      # Python Dependencies
├── frontend/
│   ├── .dockerignore
│   ├── auth-guard.js         # โค้ดกลาง: ตรวจล็อกอิน, แนบ JWT ทุกคำขอ (apiFetch), ป้องกัน XSS
│   ├── contact.html          # หน้าติดต่อเรา
│   ├── Dockerfile            # Docker configuration สำหรับ Frontend
│   ├── index.html            # หน้าแรก / ค้นหาเที่ยวบิน
│   ├── login.html            # หน้าเข้าสู่ระบบ
│   ├── my-trips.html         # หน้าทริปของฉัน / รายการตรึงราคา
│   ├── promotions.html       # หน้าโปรโมชัน
│   └── register.html         # หน้าสมัครสมาชิก
├── .env.example              # ตัวอย่างการตั้งค่า (คัดลอกเป็น .env)
├── .gitignore
├── docker-compose.yml        # Orchestration File สำหรับรันทั้งระบบ
└── README.md
```

---

## ✨ ฟีเจอร์หลัก (Features)

* **🔐 Authentication System:** สมัครสมาชิก เข้าสู่ระบบ (รหัสผ่านเข้ารหัสด้วย bcrypt, ยืนยันตัวตนด้วย JWT) และระบบตรวจสอบสิทธิ์ก่อนใช้งาน (Auth Guard)
* **✈️ Flight Search:** ค้นหาเที่ยวบินตามเมืองต้นทางและปลายทาง
* **❄️ Price Freeze System:** ตรึงราคาได้ 24 ชั่วโมง, 3 วัน หรือ 7 วัน ค่าธรรมเนียม 3–15% คิดตามความเสี่ยงที่ AI ประเมิน (ตั๋วต่ำกว่า ฿2,500 ตรึงไม่ได้)
* **🤖 AI ประเมินความเสี่ยงราคา:** ทายโอกาสที่ราคาจะขึ้น ใช้ตั้งค่าธรรมเนียมและแนะนำลูกค้าตรงๆ รวมถึงบอกว่า "ยังไม่จำเป็นต้องตรึง" เมื่อราคานิ่ง (ข้อมูลฝึกมาจากตัวจำลอง ดู `backend/ml/MODEL_CARD.md`)
* **🛡️ คุ้มครองราคา:** ราคาขึ้น เราจ่ายส่วนต่างให้สูงสุด 20% ของราคาที่ล็อก (เกินเพดาน ลูกค้าเลือกจ่ายส่วนเกินหรือยกเลิกรับเงินคืน) · ราคาลง ลูกค้าได้ราคาใหม่ · ค่าธรรมเนียมใช้จ่ายส่วนต่างก่อน ส่วนที่เหลือหักเป็นค่าตั๋ว ลูกค้าจึงไม่จ่ายแพงกว่าราคาตลาด
* **📈 ราคาตั๋วขยับทุกวัน (จำลอง):** ตามวันก่อนบิน ช่วงเทศกาล และความผันผวนของแต่ละเส้นทาง
* **💸 คืนค่าธรรมเนียมเมื่อที่นั่งเต็ม:** ถ้าที่นั่งเต็มก่อนลูกค้าออกตั๋ว (และสิทธิ์ยังไม่หมดอายุ) ระบบเปลี่ยนสถานะเป็น `refunded` และคืนค่าธรรมเนียมเต็มจำนวน เพราะลูกค้าไม่ได้ผิด
* **⏱️ กฎเวลาตามตารางบิน:** ปิดขายตั๋ว 3 ชั่วโมงก่อนเครื่องออก และสิทธิ์ตรึงราคาต้องหมดอายุก่อนปิดขายเสมอ (เที่ยวบินที่ใกล้เวลาออกจะเลือกได้แค่ระยะสั้น หรือซื้อตรงอย่างเดียว) กฎทั้งหมดอยู่ใน `backend/app/freeze_policy.py`
* **🎟️ Ticket Conversion & Booking:** ชำระส่วนที่เหลือเพื่อแปลงสิทธิ์ตรึงราคาเป็น E-Ticket หรือซื้อตั๋วโดยตรง (ค่าธรรมเนียมที่จ่ายไปแล้วนับเป็นส่วนหนึ่งของราคาตั๋ว)
* **🏷️ Promotion Code Validation:** ตรวจโค้ดส่วนลดพร้อมเงื่อนไข และคำนวณยอดสุทธิให้อัตโนมัติ

---

## 🛠️ เครื่องมือที่ใช้ (Tech Stack)

| ส่วนประกอบ | เทคโนโลยีที่ใช้ |
| --- | --- |
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, Uvicorn, bcrypt, PyJWT |
| **Frontend** | HTML5, Tailwind CSS (v4), Vanilla JavaScript (ES6) |
| **Database** | SQLite |
| **DevOps** | Docker, Docker Compose |

---

## ⚙️ การตั้งค่า (Configuration)

คัดลอก `.env.example` เป็น `.env` ที่ root โปรเจกต์ แล้วแก้ค่าตามต้องการ

| ตัวแปร | ความหมาย |
| --- | --- |
| `SECRET_KEY` | กุญแจเซ็น JWT สร้างด้วย `python -c "import secrets; print(secrets.token_urlsafe(48))"` ถ้าไม่ตั้งค่า ระบบสุ่มให้ชั่วคราวและผู้ใช้ต้องล็อกอินใหม่ทุกครั้งที่รีสตาร์ท |
| `ACCESS_TOKEN_EXPIRE_HOURS` | อายุ token เป็นชั่วโมง (ค่าเริ่มต้น 12) |
| `ALLOW_LEGACY_USER_ID` | `true` = ยังรับ `?user_id=` แบบเดิมโดยไม่ต้องมี token (**ไม่ปลอดภัย** ห้ามเปิดใช้งานจริง) ค่าเริ่มต้นคือ `false` |
| `CORS_ORIGINS` | Origin ของ frontend ที่อนุญาต คั่นด้วยจุลภาค |
| `DATABASE_URL` | (ไม่บังคับ) ใช้ฐานข้อมูลอื่นแทนไฟล์ SQLite เริ่มต้น |

> ⚠️ อย่า commit ไฟล์ `.env` และ `*.db` ขึ้น Git (ตั้งค่าไว้ใน `.gitignore` แล้ว)

---

## 🚀 วิธีการติดตั้งและเริ่มใช้งาน (Getting Started)

เลือกวิธีการรันระบบได้ 2 รูปแบบตามความสะดวก:

### วิธีที่ 1: รันด้วย Docker Compose (แนะนำ - ง่ายที่สุด)

ต้องติดตั้ง **Docker Desktop** ในเครื่องก่อนรัน (รวม Docker Compose มาให้แล้ว)

1. **เปิด Terminal / Command Prompt** ที่ root โฟลเดอร์ `FreezePriceProject`
2. **สั่งรันคอนเทนเนอร์:**

```bash
docker compose up --build
```

3. **เข้าใช้งานผ่าน Browser:**
   * **Frontend Application:** `http://localhost:8080`
   * **Backend API Docs (Swagger):** `http://localhost:8000/docs`

ฐานข้อมูลถูกเก็บไว้ที่ `backend/data/sql_app.db` จึงไม่หายเมื่อลบคอนเทนเนอร์

---

### วิธีที่ 2: รันแบบ Manual (Local Development)

#### 1. Setup Backend (FastAPI)

1. เปิด Terminal เข้าไปที่โฟลเดอร์ backend:

```bash
cd backend
```

2. สร้างและเปิดใช้งาน Virtual Environment:

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

3. ติดตั้ง Package ที่จำเป็น:

```bash
pip install -r requirements.txt
```

4. สั่งเริ่มทำงาน Backend Server:

```bash
uvicorn app.main:app --reload --port 8000
```

   * Backend API จะรันที่: `http://localhost:8000`
   * API Document (Swagger UI): `http://localhost:8000/docs`

#### 2. Setup Frontend

1. เปิด Terminal อีกหน้าต่าง แล้วเข้าไปที่โฟลเดอร์ frontend:

```bash
cd frontend
```

2. เปิดไฟล์ HTML ผ่าน Live Server ใน VS Code หรือเปิดไฟล์ `index.html` บน Browser ได้ทันที

---

## 🔑 การยืนยันตัวตน (Authentication)

1. เรียก `POST /auth/login` จะได้ `access_token` (JWT)
2. ทุก endpoint ที่ต้องล็อกอินให้แนบ header `Authorization: Bearer <access_token>`
3. ผู้ใช้เข้าถึงได้เฉพาะข้อมูลของตัวเอง (`/freeze/user/{id}`, `/bookings/user/{id}`, `/freeze/convert/{id}`) ถ้าเข้าข้อมูลคนอื่นจะได้ `403`

---

## 🎟️ โค้ดส่วนลดสำหรับทดสอบ (Mock Promotion Codes)

ทุกโค้ด **ใช้ได้ครั้งเดียวต่อบัญชี** และใช้ตอนออกตั๋ว

| โค้ดส่วนลด | รายละเอียด | เงื่อนไข |
| --- | --- | --- |
| `NEWUSER2026` | ส่วนลดค่าตั๋ว ฿100 | เฉพาะบัญชีที่ยังไม่เคยออกตั๋ว |
| `HALFPRICE50` | ส่วนลด 50% ของราคาตั๋ว | ไม่มี |
| `ASIAFLY300` | ส่วนลดค่าตั๋ว ฿300 | เที่ยวบินที่ต้นทางหรือปลายทางอยู่โซนเอเชียตะวันออก (เช่น HKG, HND, ICN) |

ส่วนลดจะไม่เกินราคาตั๋ว และถ้าโค้ดไม่ผ่านเงื่อนไข ระบบจะแจ้งเหตุผลกลับมา (ไม่ข้ามโค้ดเงียบ ๆ)

---

## 📌 API Endpoints ที่สำคัญ

| Method | Path | ต้องล็อกอิน | รายละเอียด |
| --- | --- | :---: | --- |
| POST | `/auth/register` | ไม่ | สมัครสมาชิกใหม่ |
| POST | `/auth/login` | ไม่ | เข้าสู่ระบบ ได้ JWT |
| GET | `/flights` | ✅ | ค้นหาเที่ยวบิน (`?origin=...&destination=...`) |
| GET | `/flights/{flight_id}` | ✅ | ดูเที่ยวบินรายตัว |
| POST | `/freeze/create` | ✅ | ตรึงราคา (`{"flight_id": 1, "hours": 24, 72 หรือ 168}`) |
| GET | `/freeze/user/{user_id}` | ✅ | รายการตรึงราคาของตัวเอง |
| GET | `/freeze/{freeze_id}/quote` | ✅ | ใบเสนอราคาก่อนออกตั๋ว: ราคาตลาด ส่วนต่างที่คุ้มครอง ยอดที่ต้องจ่าย |
| POST | `/freeze/{freeze_id}/cancel` | ✅ | ยกเลิกพร้อมรับค่าธรรมเนียมคืน (เฉพาะเมื่อราคาเกินเพดานความคุ้มครอง) |
| GET | `/ai/model-info` | ไม่ | รุ่นของโมเดล AI และผลการทดสอบ |
| POST | `/freeze/convert/{freeze_id}` | ✅ | แปลงสิทธิ์ตรึงราคาเป็น E-Ticket (ส่ง `promo_code` ได้) |
| POST | `/bookings/create` | ✅ | ซื้อตั๋วโดยตรง หรือใช้ `freeze_id` (ส่ง `promo_code` ได้) |
| GET | `/bookings/user/{user_id}` | ✅ | รายการตั๋วของตัวเอง |
| GET | `/promotions` | ไม่ | รายการโปรโมชัน |
| POST | `/promotions/validate` | ไม่ | ตรวจโค้ด (ส่ง `flight_id` และ token เพิ่มเพื่อให้ตรวจเงื่อนไขได้ครบ) |
| POST | `/contact` | ไม่ | ส่งข้อความติดต่อ |

**ข้อมูลใน Booking:** `total_price` = ราคาตั๋วทั้งใบหลังหักส่วนลด, `freeze_fee_paid` = ค่าธรรมเนียมตรึงราคาที่จ่ายไปแล้ว, `amount_due` = ยอดที่ต้องชำระเพิ่ม (`total_price - freeze_fee_paid`)