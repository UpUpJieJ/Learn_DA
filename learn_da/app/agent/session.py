import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.agent.schemas import AgentChatMessage, AgentContext
from config.settings import settings


@dataclass
class ChatSession:
    id: str
    created_at: datetime
    updated_at: datetime
    messages: List[AgentChatMessage] = field(default_factory=list)
    context: Optional[AgentContext] = None
    metadata: Dict = field(default_factory=dict)


class SessionStore:
    async def get(self, session_id: str) -> Optional[ChatSession]:
        pass

    async def save(self, session: ChatSession) -> None:
        pass

    async def delete(self, session_id: str) -> None:
        pass

    async def list(self, limit: int = 50) -> List[ChatSession]:
        pass


class InMemorySessionStore(SessionStore):
    def __init__(self):
        self._sessions: Dict[str, ChatSession] = {}

    async def get(self, session_id: str) -> Optional[ChatSession]:
        return self._sessions.get(session_id)

    async def save(self, session: ChatSession) -> None:
        session.updated_at = datetime.now()
        self._sessions[session.id] = session

    async def delete(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]

    async def list(self, limit: int = 50) -> List[ChatSession]:
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True,
        )
        return sessions[:limit]


class JSONFileSessionStore(SessionStore):
    def __init__(self, directory: str = "sessions"):
        self._dir = Path(directory)
        self._dir.mkdir(exist_ok=True)

    def _get_session_path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    async def get(self, session_id: str) -> Optional[ChatSession]:
        path = self._get_session_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return ChatSession(
                    id=data["id"],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                    messages=[
                        AgentChatMessage(role=m["role"], content=m["content"])
                        for m in data.get("messages", [])
                    ],
                    context=AgentContext(**data["context"]) if data.get("context") else None,
                    metadata=data.get("metadata", {}),
                )
        except Exception:
            return None

    async def save(self, session: ChatSession) -> None:
        session.updated_at = datetime.now()
        path = self._get_session_path(session.id)
        data = {
            "id": session.id,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "messages": [
                {"role": m.role, "content": m.content} for m in session.messages
            ],
            "context": session.context.model_dump() if session.context else None,
            "metadata": session.metadata,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def delete(self, session_id: str) -> None:
        path = self._get_session_path(session_id)
        if path.exists():
            path.unlink()

    async def list(self, limit: int = 50) -> List[ChatSession]:
        sessions = []
        for path in self._dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sessions.append(
                        ChatSession(
                            id=data["id"],
                            created_at=datetime.fromisoformat(data["created_at"]),
                            updated_at=datetime.fromisoformat(data["updated_at"]),
                            messages=[
                                AgentChatMessage(role=m["role"], content=m["content"])
                                for m in data.get("messages", [])
                            ],
                            context=AgentContext(**data["context"]) if data.get("context") else None,
                            metadata=data.get("metadata", {}),
                        )
                    )
            except Exception:
                continue
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions[:limit]


def create_session(
    context: Optional[AgentContext] = None,
    metadata: Optional[Dict] = None,
) -> ChatSession:
    now = datetime.now()
    return ChatSession(
        id=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        messages=[],
        context=context,
        metadata=metadata or {},
    )


def get_session_store() -> SessionStore:
    store_type = getattr(settings, "SESSION_STORE_TYPE", "in_memory")
    if store_type == "json_file":
        directory = getattr(settings, "SESSION_STORE_PATH", "sessions")
        return JSONFileSessionStore(directory)
    return InMemorySessionStore()
