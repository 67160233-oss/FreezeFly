from pydantic import BaseModel, EmailStr

class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Schema สำหรับรับข้อมูลสมัครสมาชิก
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

# Schema สำหรับส่งข้อมูล User ออกไป (ไม่ส่ง password กลับไป)
class UserResponse(BaseModel):
    id: int
    username: str
    email: str

    class Config:
        from_attributes = True

# Schema สำหรับการสร้าง Project
class ProjectCreate(BaseModel):
    title: str
    description: str | None = None

# Schema สำหรับส่งข้อมูล Project ออกไป
class ProjectResponse(BaseModel):
    id: int
    title: str
    description: str | None
    owner_id: int

    class Config:
        from_attributes = True