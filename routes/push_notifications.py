from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import os
import json

# Firebase configuration
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_SERVER_KEY = os.getenv("FIREBASE_SERVER_KEY")
FIREBASE_ENABLED = bool(FIREBASE_SERVER_KEY)

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

class DeviceToken(BaseModel):
    user_id: str
    token: str
    platform: str = "unknown"  # ios, android, web
    device_name: Optional[str] = None

class PushNotification(BaseModel):
    user_id: str
    title: str
    body: str
    data: Optional[Dict[str, Any]] = None
    image_url: Optional[str] = None
    sound: str = "default"
    badge: Optional[int] = None

class BroadcastNotification(BaseModel):
    title: str
    body: str
    data: Optional[Dict[str, Any]] = None
    topic: str = "all_users"

def create_push_notification_routes(db):
    router = APIRouter(prefix="/push", tags=["push_notifications"])
    
    async def send_fcm_notification(token: str, title: str, body: str, data: dict = None, image_url: str = None):
        """Send notification via Firebase Cloud Messaging"""
        if not FIREBASE_ENABLED or not HTTPX_AVAILABLE:
            print(f"[MOCK PUSH] To: {token[:20]}..., Title: {title}, Body: {body}")
            return {"success": True, "mock": True}
        
        fcm_url = "https://fcm.googleapis.com/fcm/send"
        
        payload = {
            "to": token,
            "notification": {
                "title": title,
                "body": body,
                "sound": "default"
            },
            "data": data or {}
        }
        
        if image_url:
            payload["notification"]["image"] = image_url
        
        headers = {
            "Authorization": f"key={FIREBASE_SERVER_KEY}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(fcm_url, json=payload, headers=headers)
            return response.json()
    
    @router.get("/config")
    async def get_push_config():
        """Get push notification configuration"""
        return {
            "firebase_enabled": FIREBASE_ENABLED,
            "project_id": FIREBASE_PROJECT_ID,
            "supported_platforms": ["ios", "android", "web"]
        }
    
    @router.post("/register-token")
    async def register_device_token(device: DeviceToken):
        """Register a device token for push notifications"""
        # Check if token already exists
        existing = await db.device_tokens.find_one({
            "user_id": device.user_id,
            "token": device.token
        })
        
        if existing:
            # Update last seen
            await db.device_tokens.update_one(
                {"_id": existing["_id"]},
                {"$set": {"last_seen": datetime.utcnow()}}
            )
            return {"success": True, "message": "Token updated"}
        
        # Insert new token
        token_doc = {
            "id": str(uuid.uuid4()),
            "user_id": device.user_id,
            "token": device.token,
            "platform": device.platform,
            "device_name": device.device_name,
            "created_at": datetime.utcnow(),
            "last_seen": datetime.utcnow(),
            "is_active": True
        }
        await db.device_tokens.insert_one(token_doc)
        
        return {"success": True, "message": "Token registered"}
    
    @router.delete("/unregister-token")
    async def unregister_device_token(user_id: str, token: str):
        """Unregister a device token"""
        await db.device_tokens.delete_one({
            "user_id": user_id,
            "token": token
        })
        return {"success": True, "message": "Token unregistered"}
    
    @router.post("/send")
    async def send_push_notification(notification: PushNotification, background_tasks: BackgroundTasks):
        """Send a push notification to a user"""
        # Get user's device tokens
        tokens = await db.device_tokens.find({
            "user_id": notification.user_id,
            "is_active": True
        }).to_list(10)
        
        if not tokens:
            return {"success": False, "message": "No device tokens found for user"}
        
        # Log notification
        notification_log = {
            "id": str(uuid.uuid4()),
            "user_id": notification.user_id,
            "title": notification.title,
            "body": notification.body,
            "data": notification.data,
            "sent_to_devices": len(tokens),
            "created_at": datetime.utcnow(),
            "status": "sent"
        }
        await db.notification_logs.insert_one(notification_log)
        
        # Send to all devices
        results = []
        for token_doc in tokens:
            result = await send_fcm_notification(
                token_doc["token"],
                notification.title,
                notification.body,
                notification.data,
                notification.image_url
            )
            results.append(result)
        
        return {
            "success": True,
            "devices_notified": len(tokens),
            "notification_id": notification_log["id"],
            "firebase_enabled": FIREBASE_ENABLED
        }
    
    @router.post("/send-to-psychic")
    async def notify_psychic_new_client(psychic_id: str, client_name: str, session_type: str):
        """Send notification to psychic about new client"""
        notification = PushNotification(
            user_id=psychic_id,
            title="New Client Request! 🌟",
            body=f"{client_name} wants to start a {session_type} session with you.",
            data={
                "type": "new_client_request",
                "client_name": client_name,
                "session_type": session_type
            }
        )
        
        return await send_push_notification(notification, BackgroundTasks())
    
    @router.post("/send-session-reminder")
    async def send_session_reminder(user_id: str, psychic_name: str, minutes_until: int):
        """Send session reminder notification"""
        notification = PushNotification(
            user_id=user_id,
            title="Session Reminder ⏰",
            body=f"Your reading with {psychic_name} starts in {minutes_until} minutes.",
            data={
                "type": "session_reminder",
                "psychic_name": psychic_name,
                "minutes_until": minutes_until
            }
        )
        
        return await send_push_notification(notification, BackgroundTasks())
    
    @router.post("/send-new-message")
    async def send_new_message_notification(user_id: str, sender_name: str, message_preview: str):
        """Send new message notification"""
        notification = PushNotification(
            user_id=user_id,
            title=f"New message from {sender_name}",
            body=message_preview[:100] + ("..." if len(message_preview) > 100 else ""),
            data={
                "type": "new_message",
                "sender_name": sender_name
            }
        )
        
        return await send_push_notification(notification, BackgroundTasks())
    
    @router.get("/tokens/{user_id}")
    async def get_user_tokens(user_id: str):
        """Get user's registered device tokens"""
        tokens = await db.device_tokens.find(
            {"user_id": user_id},
            {"token": 0}  # Don't expose actual tokens
        ).to_list(10)
        
        return {
            "user_id": user_id,
            "device_count": len(tokens),
            "devices": [{
                "platform": t.get("platform"),
                "device_name": t.get("device_name"),
                "last_seen": t.get("last_seen").isoformat() if t.get("last_seen") else None
            } for t in tokens]
        }
    
    @router.get("/history/{user_id}")
    async def get_notification_history(user_id: str, limit: int = 20):
        """Get user's notification history"""
        logs = await db.notification_logs.find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        
        for log in logs:
            if "_id" in log:
                del log["_id"]
            if log.get("created_at"):
                log["created_at"] = log["created_at"].isoformat()
        
        return logs
    
    return router
