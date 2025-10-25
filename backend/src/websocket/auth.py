from fastapi import APIRouter, HTTPException, Depends, Request
from src.auth.auth import get_current_user
from src.db.models import User

router = APIRouter(prefix="/ws-auth", tags=["websocket-auth"])


@router.get("/token")
async def get_websocket_token(request: Request, current_user: User = Depends(get_current_user)):
    """
    Получить токен для WebSocket соединения из кук
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Токен не найден")

    return {
        "token": token,
        "user_id": current_user.user_id,
        "username": current_user.user_login,
        "full_name": current_user.user_full_name
    }