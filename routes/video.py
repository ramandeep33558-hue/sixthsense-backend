from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import os
import time
import hashlib
import hmac

# Agora configuration
AGORA_APP_ID = os.getenv("AGORA_APP_ID")
AGORA_APP_CERTIFICATE = os.getenv("AGORA_APP_CERTIFICATE")
AGORA_ENABLED = bool(AGORA_APP_ID and AGORA_APP_CERTIFICATE)

class VideoCallRequest(BaseModel):
    caller_id: str
    callee_id: str
    call_type: str = "video"  # video, voice
    psychic_id: Optional[str] = None

class JoinCallRequest(BaseModel):
    channel_name: str
    user_id: str
    role: str = "publisher"  # publisher, subscriber

def generate_agora_token(channel_name: str, uid: int, role: int = 1, expire_time: int = 3600):
    """Generate Agora RTC token"""
    if not AGORA_ENABLED:
        return None
    
    # This is a simplified token generation
    # In production, use the official Agora token builder
    current_time = int(time.time())
    privilege_expired_ts = current_time + expire_time
    
    # Create token (simplified - use official SDK in production)
    token_data = f"{AGORA_APP_ID}:{channel_name}:{uid}:{privilege_expired_ts}"
    signature = hmac.new(
        AGORA_APP_CERTIFICATE.encode(),
        token_data.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return f"{token_data}:{signature}"

def create_video_routes(db):
    router = APIRouter(prefix="/video", tags=["video"])
    
    @router.get("/config")
    async def get_video_config():
        """Get video call configuration"""
        return {
            "agora_enabled": AGORA_ENABLED,
            "app_id": AGORA_APP_ID if AGORA_ENABLED else "mock_app_id",
            "features": {
                "video_call": True,
                "voice_call": True,
                "screen_share": False,
                "recording": AGORA_ENABLED
            }
        }
    
    @router.post("/initiate-call")
    async def initiate_call(request: VideoCallRequest):
        """Initiate a video/voice call"""
        channel_name = f"call_{uuid.uuid4().hex[:12]}"
        
        # Create call record
        call = {
            "id": str(uuid.uuid4()),
            "channel_name": channel_name,
            "caller_id": request.caller_id,
            "callee_id": request.callee_id,
            "psychic_id": request.psychic_id,
            "call_type": request.call_type,
            "status": "ringing",
            "created_at": datetime.utcnow(),
            "started_at": None,
            "ended_at": None,
            "duration_seconds": 0
        }
        await db.calls.insert_one(call)
        
        # Generate tokens
        caller_token = None
        callee_token = None
        
        if AGORA_ENABLED:
            caller_uid = hash(request.caller_id) % 100000
            callee_uid = hash(request.callee_id) % 100000
            caller_token = generate_agora_token(channel_name, caller_uid)
            callee_token = generate_agora_token(channel_name, callee_uid)
        
        return {
            "call_id": call["id"],
            "channel_name": channel_name,
            "app_id": AGORA_APP_ID or "mock_app_id",
            "caller_token": caller_token or f"mock_token_{channel_name}_caller",
            "callee_token": callee_token or f"mock_token_{channel_name}_callee",
            "agora_enabled": AGORA_ENABLED
        }
    
    @router.post("/join")
    async def join_call(request: JoinCallRequest):
        """Get token to join an existing call"""
        token = None
        uid = hash(request.user_id) % 100000
        
        if AGORA_ENABLED:
            role = 1 if request.role == "publisher" else 2
            token = generate_agora_token(request.channel_name, uid, role)
        
        return {
            "token": token or f"mock_token_{request.channel_name}_{request.user_id}",
            "uid": uid,
            "channel_name": request.channel_name,
            "app_id": AGORA_APP_ID or "mock_app_id"
        }
    
    @router.put("/call/{call_id}/answer")
    async def answer_call(call_id: str):
        """Answer an incoming call"""
        result = await db.calls.update_one(
            {"id": call_id},
            {
                "$set": {
                    "status": "connected",
                    "started_at": datetime.utcnow()
                }
            }
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Call not found")
        
        return {"success": True, "status": "connected"}
    
    @router.put("/call/{call_id}/end")
    async def end_call(call_id: str):
        """End an active call"""
        call = await db.calls.find_one({"id": call_id})
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
        
        ended_at = datetime.utcnow()
        started_at = call.get("started_at")
        duration = 0
        
        if started_at:
            duration = int((ended_at - started_at).total_seconds())
        
        await db.calls.update_one(
            {"id": call_id},
            {
                "$set": {
                    "status": "ended",
                    "ended_at": ended_at,
                    "duration_seconds": duration
                }
            }
        )
        
        return {
            "success": True,
            "duration_seconds": duration,
            "duration_minutes": round(duration / 60, 2)
        }
    
    @router.put("/call/{call_id}/reject")
    async def reject_call(call_id: str):
        """Reject an incoming call"""
        await db.calls.update_one(
            {"id": call_id},
            {"$set": {"status": "rejected", "ended_at": datetime.utcnow()}}
        )
        return {"success": True, "status": "rejected"}
    
    @router.get("/call/{call_id}")
    async def get_call_status(call_id: str):
        """Get call status and details"""
        call = await db.calls.find_one({"id": call_id})
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
        
        if "_id" in call:
            del call["_id"]
        
        # Convert datetime objects
        for key in ["created_at", "started_at", "ended_at"]:
            if call.get(key):
                call[key] = call[key].isoformat()
        
        return call
    
    @router.get("/history/{user_id}")
    async def get_call_history(user_id: str, limit: int = 20):
        """Get user's call history"""
        calls = await db.calls.find(
            {"$or": [{"caller_id": user_id}, {"callee_id": user_id}]}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        
        for call in calls:
            if "_id" in call:
                del call["_id"]
            for key in ["created_at", "started_at", "ended_at"]:
                if call.get(key):
                    call[key] = call[key].isoformat()
        
        return calls
    
    return router
