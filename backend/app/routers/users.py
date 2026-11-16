import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import Actor, get_db, require
from ..models import User
from ..schemas import PasswordResetIn, UserCreate, UserUpdate
from ..serializers import user_public
from ..services import directory
from .common import forward_to_directory

router = APIRouter(prefix="/api/users", tags=["users"])


def _hospital(request: Request) -> bool:
    return request.app.state.settings.is_hospital


@router.get("")
def list_users(_: Actor = Depends(require("users.manage")), db: Session = Depends(get_db)):
    return {"items": [user_public(u) for u in db.scalars(select(User).order_by(User.full_name))]}


@router.post("")
def create_user(body: UserCreate, request: Request, actor: Actor = Depends(require("users.manage")), db: Session = Depends(get_db)):
    if _hospital(request):
        try:
            return forward_to_directory(request, db, actor, "/users", body.model_dump())
        except AppError as e:
            if e.code == "DIRECTORY_OFFLINE":
                user = directory.create_user(db, request.app.state.settings, actor, body)
                user_obj = db.get(User, uuid.UUID(user["id"]))
                if user_obj:
                    user_obj.is_verified = True
                    user_obj.offline_login_enabled = True
                    db.commit()
                return user
            raise
    return directory.create_user(db, request.app.state.settings, actor, body)


@router.patch("/{user_id}")
def update_user(user_id: uuid.UUID, body: UserUpdate, request: Request, actor: Actor = Depends(require("users.manage")),
                db: Session = Depends(get_db)):
    if _hospital(request):
        try:
            return forward_to_directory(request, db, actor, f"/users/{user_id}/update", body.model_dump())
        except AppError as e:
            if e.code == "DIRECTORY_OFFLINE":
                return directory.update_user(db, request.app.state.settings, actor, user_id, body)
            raise
    return directory.update_user(db, request.app.state.settings, actor, user_id, body)


@router.post("/{user_id}/reset-password")
def reset_password(user_id: uuid.UUID, body: PasswordResetIn, request: Request,
                   actor: Actor = Depends(require("users.manage")), db: Session = Depends(get_db)):
    if _hospital(request):
        try:
            return forward_to_directory(request, db, actor, f"/users/{user_id}/reset-password", body.model_dump())
        except AppError as e:
            if e.code == "DIRECTORY_OFFLINE":
                return directory.reset_password(db, request.app.state.settings, actor, user_id, body.password)
            raise
    return directory.reset_password(db, request.app.state.settings, actor, user_id, body.password)


@router.post("/{user_id}/revoke-sessions")
def revoke_sessions(user_id: uuid.UUID, request: Request, actor: Actor = Depends(require("users.manage")),
                    db: Session = Depends(get_db)):
    if _hospital(request):
        # revoke immediately on this server too, so it works even before the next directory pull
        directory._revoke_local_sessions(db, user_id)
        db.commit()
        return forward_to_directory(request, db, actor, f"/users/{user_id}/revoke-sessions")
    return directory.revoke_sessions(db, request.app.state.settings, actor, user_id)


@router.post("/{user_id}/unlock")
def unlock(user_id: uuid.UUID, request: Request, actor: Actor = Depends(require("users.manage")), db: Session = Depends(get_db)):
    return directory.unlock_user(db, request.app.state.settings, actor, user_id)
