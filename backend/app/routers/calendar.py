"""홈 달력: 사용자 개인 일정 (본인 것만 보고 고친다)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user
from ..models import CalendarEvent, User
from ..schemas import ORM

router = APIRouter(prefix="/api/calendar", tags=["달력"])

Purpose = Literal["meeting", "outside", "vacation", "education", "other"]
TIME = r"^([01]\d|2[0-3]):[0-5]\d$"


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    purpose: Purpose = "meeting"
    start_date: date
    end_date: date
    start_time: str | None = Field(None, pattern=TIME)
    end_time: str | None = Field(None, pattern=TIME)
    content: str | None = Field(None, max_length=5000)

    @model_validator(mode="after")
    def _check_range(self) -> "EventIn":
        if self.end_date < self.start_date:
            raise ValueError("끝나는 날짜가 시작 날짜보다 빠릅니다.")
        if self.start_date == self.end_date and self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError("끝나는 시간이 시작 시간보다 빠릅니다.")
        return self


class EventOut(ORM):
    id: int
    title: str
    purpose: str
    start_date: str
    end_date: str
    start_time: str | None
    end_time: str | None
    content: str | None


def _apply(event: CalendarEvent, body: EventIn) -> None:
    event.title = body.title.strip()
    event.purpose = body.purpose
    event.start_date = body.start_date.isoformat()
    event.end_date = body.end_date.isoformat()
    event.start_time = body.start_time
    event.end_time = body.end_time
    event.content = (body.content or "").strip() or None


def _own(db: Session, user: User, event_id: int) -> CalendarEvent:
    event = db.get(CalendarEvent, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    return event


@router.get("/events", response_model=list[EventOut])
def list_events(start: date, end: date, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[CalendarEvent]:
    """start~end(포함) 기간과 겹치는 내 일정."""
    query = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user.id,
            CalendarEvent.start_date <= end.isoformat(),
            CalendarEvent.end_date >= start.isoformat(),
        )
        .order_by(CalendarEvent.start_date, CalendarEvent.start_time, CalendarEvent.id)
    )
    return list(db.scalars(query))


@router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(body: EventIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> CalendarEvent:
    event = CalendarEvent(user_id=user.id)
    _apply(event, body)
    db.add(event)
    db.commit()
    return event


@router.put("/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> CalendarEvent:
    event = _own(db, user, event_id)
    _apply(event, body)
    db.commit()
    return event


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    db.delete(_own(db, user, event_id))
    db.commit()
