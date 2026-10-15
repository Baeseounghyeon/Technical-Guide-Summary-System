from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_vendors, get_active_user
from ..models import User, UserStatus
from ..schemas import LoginIn, MeOut, SignupIn, TokenOut, UserOut, VendorOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["인증"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, db: Session = Depends(get_db)) -> User:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 가입된 이메일입니다.")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        name=body.name,
        phone=body.phone,
        department=body.department,
        company_name=body.company_name,
    )
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다.")
    if user.status == UserStatus.PENDING:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "관리자 승인 대기 중입니다.")
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "사용이 중지된 계정입니다.")
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> MeOut:
    return MeOut(
        **UserOut.model_validate(user).model_dump(),
        partner_name=user.partner.name if user.partner else None,
        vendors=[VendorOut.model_validate(v) for v in accessible_vendors(db, user)],
    )
