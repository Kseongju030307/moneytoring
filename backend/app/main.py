from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, engine, Base
from app.models import User, ChatSession, ChatMessage  # noqa: F401
from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_user_by_username,
    hash_password,
)
from app.document_service import list_documents, upload_pdf, delete_pdf
from app.query_parser import parse_query
from app.rag import ask_rag


app = FastAPI(title="Samsung Earnings RAG API")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


# ── Auth schemas ──────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str

    model_config = {"from_attributes": True}


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@app.post("/auth/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    if get_user_by_username(db, request.username):
        raise HTTPException(status_code=400, detail="이미 사용 중인 아이디입니다")
    if db.query(User).filter(User.email == request.email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다")

    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hash_password(request.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "회원가입이 완료되었습니다", "username": user.username}


@app.post("/auth/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="아이디 또는 비밀번호가 올바르지 않습니다")
    token = create_access_token(user.username)
    return TokenResponse(access_token=token, token_type="bearer", username=user.username)


@app.get("/auth/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


# ── Chat schemas ───────────────────────────────────────────────────────────────

class MessageItem(BaseModel):
    role: str
    content: str
    parsed_query: Optional[dict] = None


class ChatRequest(BaseModel):
    question: str
    k: int = 8
    history: list[MessageItem] = []
    chat_id: Optional[str] = None


class SourceItem(BaseModel):
    file_name: str
    page: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    parsed_query: dict


class DeleteDocumentRequest(BaseModel):
    file_name: str


# ── Chat session schemas ───────────────────────────────────────────────────────

class CreateChatRequest(BaseModel):
    chat_id: str
    title: str = "새 채팅"


class UpdateChatTitleRequest(BaseModel):
    title: str


# ── Utility ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


def get_last_financial_parsed(history: list[dict]) -> dict | None:
    for msg in reversed(history):
        parsed = msg.get("parsed_query")
        if not isinstance(parsed, dict):
            continue
        if parsed.get("intent") == "financial":
            return parsed
    return None


def merge_parsed_query(current: dict, previous: dict | None) -> dict:
    if not previous:
        return current
    if current.get("intent") == "general":
        return current

    merged = dict(current)
    if not merged.get("quarters"):
        merged["quarters"] = previous.get("quarters", [])
    if not merged.get("business_units"):
        merged["business_units"] = previous.get("business_units", [])
    if not merged.get("metrics"):
        merged["metrics"] = previous.get("metrics", [])
    if merged.get("intent") != "financial" and previous.get("intent") == "financial":
        if merged.get("quarters") or merged.get("metrics") or merged.get("business_units"):
            merged["intent"] = "financial"
    return merged


# ── Chat session endpoints ────────────────────────────────────────────────────

@app.get("/chats")
def list_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return {
        "chats": [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": s.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "messages": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "sources": m.sources or [],
                        "parsed_query": m.parsed_query,
                        "timestamp": m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    for m in s.messages
                ],
            }
            for s in sessions
        ]
    }


@app.post("/chats")
def create_chat(
    request: CreateChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = ChatSession(
        id=request.chat_id,
        user_id=current_user.id,
        title=request.title,
    )
    db.add(session)
    db.commit()
    return {"id": session.id, "title": session.title}


@app.put("/chats/{chat_id}")
def update_chat_title(
    chat_id: str,
    request: UpdateChatTitleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == chat_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="채팅을 찾을 수 없습니다")
    session.title = request.title
    session.updated_at = datetime.utcnow()
    db.commit()
    return {"id": session.id, "title": session.title}


@app.delete("/chats/{chat_id}")
def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == chat_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="채팅을 찾을 수 없습니다")
    db.delete(session)
    db.commit()
    return {"message": "채팅이 삭제되었습니다"}


# ── Chat & document endpoints (auth required) ─────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    try:
        history = [msg.model_dump() for msg in request.history]
        current_parsed = parse_query(question)
        previous_parsed = get_last_financial_parsed(history)
        parsed = merge_parsed_query(current_parsed, previous_parsed)

        print("\n[CURRENT PARSED]")
        print(current_parsed)
        print("\n[PREVIOUS PARSED]")
        print(previous_parsed)
        print("\n[MERGED PARSED]")
        print(parsed)

        result = ask_rag(question, parsed=parsed, k=request.k)
        answer = result.get("answer", "")
        sources = result.get("sources", [])
        parsed_query = result.get("parsed_query", parsed)

        if request.chat_id:
            session = (
                db.query(ChatSession)
                .filter(
                    ChatSession.id == request.chat_id,
                    ChatSession.user_id == current_user.id,
                )
                .first()
            )
            if session:
                db.add(ChatMessage(
                    session_id=request.chat_id,
                    role="user",
                    content=question,
                    sources=[],
                    parsed_query=None,
                ))
                db.add(ChatMessage(
                    session_id=request.chat_id,
                    role="assistant",
                    content=answer,
                    sources=sources,
                    parsed_query=parsed_query,
                ))
                session.updated_at = datetime.utcnow()
                db.commit()

        return ChatResponse(
            answer=answer,
            sources=[
                SourceItem(file_name=s.get("file_name", "unknown"), page=s.get("page"))
                for s in sources
            ],
            parsed_query=parsed_query,
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류가 발생했습니다: {e}")


@app.get("/documents")
def get_documents(current_user: User = Depends(get_current_user)):
    return {"documents": list_documents()}


@app.post("/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    return upload_pdf(file)


@app.post("/documents/delete")
def delete_document(
    request: DeleteDocumentRequest,
    current_user: User = Depends(get_current_user),
):
    return delete_pdf(request.file_name)
