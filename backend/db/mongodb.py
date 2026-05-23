import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "myk_scraper")

client: AsyncIOMotorClient = None
db = None

async def connect_to_mongo():
    global client, db
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.chats.create_index("session_id")
    await db.chats.create_index("user_id")

async def close_mongo_connection():
    global client
    if client:
        client.close()
