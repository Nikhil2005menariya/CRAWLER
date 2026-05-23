from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
import bcrypt
import jwt
from datetime import datetime, timedelta
import os
import backend.db.mongodb as mongodb

router = APIRouter()

SECRET_KEY = os.environ.get("JWT_SECRET", "super-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "client"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/register", response_model=Token)
async def register(user: UserCreate):
    existing_user = await mongodb.db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    user_dict = {"email": user.email, "hashed_password": hashed_password, "role": user.role}
    
    result = await mongodb.db.users.insert_one(user_dict)
    
    # Create token
    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer", "user": {"email": user.email, "role": user.role, "id": str(result.inserted_id)}}

@router.post("/login", response_model=Token)
async def login(user: UserLogin):
    db_user = await mongodb.db.users.find_one({"email": user.email})
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email, "role": db_user["role"]})
    return {"access_token": access_token, "token_type": "bearer", "user": {"email": db_user["email"], "role": db_user["role"], "id": str(db_user["_id"])}}

from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    
    user = await mongodb.db.users.find_one({"email": email})
    if user is None:
        raise credentials_exception
    return user

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {"email": current_user["email"], "role": current_user["role"], "id": str(current_user["_id"])}
