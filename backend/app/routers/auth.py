from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import Actor, client_ip, current_actor, get_db, get_settings, terminal_from
from ..models import AuthSession, User
from ..schemas import LoginIn, OtpResendIn, OtpVerifyIn, RefreshIn, SetupIn
from ..serializers import user_public
from ..services import auth, setup
from ..util import AppError, iso

router = APIRouter(prefix="/api/auth", tags=["auth"])
REFRESH_COOKIE = "dd_refresh"


def _respond(result: dict, response: Response, settings: Settings) -> dict:
    if result.get("status") == "ok":
        response.set_cookie(REFRESH_COOKIE, result.pop("refresh_token"), httponly=True, secure=settings.cookie_secure,
                            samesite="strict", max_age=settings.session_hours * 3600, path="/api/auth")
    return result


def _ctx(request: Request) -> dict:
    return {"terminal": terminal_from(request), "ip": client_ip(request),
            "user_agent": request.headers.get("user-agent", "")}


@router.get("/setup")
def setup_status(db: Session = Depends(get_db)):
    """Tells the sign-in screen whether to show the first-time sign-up form."""
    return {"needs_setup": setup.needs_setup(db)}


@router.post("/setup")
def run_setup(body: SetupIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    request.app.state.limiter.check(f"setup:{client_ip(request)}", 10)
    return setup.run_setup(db, settings, request.app.state.peer, body)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings)):
    request.app.state.limiter.check(f"login:{client_ip(request)}", settings.login_rate_per_minute)
    result = auth.login(db, settings, request.app.state.peer, body.username, body.password, **_ctx(request))
    return _respond(result, response, settings)


@router.post("/otp/verify")
def otp_verify(body: OtpVerifyIn, request: Request, response: Response, db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings)):
    request.app.state.limiter.check(f"otp:{client_ip(request)}", settings.login_rate_per_minute)
    result = auth.verify_otp(db, settings, request.app.state.peer, body.challenge_id, body.code, **_ctx(request))
    return _respond(result, response, settings)


@router.post("/otp/resend")
def otp_resend(body: OtpResendIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    request.app.state.limiter.check(f"otp:{client_ip(request)}", settings.login_rate_per_minute)
    return auth.resend_otp(db, settings, request.app.state.peer, body.challenge_id)


@router.post("/refresh")
def refresh(request: Request, response: Response, body: RefreshIn | None = None, db: Session = Depends(get_db),
            settings: Settings = Depends(get_settings)):
    token = request.cookies.get(REFRESH_COOKIE) or (body.refresh_token if body else None)
    if not token:
        raise AppError("SESSION_EXPIRED", "Please sign in.", 401)
    return _respond(auth.refresh(db, settings, token), response, settings)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    actor = None
    try:
        actor = current_actor(request, db, settings)
    except AppError:
        pass
    auth.logout(db, settings, actor, request.cookies.get(REFRESH_COOKIE))
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return {"status": "ok"}


@router.get("/me")
def me(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    user = db.get(User, actor.user_id)
    session = db.get(AuthSession, actor.session_id)
    return {"user": user_public(user), "session": {"id": str(session.id), "channel": session.channel,
                                                    "terminal": session.terminal, "offline": session.offline,
                                                    "expires_at": iso(session.expires_at)}}
