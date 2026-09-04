import os
import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from report.db import get_db

# Constants
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

router = APIRouter()

# Models
class UserCreate(BaseModel):
    email: str
    password: str
    merchant_name: str

class Token(BaseModel):
    access_token: str
    token_type: str
    merchant_id: str

# Helpers
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: datetime.timedelta = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (expires_delta if expires_delta else datetime.timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        merchant_id: str = payload.get("merchant_id")
        if user_id is None or merchant_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    
    if user is None:
        raise credentials_exception
    return {"id": user["id"], "merchant_id": user["merchant_id"], "role": user["role"]}

# Endpoints
@router.post("/api/signup", response_model=Token)
def signup(user: UserCreate):
    conn = get_db()
    existing_user = conn.execute("SELECT id FROM users WHERE email = ?", (user.email,)).fetchone()
    if existing_user:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
        
    merchant_id = f"m_{uuid.uuid4().hex[:12]}"
    user_id = f"u_{uuid.uuid4().hex[:12]}"
    
    hashed_pwd = get_password_hash(user.password)
    
    with conn:
        conn.execute("INSERT INTO merchants (id, name) VALUES (?, ?)", (merchant_id, user.merchant_name))
        conn.execute(
            "INSERT INTO users (id, merchant_id, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
            (user_id, merchant_id, user.email, hashed_pwd, "admin")
        )
    conn.close()
    
    access_token = create_access_token(
        data={"sub": user_id, "merchant_id": merchant_id, "role": "admin"},
        expires_delta=datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer", "merchant_id": merchant_id}


@router.post("/api/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (form_data.username,)).fetchone()
    conn.close()
    
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(
        data={"sub": user["id"], "merchant_id": user["merchant_id"], "role": user["role"]},
        expires_delta=datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer", "merchant_id": user["merchant_id"]}
