from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List
import uuid
from datetime import datetime, timedelta
import sys
import random
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

ROOT_DIR = Path(__file__).parent

# MongoDB connection settings
mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017/sixthsense')
db_name = os.getenv('DB_NAME', 'sixthsense')

# Initialize MongoDB client with retry
def get_db():
    try:
        client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
        return client[db_name]
    except Exception as e:
        print(f"MongoDB connection error: {e}")
        raise

db = get_db()

# Create the main app
app = FastAPI(title="Psychic Marketplace API", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Import route modules
from routes.auth import create_auth_routes
from routes.psychics import create_psychic_routes
from routes.wallet import create_wallet_routes
from routes.questions import create_questions_routes
from routes.favorites import create_favorites_routes
from routes.tips import create_tips_routes
from routes.reviews import create_reviews_routes
from routes.chat import create_chat_routes
from routes.psychic_portal import create_psychic_portal_routes
from routes.admin import create_admin_routes
from routes.horoscope import create_horoscope_routes
from routes.messages import create_messages_routes
from routes.support import create_support_routes
from routes.applications import create_application_routes
from routes.notifications import create_notifications_routes
from routes.websocket import create_websocket_routes
from routes.payments import create_payment_routes
from routes.email import create_email_routes
from routes.storage import create_storage_routes
from routes.video import create_video_routes
from routes.push_notifications import create_push_notification_routes
from routes.psychics import create_user_routes

# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Psychic Marketplace API v1.0"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

# Public endpoint for active sale - accessible by all apps
@api_router.get("/sales/active")
async def get_active_sale_public():
    """Get currently active sale - public endpoint for client/psychic apps"""
    sale = await db.sales.find_one({"is_active": True})
    if sale:
        if "_id" in sale:
            del sale["_id"]
        return sale
    return None

# Include the main router
app.include_router(api_router)

# Mount static files for generated images
static_dir = ROOT_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include feature routers
auth_router = create_auth_routes(db)
psychics_router = create_psychic_routes(db)
wallet_router = create_wallet_routes(db)
questions_router = create_questions_routes(db)
favorites_router = create_favorites_routes(db)
tips_router = create_tips_routes(db)
reviews_router = create_reviews_routes(db)
chat_router = create_chat_routes(db)
psychic_portal_router = create_psychic_portal_routes(db)
admin_router = create_admin_routes(db)
horoscope_router = create_horoscope_routes(db)
messages_router = create_messages_routes(db)
support_router = create_support_routes(db)
applications_router = create_application_routes(db)
notifications_router = create_notifications_routes(db)
websocket_router = create_websocket_routes(db)
payments_router = create_payment_routes(db)
email_router = create_email_routes(db)
storage_router = create_storage_routes(db)
video_router = create_video_routes(db)
push_router = create_push_notification_routes(db)
user_router = create_user_routes(db)

app.include_router(auth_router, prefix="/api")
app.include_router(psychics_router, prefix="/api")
app.include_router(wallet_router, prefix="/api")
app.include_router(questions_router, prefix="/api")
app.include_router(favorites_router, prefix="/api")
app.include_router(tips_router, prefix="/api")
app.include_router(reviews_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(psychic_portal_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(horoscope_router, prefix="/api")
app.include_router(messages_router, prefix="/api")
app.include_router(support_router, prefix="/api")
app.include_router(applications_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(websocket_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.include_router(email_router, prefix="/api")
app.include_router(storage_router, prefix="/api")
app.include_router(video_router, prefix="/api")
app.include_router(push_router, prefix="/api")
app.include_router(user_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Promotional notification messages
PROMOTIONAL_MESSAGES = [
    {"title": "Need Clarity? ✨", "body": "Your favorite psychics are online now! Get a reading and find the answers you seek."},
    {"title": "The Stars Are Aligned 🌟", "body": "Today is the perfect day for a reading. Connect with an advisor and discover what the universe has in store."},
    {"title": "Trust Your Intuition 🔮", "body": "Something on your mind? Our gifted psychics are ready to guide you through any situation."},
    {"title": "Special Energy Today 💫", "body": "We sense big things for you! Get a personalized reading now and unlock your potential."},
    {"title": "Your Path Awaits 🌙", "body": "Questions about love, career, or life? Our top-rated advisors are waiting to help you."},
    {"title": "Time for Guidance 🌺", "body": "Life's big decisions deserve cosmic insight. Book a reading with a trusted psychic today!"},
    {"title": "Unlock Your Future 🗝️", "body": "Curious about what's next? Our psychics can reveal the path ahead. Connect now!"},
    {"title": "Spiritual Wellness Check ✨", "body": "When was your last reading? Reconnect with your spiritual journey today."},
]

# App rating prompt messages
APP_RATING_MESSAGES = {
    "client_positive": {
        "title": "Enjoying Your Experience? ⭐",
        "body": "We noticed you had a great reading! If you're loving the app, please take a moment to rate us. Your feedback helps others discover us!"
    },
    "psychic_positive": {
        "title": "You're Doing Amazing! 🌟",
        "body": "Congratulations on that 5-star rating and tip! If you're enjoying being an advisor, please rate the app. Your review helps other psychics join!"
    }
}

async def check_and_send_app_rating_prompt(user_id: str, user_type: str, trigger_type: str):
    """
    Check if user should receive app rating prompt and send if appropriate.
    
    For clients: Triggered after positive rating (4-5 stars) AND session > 10 min
    For psychics: Triggered after receiving 5-star rating AND tip > $5
    """
    try:
        # Check if we already prompted this user recently (within 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_prompt = await db.notifications.find_one({
            "user_id": user_id,
            "type": "app_rating_prompt",
            "created_at": {"$gte": thirty_days_ago}
        })
        
        if recent_prompt:
            return None  # Don't spam with rating prompts
        
        # Get appropriate message
        message_key = f"{user_type}_positive"
        message = APP_RATING_MESSAGES.get(message_key)
        
        if not message:
            return None
        
        # Create and save notification
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": message["title"],
            "body": message["body"],
            "type": "app_rating_prompt",
            "trigger": trigger_type,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        
        await db.notifications.insert_one(notification)
        logger.info(f"📱 Sent app rating prompt to {user_type} {user_id}")
        return notification
        
    except Exception as e:
        logger.error(f"Error sending app rating prompt: {e}")
        return None

async def send_scheduled_promotional_notifications():
    """Scheduled task to send promotional notifications to all users (max 2/day per user)"""
    try:
        logger.info("🔔 Running scheduled promotional notifications...")
        
        users = await db.users.find({"status": "active"}).to_list(10000)
        sent_count = 0
        
        for user in users:
            user_id = user.get("id")
            
            # Check if user has disabled promotional notifications
            prefs = await db.notification_preferences.find_one({"user_id": user_id})
            if prefs and not prefs.get("promotional", True):
                continue
            
            # Check how many promotional notifications were sent today
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_count = await db.notifications.count_documents({
                "user_id": user_id,
                "type": "promotional",
                "created_at": {"$gte": today_start}
            })
            
            # Only send if fewer than 2 promotional notifications sent today
            if today_count >= 2:
                continue
            
            # Pick a random promotional message
            message = random.choice(PROMOTIONAL_MESSAGES)
            
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": message["title"],
                "body": message["body"],
                "type": "promotional",
                "is_read": False,
                "created_at": datetime.utcnow()
            }
            
            await db.notifications.insert_one(notification)
            sent_count += 1
        
        logger.info(f"✅ Sent {sent_count} promotional notifications")
        return sent_count
    except Exception as e:
        logger.error(f"❌ Error sending promotional notifications: {e}")
        return 0

# Initialize scheduler
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    """Start the scheduler when app starts"""
    # Schedule notifications at 9 AM and 6 PM UTC daily
    scheduler.add_job(
        send_scheduled_promotional_notifications,
        CronTrigger(hour=9, minute=0),  # 9:00 AM UTC
        id="morning_notifications",
        replace_existing=True
    )
    scheduler.add_job(
        send_scheduled_promotional_notifications,
        CronTrigger(hour=18, minute=0),  # 6:00 PM UTC
        id="evening_notifications",
        replace_existing=True
    )
    scheduler.start()
    logger.info("📅 Promotional notification scheduler started (9 AM & 6 PM UTC daily)")

@app.on_event("shutdown")
async def shutdown_db_client():
    scheduler.shutdown()
    client.close()
    logger.info("🛑 Scheduler and database connection closed")
