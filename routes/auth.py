from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta, timezone
import jwt
import bcrypt
import os
import httpx
import uuid
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.user import UserCreate, UserLogin, User, UserResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

SECRET_KEY = os.environ.get("JWT_SECRET", "psychic-marketplace-secret-key-2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

# Emergent OAuth session endpoint
EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

# Apple Sign-In constants
APPLE_AUTH_URL = "https://appleid.apple.com"
APPLE_PUBLIC_KEYS_URL = f"{APPLE_AUTH_URL}/auth/keys"
APPLE_BUNDLE_ID = os.environ.get("APPLE_BUNDLE_ID", "com.sixthsense.psychics")

def get_zodiac_sign(birth_date: str) -> str:
    """Calculate zodiac sign from birth date (MM-DD or YYYY-MM-DD)"""
    try:
        if len(birth_date) == 10:  # YYYY-MM-DD
            month = int(birth_date[5:7])
            day = int(birth_date[8:10])
        else:
            return "Unknown"
        
        zodiac_dates = [
            (1, 20, "Capricorn"), (2, 19, "Aquarius"), (3, 20, "Pisces"),
            (4, 20, "Aries"), (5, 21, "Taurus"), (6, 21, "Gemini"),
            (7, 22, "Cancer"), (8, 23, "Leo"), (9, 23, "Virgo"),
            (10, 23, "Libra"), (11, 22, "Scorpio"), (12, 22, "Sagittarius")
        ]
        
        for i, (m, d, sign) in enumerate(zodiac_dates):
            if month == m and day <= d:
                return zodiac_dates[i-1][2] if i > 0 else "Capricorn"
            elif month == m:
                return sign
        return "Sagittarius"
    except:
        return "Unknown"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

async def get_current_user(token: str, db: AsyncIOMotorDatabase) -> User:
    payload = verify_token(token)
    user = await db.users.find_one({"id": payload.get("user_id")})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return User(**user)

def create_auth_routes(db: AsyncIOMotorDatabase):
    @router.post("/register", response_model=TokenResponse)
    async def register(user_data: UserCreate):
        # Check if email exists
        existing = await db.users.find_one({"email": user_data.email})
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create user
        zodiac = get_zodiac_sign(user_data.birth_date) if user_data.birth_date else None
        user = User(
            email=user_data.email,
            name=user_data.name,
            birth_date=user_data.birth_date,
            zodiac_sign=zodiac,
            is_new_user=True,  # First reading gets 4 free minutes
            first_reading_free_used=False
        )
        
        # Store with hashed password
        user_dict = user.dict()
        user_dict["password_hash"] = hash_password(user_data.password)
        await db.users.insert_one(user_dict)
        
        # Create token
        token = create_access_token({"user_id": user.id, "email": user.email})
        
        return TokenResponse(
            access_token=token,
            user=UserResponse(**user.dict())
        )
    
    @router.post("/login", response_model=TokenResponse)
    async def login(credentials: UserLogin):
        user_doc = await db.users.find_one({"email": credentials.email})
        if not user_doc:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        if not verify_password(credentials.password, user_doc.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        user = User(**user_doc)
        token = create_access_token({"user_id": user.id, "email": user.email})
        
        return TokenResponse(
            access_token=token,
            user=UserResponse(**user.dict())
        )
    
    @router.get("/me", response_model=UserResponse)
    async def get_me(token: str):
        user = await get_current_user(token, db)
        return UserResponse(**user.dict())
    
    @router.post("/psychic/login")
    async def psychic_login(credentials: UserLogin):
        """Login endpoint for Psychic Advisor app"""
        # Mock psychic data for demo
        MOCK_PSYCHICS = {
            "advisor@psychic.com": {
                "id": "psychic-001",
                "email": "advisor@psychic.com",
                "password": "advisor123",
                "name": "Luna Mystic",
                "profile_picture": None,
                "specialties": ["Love & Relationships", "Tarot", "Dream Analysis"],
                "years_experience": 8,
                "chat_rate": 3.99,
                "phone_rate": 4.99,
                "video_rate": 5.99,
                "online_status": "online",
                "total_earnings": 12450.00,
                "average_rating": 4.92,
                "total_reviews": 342,
                "total_readings": 1205,
                "status": "approved"
            },
            "mystic@advisor.com": {
                "id": "psychic-002",
                "email": "mystic@advisor.com",
                "password": "mystic123",
                "name": "Rose Starlight",
                "profile_picture": None,
                "specialties": ["Astrology", "Career", "Spiritual Guidance"],
                "years_experience": 12,
                "chat_rate": 5.99,
                "phone_rate": 6.99,
                "video_rate": 7.99,
                "online_status": "online",
                "total_earnings": 28900.00,
                "average_rating": 4.95,
                "total_reviews": 567,
                "total_readings": 2340,
                "status": "approved"
            }
        }
        
        psychic = MOCK_PSYCHICS.get(credentials.email)
        if not psychic:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        if credentials.password != psychic["password"]:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Return psychic data (without password)
        psychic_data = {k: v for k, v in psychic.items() if k != "password"}
        
        return {
            "success": True,
            "psychic": psychic_data
        }
    
    @router.put("/psychic/profile")
    async def update_psychic_profile(profile_data: dict):
        """Update psychic profile - name, bio, profile picture"""
        psychic_id = profile_data.get("psychic_id")
        
        if not psychic_id:
            raise HTTPException(status_code=400, detail="Psychic ID required")
        
        update_data = {}
        if "name" in profile_data:
            update_data["name"] = profile_data["name"]
        if "bio" in profile_data:
            update_data["bio"] = profile_data["bio"]
        if "profile_picture" in profile_data:
            update_data["profile_picture"] = profile_data["profile_picture"]
        
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            
            # Update in psychics collection
            result = await db.psychics.update_one(
                {"id": psychic_id},
                {"$set": update_data}
            )
            
            # Also update the profile picture in the linked client app user if it exists
            # This syncs the profile picture across both apps
            if "profile_picture" in update_data:
                psychic = await db.psychics.find_one({"id": psychic_id})
                if psychic and psychic.get("email"):
                    await db.users.update_one(
                        {"email": psychic["email"]},
                        {"$set": {"profile_picture": update_data["profile_picture"]}}
                    )
        
        return {"success": True, "message": "Profile updated successfully"}
    
    @router.put("/user/profile")
    async def update_user_profile(profile_data: dict):
        """Update user profile - name, email, phone, profile picture"""
        user_id = profile_data.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID required")
        
        update_data = {}
        if "name" in profile_data:
            update_data["name"] = profile_data["name"]
        if "email" in profile_data:
            update_data["email"] = profile_data["email"]
        if "phone" in profile_data:
            update_data["phone"] = profile_data["phone"]
        if "profile_picture" in profile_data:
            update_data["profile_picture"] = profile_data["profile_picture"]
        if "birth_date" in profile_data:
            update_data["birth_date"] = profile_data["birth_date"]
            update_data["zodiac_sign"] = get_zodiac_sign(profile_data["birth_date"])
        
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            
            # Update in users collection
            result = await db.users.update_one(
                {"id": user_id},
                {"$set": update_data}
            )
            
            # Also update in psychics collection if they're a psychic (cross-app sync)
            if "profile_picture" in update_data:
                user = await db.users.find_one({"id": user_id})
                if user and user.get("email"):
                    await db.psychics.update_one(
                        {"email": user["email"]},
                        {"$set": {"profile_picture": update_data["profile_picture"]}}
                    )
        
        return {"success": True, "message": "Profile updated successfully"}
    
    @router.put("/users/{user_id}/mark-first-reading-used")
    async def mark_first_reading_used(user_id: str):
        """Mark the user's first free reading as used"""
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Only mark if not already used
        if not user.get("first_reading_free_used", False):
            await db.users.update_one(
                {"id": user_id},
                {"$set": {
                    "first_reading_free_used": True,
                    "is_new_user": False  # No longer a new user after first reading
                }}
            )
        
        return {"success": True, "message": "First reading marked as used"}
    
    @router.post("/forgot-password")
    async def forgot_password(data: dict):
        """Send password reset email"""
        email = data.get("email", "").lower().strip()
        
        # Find user
        user = await db.users.find_one({"email": email})
        
        if user:
            # Generate reset token
            import secrets
            reset_token = secrets.token_urlsafe(32)
            reset_expiry = datetime.utcnow() + timedelta(hours=1)
            
            # Store reset token
            await db.users.update_one(
                {"email": email},
                {"$set": {
                    "reset_token": reset_token,
                    "reset_token_expiry": reset_expiry
                }}
            )
            
            # Send email (would be real in production)
            reset_url = f"https://sixthsensepsychics.com/reset-password?token={reset_token}"
            
            # Log the reset attempt (in real app, would send email)
            print(f"[PASSWORD RESET] Email: {email}, Token: {reset_token}")
        
        # Always return success to prevent email enumeration
        return {"success": True, "message": "If an account exists, a reset link has been sent."}
    
    @router.post("/reset-password")
    async def reset_password(data: dict):
        """Reset password with token"""
        token = data.get("token")
        new_password = data.get("password")
        
        if not token or not new_password:
            raise HTTPException(status_code=400, detail="Token and password required")
        
        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
        # Find user with valid token
        user = await db.users.find_one({
            "reset_token": token,
            "reset_token_expiry": {"$gt": datetime.utcnow()}
        })
        
        if not user:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        
        # Hash new password
        import bcrypt
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        
        # Update password and clear token
        await db.users.update_one(
            {"id": user["id"]},
            {
                "$set": {"password": hashed_password.decode('utf-8')},
                "$unset": {"reset_token": "", "reset_token_expiry": ""}
            }
        )
        
        return {"success": True, "message": "Password has been reset successfully"}
    
    # =============================================================================
    # SOCIAL AUTHENTICATION - Google OAuth via Emergent & Apple Sign-In
    # =============================================================================
    
    @router.post("/google/session")
    async def google_auth_session(data: dict):
        """
        Exchange Emergent OAuth session_id for user data and create/login user.
        This endpoint is called by the frontend after Google OAuth redirect.
        """
        session_id = data.get("session_id")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        
        try:
            # Call Emergent Auth to get user data
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    EMERGENT_SESSION_URL,
                    headers={"X-Session-ID": session_id},
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    raise HTTPException(status_code=401, detail="Invalid or expired session")
                
                google_user_data = response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Failed to verify session: {str(e)}")
        
        # Extract user info from Google OAuth response
        google_email = google_user_data.get("email")
        google_name = google_user_data.get("name")
        google_picture = google_user_data.get("picture")
        google_id = google_user_data.get("id")  # Google's unique user ID
        
        if not google_email:
            raise HTTPException(status_code=400, detail="Email not provided by Google")
        
        # Check if user exists by email or google_id
        existing_user = await db.users.find_one({
            "$or": [
                {"email": google_email},
                {"google_id": google_id}
            ]
        })
        
        if existing_user:
            # User exists - update Google info and login
            user = User(**existing_user)
            
            # Update profile picture if user doesn't have one
            update_data = {"google_id": google_id}
            if not existing_user.get("profile_picture") and google_picture:
                update_data["profile_picture"] = google_picture
            
            await db.users.update_one(
                {"id": user.id},
                {"$set": update_data}
            )
            
            token = create_access_token({"user_id": user.id, "email": user.email})
            
            return TokenResponse(
                access_token=token,
                user=UserResponse(**user.dict())
            )
        else:
            # Create new user with Google info
            user = User(
                email=google_email,
                name=google_name or google_email.split("@")[0],
                google_id=google_id,
                profile_picture=google_picture,
                is_new_user=True,
                first_reading_free_used=False,
                auth_provider="google"
            )
            
            user_dict = user.dict()
            # No password hash for social auth users
            user_dict["password_hash"] = None
            await db.users.insert_one(user_dict)
            
            token = create_access_token({"user_id": user.id, "email": user.email})
            
            return TokenResponse(
                access_token=token,
                user=UserResponse(**user.dict())
            )
    
    @router.post("/apple/verify")
    async def apple_auth_verify(data: dict):
        """
        Verify Apple Sign-In identity token and create/login user.
        Called by iOS app after Apple authentication.
        """
        identity_token = data.get("identity_token")
        apple_user_id = data.get("user")  # Apple's unique user identifier
        user_name = data.get("name")  # Only provided on first sign-in
        user_email = data.get("email")  # Only provided on first sign-in
        
        if not identity_token or not apple_user_id:
            raise HTTPException(status_code=400, detail="identity_token and user are required")
        
        try:
            # Verify the Apple identity token
            decoded_token = await verify_apple_token(identity_token)
            
            # Extract user info from verified token
            token_subject = decoded_token.get("sub")  # This should match apple_user_id
            token_email = decoded_token.get("email")
            
            # Use email from token if not provided directly (first sign-in only gets it in payload)
            email = user_email or token_email
            
        except ValueError as e:
            raise HTTPException(status_code=401, detail=f"Invalid Apple token: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Token verification failed: {str(e)}")
        
        # Check if user exists by Apple ID or email
        existing_user = await db.users.find_one({
            "$or": [
                {"apple_id": apple_user_id},
                {"email": email} if email else {"apple_id": apple_user_id}
            ]
        })
        
        if existing_user:
            # User exists - update Apple info and login
            user = User(**existing_user)
            
            # Link Apple ID if not already linked
            if not existing_user.get("apple_id"):
                await db.users.update_one(
                    {"id": user.id},
                    {"$set": {"apple_id": apple_user_id}}
                )
            
            token = create_access_token({"user_id": user.id, "email": user.email})
            
            return TokenResponse(
                access_token=token,
                user=UserResponse(**user.dict())
            )
        else:
            # Create new user with Apple info
            # Note: Apple only provides name on first sign-in, so we need to capture it
            user = User(
                email=email or f"{apple_user_id}@privaterelay.appleid.com",
                name=user_name or (email.split("@")[0] if email else "Apple User"),
                apple_id=apple_user_id,
                is_new_user=True,
                first_reading_free_used=False,
                auth_provider="apple"
            )
            
            user_dict = user.dict()
            user_dict["password_hash"] = None
            await db.users.insert_one(user_dict)
            
            token = create_access_token({"user_id": user.id, "email": user.email})
            
            return TokenResponse(
                access_token=token,
                user=UserResponse(**user.dict())
            )
    
    return router


# =============================================================================
# Apple Token Verification Helper
# =============================================================================

_apple_public_keys = {}

async def fetch_apple_public_keys():
    """Fetch Apple's public keys for JWT verification"""
    global _apple_public_keys
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(APPLE_PUBLIC_KEYS_URL)
            response.raise_for_status()
            keys_data = response.json()
            _apple_public_keys = {key["kid"]: key for key in keys_data.get("keys", [])}
    except Exception as e:
        print(f"Failed to fetch Apple public keys: {e}")

async def verify_apple_token(identity_token: str) -> dict:
    """Verify Apple identity token and return decoded claims"""
    global _apple_public_keys
    
    # Fetch keys if not cached
    if not _apple_public_keys:
        await fetch_apple_public_keys()
    
    if not _apple_public_keys:
        raise ValueError("Unable to fetch Apple public keys")
    
    try:
        # Decode header to get key ID
        import base64
        import json
        
        header_segment = identity_token.split(".")[0]
        # Add padding if needed
        padding = 4 - len(header_segment) % 4
        if padding != 4:
            header_segment += "=" * padding
        header = json.loads(base64.urlsafe_b64decode(header_segment))
        
        kid = header.get("kid")
        if not kid or kid not in _apple_public_keys:
            # Refresh keys and try again
            await fetch_apple_public_keys()
            if kid not in _apple_public_keys:
                raise ValueError(f"Key ID {kid} not found in Apple public keys")
        
        key_data = _apple_public_keys[kid]
        
        # Convert JWK to PEM format
        public_key = jwk_to_pem(key_data)
        
        # Verify and decode token
        decoded = jwt.decode(
            identity_token,
            public_key,
            algorithms=["RS256"],
            audience=APPLE_BUNDLE_ID,
            issuer=APPLE_AUTH_URL,
        )
        
        return decoded
        
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {str(e)}")

def jwk_to_pem(jwk: dict) -> str:
    """Convert JWK to PEM format for PyJWT"""
    import base64
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    
    # Extract RSA key components
    n_bytes = base64.urlsafe_b64decode(jwk['n'] + '==')
    e_bytes = base64.urlsafe_b64decode(jwk['e'] + '==')
    
    n = int.from_bytes(n_bytes, byteorder='big')
    e = int.from_bytes(e_bytes, byteorder='big')
    
    # Create RSA public key
    public_numbers = rsa.RSAPublicNumbers(e, n)
    public_key = public_numbers.public_key(default_backend())
    
    # Serialize to PEM
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return pem.decode('utf-8')
