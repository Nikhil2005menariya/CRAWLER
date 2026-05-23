from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid
import backend.db.mongodb as mongodb
from backend.api.routes.auth import get_current_user
from backend.agents.retrieval_agent import build_retrieval_agent
from langchain_core.messages import HumanMessage, AIMessage

agent = build_retrieval_agent()

router = APIRouter()

class ChatMessage(BaseModel):
    content: str

class ChatSessionCreate(BaseModel):
    title: str = "New Chat"

@router.post("/session")
async def create_session(session_data: ChatSessionCreate, current_user: dict = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    chat_doc = {
        "session_id": session_id,
        "user_id": str(current_user["_id"]),
        "title": session_data.title,
        "messages": [],
        "created_at": datetime.utcnow()
    }
    await mongodb.db.chats.insert_one(chat_doc)
    return {"session_id": session_id, "title": session_data.title}

@router.get("/sessions")
async def get_sessions(current_user: dict = Depends(get_current_user)):
    cursor = mongodb.db.chats.find({"user_id": str(current_user["_id"])}).sort("created_at", -1)
    sessions = []
    async for doc in cursor:
        sessions.append({
            "session_id": doc["session_id"],
            "title": doc["title"],
            "created_at": doc["created_at"]
        })
    return sessions

@router.get("/session/{session_id}")
async def get_session(session_id: str, current_user: dict = Depends(get_current_user)):
    chat = await mongodb.db.chats.find_one({"session_id": session_id, "user_id": str(current_user["_id"])})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"session_id": chat["session_id"], "title": chat["title"], "messages": chat["messages"]}

@router.post("/message/{session_id}")
async def send_message(session_id: str, message: ChatMessage, current_user: dict = Depends(get_current_user)):
    chat = await mongodb.db.chats.find_one({"session_id": session_id, "user_id": str(current_user["_id"])})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Save human message
    human_msg = {"role": "user", "content": message.content, "timestamp": datetime.utcnow()}
    await mongodb.db.chats.update_one(
        {"session_id": session_id},
        {"$push": {"messages": human_msg}}
    )
    
    # Run the ReAct agent
    # We should reconstruct the history
    history = []
    for msg in chat["messages"]:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        else:
            history.append(AIMessage(content=msg["content"]))
    history.append(HumanMessage(content=message.content))
    
    global agent
    try:
        response = agent.invoke({"messages": history})
    except Exception as exc:
        exc_str = str(exc)
        if any(w in exc_str for w in ["429", "rate_limit", "400", "tool_use_failed", "BadRequestError", "Failed to call a function"]):
            import logging, os
            logging.getLogger(__name__).warning("Active chatbot agent rate limited or tool-use failed. Re-building agent with Llama 8B fallback...")
            agent = build_retrieval_agent(force_model="llama-3.1-8b-instant")
            try:
                response = agent.invoke({"messages": history})
            except Exception as inner_exc:
                logging.getLogger(__name__).error("Fallback agent also failed: %s. Proceeding with a simple text model without tools...", inner_exc)
                from langchain_openai import ChatOpenAI
                direct_llm = ChatOpenAI(
                    openai_api_base="https://api.groq.com/openai/v1",
                    openai_api_key=os.environ.get("GROQ_API_KEY"),
                    model_name="llama-3.1-8b-instant",
                    temperature=0.0
                )
                direct_res = direct_llm.invoke(history)
                # Save assistant response to DB
                ai_msg = {"role": "assistant", "content": direct_res.content, "timestamp": datetime.utcnow()}
                await mongodb.db.chats.update_one(
                    {"session_id": session_id},
                    {"$push": {"messages": ai_msg}}
                )
                return {"reply": direct_res.content}
        else:
            raise exc
    ai_content = response["messages"][-1].content
    
    # Save AI message
    ai_msg = {"role": "assistant", "content": ai_content, "timestamp": datetime.utcnow()}
    await mongodb.db.chats.update_one(
        {"session_id": session_id},
        {"$push": {"messages": ai_msg}}
    )
    
    return {"reply": ai_content}
