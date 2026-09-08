"""Development-only request identity resolution for the local prototype."""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import User


USER_ID_HEADER = "X-MemoryCue-User-Id"


def get_current_user(
    user_id_header: str | None = Header(default=None, alias=USER_ID_HEADER),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the explicitly selected development user for one request."""

    if user_id_header is None or not user_id_header.strip():
        raise HTTPException(status_code=401, detail="User identity is required.")

    try:
        user_id = int(user_id_header.strip())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="User not found.") from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user
