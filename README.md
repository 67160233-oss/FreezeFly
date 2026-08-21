
---

# ✈️ FreezeFly (FreezePriceProject)

**FreezeFly** คือเว็บแอปพลิเคชันระบบค้นหาเที่ยวบิน ตรึงราคาตั๋วเครื่องบินล่วงหน้า (Price Freeze) เพื่อป้องกันราคาปรับขึ้น และจัดการการออกตั๋วเครื่องบินพร้อมระบบโค้ดส่วนลด (Promotion Code)

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)

```text
FreezePriceProject/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── database.py       # การเชื่อมต่อฐานข้อมูล SQLite (SQLAlchemy)
│   │   ├── main.py           # REST API Routes และ Business Logic หลัก
│   │   ├── models.py         # ORM Database Models
│   │   └── schemas.py        # Pydantic Schemas สำหรับ Validation
│   ├── Dockerfile            # Docker configuration สำหรับ Backend
│   ├── requirements.txt      # Python Dependencies
│   └── sql_app.db            # SQLite Database File
├── frontend/
│   ├── auth-guard.js         # ระบบตรวจสอบการเข้าสู่ระบบ
│   ├── contact.html          # หน้าติดต่อเรา
│   ├── Dockerfile            # Docker configuration สำหรับ Frontend
│   ├── index.html            # หน้าแรก / ค้นหาเที่ยวบิน
│   ├── login.html            # หน้าเข้าสู่ระบบ
│   ├── my-trips.html         # หน้าทริปของฉัน / รายการตรึงราคา
│   ├── promotions.html       # หน้าโปรโมชัน
│   └── register.html         # หน้าสมัครสมาชิก
├── .dockerignore
├── .gitignore
├── docker-compose.yml        # Orchestration File สำหรับรันทั้งระบบ
└── README.md

```

---

## ✨ ฟีเจอร์หลัก (Features)

* **🔐 Authentication System:** สมัครสมาชิก เข้าสู่ระบบ และระบบตรวจสอบสิทธิ์ก่อนใช้งาน (Auth Guard)
* **✈️ Flight Search:** ค้นหาเที่ยวบินแบบ Real-time ตามเมืองต้นทางและปลายทาง
* **❄️ Price Freeze System:** ตรึงราคาเที่ยวบินล็อกราคานาน 24 ชั่วโมง ชำระค่าธรรมเนียมเริ่มต้นเพียง 5%
* **🎟️ Ticket Conversion & Booking:** ชำระเงินส่วนที่เหลือเพื่อแปลงสิทธิ์ตรึงราคาเป็น E-Ticket หรือซื้อตั๋วโดยตรง
* **🏷️ Promotion Code Validation:** ระบบตรวจสอบโค้ดส่วนลดก่อนชำระเงิน พร้อมคำนวณยอดสุทธิให้อัตโนมัติ

---

## 🛠️ เครื่องมือที่ใช้ (Tech Stack)

| ส่วนประกอบ | เทคโนโลยีที่ใช้ |
| --- | --- |
| **Backend** | Python 3.10+, FastAPI, SQLAlchemy, Pydantic, Uvicorn |
| **Frontend** | HTML5, Tailwind CSS (v4), Vanilla JavaScript (ES6) |
| **Database** | SQLite |
| **DevOps** | Docker, Docker Compose |

---

## 🚀 วิธีการติดตั้งและเริ่มใช้งาน (Getting Started)

เลือกวิธีการรันระบบได้ 2 รูปแบบตามความสะดวก:

### วิธีที่ 1: รันด้วย Docker Compose (แนะนำ - ง่ายที่สุด)

ต้องติดตั้ง **Docker** และ **Docker Desktop** ในเครื่องก่อนรัน

1. **เปิด Terminal / Command Prompt** ที่ root โฟลเดอร์ `FreezePriceProject`
2. **สั่งรันคอนเทนเนอร์:**
```bash
docker-compose up --build

```


3. **เข้าใช้งานผ่าน Browser:**
* **Frontend Application:** `http://localhost:8080` (หรือ Port ที่ตั้งค่าไว้ใน Docker)
* **Backend API Docs (Swagger):** `http://localhost:8000/docs`



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

## 🎟️ โค้ดส่วนลดสำหรับทดสอบ (Mock Promotion Codes)

สามารถนำโค้ดด้านล่างไปทดสอบกรอกในหน้าออกตั๋วได้ทันที:

| โค้ดส่วนลด | รายละเอียด |
| --- | --- |
| `NEWUSER2026` | ส่วนลดค่าตั๋ว ฿100 สำหรับสมาชิกใหม่ |
| `HALFPRICE50` | ส่วนลด 50% สำหรับการออกตั๋ว |
| `ASIAFLY300` | ส่วนลด ฿300 สำหรับเที่ยวบินโซนเอเชีย |

---

## 📌 API Endpoints ที่สำคัญ

* `POST /auth/register` - สมัครสมาชิกใหม่
* `POST /auth/login` - เข้าสู่ระบบ
* `GET /flights` - ค้นหาและดึงรายการเที่ยวบิน (`?origin=...&destination=...`)
* `POST /freeze/create` - ตรึงราคาเที่ยวบิน
* `GET /freeze/user/{user_id}` - ดึงรายการตรึงราคาของผู้ใช้
* `POST /promotions/validate` - ตรวจสอบความถูกต้องของโค้ดส่วนลด
* `POST /freeze/convert/{freeze_id}` - แปลงรายการตรึงราคาเป็น E-Ticket