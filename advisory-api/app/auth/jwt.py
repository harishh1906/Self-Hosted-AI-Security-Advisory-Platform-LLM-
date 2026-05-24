import os
import logging
from datetime import datetime, timedelta, timezone
from jose import jwt

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_THIS_IN_PROD")
if SECRET_KEY == "CHANGE_THIS_IN_PROD":
    logger.warning("JWT_SECRET_KEY not set — using insecure default. Set JWT_SECRET_KEY env var in production.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.JWTError:
        raise ValueError("Invalid token")

