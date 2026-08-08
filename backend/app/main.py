from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models, schemas
from .database import engine, get_db

# สั่งสร้างตารางในฐานข้อมูลอัตโนมัติหากยังไม่มี
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FreezeFly Project Management API")

# ตั้งค่า CORS อนุญาตให้ Frontend ทุกโดเมน/พอร์ต เชื่อมต่อเข้ามาได้ช่วงพัฒนา
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Project Management API Service is Running"}

# --- 1. Authentication & User Endpoints ---

@app.post("/auth/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username หรือชื่อผู้ใช้งานนี้มีในระบบแล้ว")
    
    existing_email = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="อีเมลนี้ถูกใช้งานไปแล้ว")
    
    new_user = models.User(
        username=user.username,
        email=user.email,
        password=user.password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/auth/login")
def login_user(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    
    if not user or user.password != credentials.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง"
        )
    
    return {
        "message": "เข้าสู่ระบบสำเร็จ",
        "access_token": f"fake-jwt-token-for-{user.id}",
        "token_type": "bearer",
        "username": user.username,
        "email": user.email
    }

@app.get("/users/check-username/{name}")
def check_username(name: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == name).first()
    return {"is_available": user is None}

# --- 2. Project Management Endpoints ---

@app.post("/projects", response_model=schemas.ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(project: schemas.ProjectCreate, user_id: int, db: Session = Depends(get_db)):
    new_project = models.Project(
        title=project.title,
        description=project.description,
        owner_id=user_id
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project

@app.get("/projects", response_model=list[schemas.ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    return db.query(models.Project).all()