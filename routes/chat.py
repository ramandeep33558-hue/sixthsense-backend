from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime
import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from models.chat import ChatSession, ChatSessionCreate, ChatMessage, AddMinutesRequest

def create_chat_routes(db):
    router = APIRouter(prefix="/chat", tags=["chat"])
    
    @router.post("/start")
    async def start_session(session: ChatSessionCreate, user_id: str = None):
        """Start a new chat/phone/video session"""
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID required")
        
        # Get psychic's rate
        psychic = await db.psychics.find_one({"id": session.psychic_id})
        if not psychic:
            raise HTTPException(status_code=404, detail="Psychic not found")
        
        if psychic.get("online_status") == "offline":
            raise HTTPException(status_code=400, detail="Psychic is offline")
        
        # Get rate based on session type
        rate_key = f"{session.session_type}_rate"
        rate = psychic.get(rate_key, 2.99)
        
        # Calculate initial cost
        initial_cost = rate * session.initial_minutes
        
        new_session = ChatSession(
            client_id=user_id,
            psychic_id=session.psychic_id,
            session_type=session.session_type,
            rate_per_minute=rate,
            auto_end_minutes=session.initial_minutes,
            total_cost=initial_cost
        )
        
        await db.chat_sessions.insert_one(new_session.dict())
        
        # Update psychic status to busy
        await db.psychics.update_one(
            {"id": session.psychic_id},
            {"$set": {"online_status": "busy"}}
        )
        
        return {"success": True, "session": new_session.dict()}
    
    @router.post("/message")
    async def send_message(session_id: str, message: str, user_id: str = None, user_type: str = "client", image_url: str = None):
        """Send a message in a chat session"""
        session = await db.chat_sessions.find_one({"id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session.get("status") != "active":
            raise HTTPException(status_code=400, detail="Session is not active")
        
        new_message = ChatMessage(
            sender_type=user_type,
            sender_id=user_id or "unknown",
            message=message,
            message_type="image" if image_url else "text",
            image_url=image_url
        )
        
        await db.chat_sessions.update_one(
            {"id": session_id},
            {"$push": {"messages": new_message.dict()}}
        )
        
        return {"success": True, "message": new_message.dict()}
    
    @router.post("/add-minutes")
    async def add_minutes(request: AddMinutesRequest, user_id: str = None):
        """Add more minutes to an active session (1-tap add)"""
        session = await db.chat_sessions.find_one({"id": request.session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session.get("status") != "active":
            raise HTTPException(status_code=400, detail="Session is not active")
        
        additional_cost = session.get("rate_per_minute", 2.99) * request.minutes
        
        await db.chat_sessions.update_one(
            {"id": request.session_id},
            {
                "$inc": {
                    "auto_end_minutes": request.minutes,
                    "total_cost": additional_cost
                },
                "$set": {"warning_sent": False}  # Reset warning
            }
        )
        
        return {"success": True, "minutes_added": request.minutes, "additional_cost": additional_cost}
    
    @router.post("/end/{session_id}")
    async def end_session(session_id: str):
        """End a chat session"""
        session = await db.chat_sessions.find_one({"id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Calculate final duration and cost
        started_at = session.get("started_at", datetime.utcnow())
        duration_minutes = (datetime.utcnow() - started_at).total_seconds() / 60
        total_cost = duration_minutes * session.get("rate_per_minute", 2.99)
        
        await db.chat_sessions.update_one(
            {"id": session_id},
            {
                "$set": {
                    "status": "ended",
                    "ended_at": datetime.utcnow(),
                    "total_minutes": round(duration_minutes, 2),
                    "total_cost": round(total_cost, 2)
                }
            }
        )
        
        # Set psychic back to online
        await db.psychics.update_one(
            {"id": session.get("psychic_id")},
            {"$set": {"online_status": "online"}}
        )
        
        # Update psychic earnings (40%)
        psychic_earnings = total_cost * 0.40
        await db.psychics.update_one(
            {"id": session.get("psychic_id")},
            {"$inc": {"total_earnings": psychic_earnings, "total_readings": 1}}
        )
        
        return {
            "success": True,
            "duration_minutes": round(duration_minutes, 2),
            "total_cost": round(total_cost, 2)
        }
    
    @router.get("/{session_id}")
    async def get_session(session_id: str):
        """Get session details"""
        session = await db.chat_sessions.find_one({"id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    
    @router.get("/active/{user_id}")
    async def get_active_sessions(user_id: str):
        """Get user's active sessions"""
        sessions = await db.chat_sessions.find({
            "client_id": user_id,
            "status": "active"
        }).to_list(10)
        return sessions
    
    @router.get("/history/{user_id}")
    async def get_session_history(user_id: str, limit: int = 20):
        """Get user's session history"""
        sessions = await db.chat_sessions.find({
            "client_id": user_id
        }).sort("started_at", -1).to_list(limit)
        return sessions
    
    return router
