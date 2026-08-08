## สมาชิก
67160233 รวีโรจน์ ศรีพหรม section 1
67160217 ธนกร แก้วศรีสด section 1

---

# FreezePrice Project

ระบบบริหารจัดการและจองบริการ FreezePrice พร้อมระบบลงทะเบียน เข้าสู่ระบบ และ API บริหารจัดการข้อมูล พัฒนาด้วย **FastAPI (Backend)** และ **HTML/Tailwind CSS (Frontend)**

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)

```text
FreezePriceProject/
├── .venv/                    # Python Virtual Environment
├── backend/                  # ส่วนบริการเซิร์ฟเวอร์ (FastAPI)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── database.py       # การตั้งค่าเชื่อมต่อฐานข้อมูล (SQLAlchemy)
│   │   ├── main.py           # API Endpoints หลักและการตั้งค่า CORS
│   │   ├── models.py         # Database Models (ตารางข้อมูล)
│   │   └── schemas.py        # Data Validation Models (Pydantic)
│   ├── Dockerfile            # คอนฟิกการสร้าง Docker Image ของ Backend
│   └── requirements.txt      # รายการ Library ของ Backend
├── frontend/                 # ส่วนแสดงผลเว็บไซต์ (UI)
│   ├── Dockerfile            # คอนฟิกการสร้าง Docker Image ของ Frontend
│   ├── index.html            # หน้าหลักของระบบ
│   ├── login.html            # หน้าเข้าสู่ระบบ (เชื่อมต่อ API /auth/login)
│   └── register.html         # หน้าลงทะเบียน (เชื่อมต่อ API /auth/register)
├── .dockerignore             # ยกเว้นไฟล์ที่ไม่ต้องการให้อยู่ใน Docker Image
├── .gitignore                # ยกเว้นไฟล์ที่ไม่ต้องการให้อัปโหลดขึ้น Git
├── docker-compose.yml        # คอนฟิกการรันระบบ Backend & Frontend พร้อมกัน
└── README.md                 # เอกสารอธิบายโปรเจกต์และคู่มือการใช้งาน


วิธีเปิดใช้งานระบบ (Getting Started)
เลือกสั่งรันระบบได้ 2 วิธี ตามรูปแบบการทำงานของคุณ:


วิธีที่ 1: รันผ่าน Docker Compose (แนะนำ)
เปิด Terminal ที่โฟลเดอร์หลักของโปรเจกต์ (FreezePriceProject)

สั่งเปิดการทำงานของระบบทั้งหมด:
    Bash
        docker compose up --build

เข้าใช้งานระบบ:
    Frontend UI: http://localhost
    Backend API Documentation: http://localhost:8000/docs


วิธีที่ 2: รันแบบ Local Development (ไม่ใช้ Docker)
    1. การตั้งค่าและสั่งรัน Backend (FastAPI)
    เปิด Terminal แล้วย้ายเข้าโฟลเดอร์ backend:
        Bash
            cd backend
        
    เปิดใช้งาน Virtual Environment:
        Bash
            # Windows (PowerShell / CMD)
            ..\.venv\Scripts\activate
            
    ติดตั้ง Library ที่จำเป็น:
        Bash
            pip install -r requirements.txt

    สั่งรัน Backend Server:
        Bash
            uvicorn app.main:app --reload --port 8000
        เข้าดู API Documentation ได้ที่: http://localhost:8000/docs

    2. การสั่งรัน Frontend
        เปิดไฟล์ frontend/index.html หรือ login.html ผ่าน Extension Live Server ใน VS Code
        หรือดับเบิลคลิกเปิดไฟล์ .html ผ่าน Web Browser โดยตรง

📌 หมายเหตุการตั้งค่าฐานข้อมูล (Database Setup Note)
PostgreSQL: ตรวจสอบว่าได้เปิด Service ของ PostgreSQL บนเครื่อง (Port 5432) หรือเปิด Container ฐานข้อมูลขึ้นมาก่อนรัน Backend

SQLite (ทางเลือกง่าย): หากต้องการรันระบบทดสอบโดยไม่ต้องเปิด PostgreSQL Server ให้เปิดไฟล์ backend/app/database.py แล้วเปลี่ยน URL เป็น SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"