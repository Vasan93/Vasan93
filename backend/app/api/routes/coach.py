"""Coaching endpoints: explanations, lessons, comprehension checks, chat."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RateLimit, get_current_user
from app.coaching import service
from app.core.db import get_db
from app.models import AnalyzedMove, Game, Lesson, User
from app.schemas.coaching import (
    ChatRequest,
    CheckAnswer,
    CheckResult,
    CoachingText,
    ExplainRequest,
    LessonOut,
    LessonRequest,
)
from app.weakness.taxonomy import TAXONOMY, label as taxonomy_label

router = APIRouter(prefix="/coach", tags=["coaching"])

# LLM calls cost money and time; keep a firm ceiling per learner.
coaching_limit = RateLimit(limit=60, window_seconds=3600, name="coaching")
lesson_limit = RateLimit(limit=20, window_seconds=3600, name="lesson")


@router.post("/explain", response_model=CoachingText)
def explain(
    payload: ExplainRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(coaching_limit),
) -> CoachingText:
    game = db.get(Game, payload.game_id)
    if game is None or game.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found.")

    move = db.scalar(
        select(AnalyzedMove).where(AnalyzedMove.game_id == game.id, AnalyzedMove.ply == payload.ply)
    )
    if move is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That move has not been reviewed yet.")

    response = service.explain_move(db, user, move)
    db.commit()
    return CoachingText(
        text=response.text,
        source=response.source,
        language=response.language,
        requested_language=response.requested_language,
        language_fallback=response.language_fallback,
        notes=response.notes,
    )


def _lesson_out(lesson: Lesson) -> LessonOut:
    body = service.lesson_body(lesson)
    check = body.get("check")
    return LessonOut(
        id=lesson.id,
        topic=lesson.topic,
        topic_label=taxonomy_label(lesson.topic),
        title=body.get("title", taxonomy_label(lesson.topic)),
        language=lesson.language,
        intro=body.get("intro", ""),
        source=body.get("source", "template"),
        opening=body.get("opening", ""),
        sections=body.get("sections", []),
        examples=body.get("examples", []),
        # The answer never leaves the server before the student has tried.
        check={"fen": check["fen"], "question": check.get("question", ""), "hint": check.get("hint", "")}
        if check
        else None,
        passed=lesson.passed,
        score=lesson.score,
    )


@router.post("/lessons", response_model=LessonOut, status_code=status.HTTP_201_CREATED)
def create_lesson(
    payload: LessonRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(lesson_limit),
) -> LessonOut:
    if payload.taxonomy_key not in TAXONOMY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown lesson topic.")
    try:
        lesson = service.create_lesson(db, user, payload.taxonomy_key)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return _lesson_out(lesson)


@router.get("/lessons", response_model=list[LessonOut])
def list_lessons(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[LessonOut]:
    lessons = db.scalars(select(Lesson).where(Lesson.user_id == user.id).order_by(Lesson.id.desc())).all()
    return [_lesson_out(lesson) for lesson in lessons]


def _owned_lesson(lesson_id: int, user: User, db: Session) -> Lesson:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None or lesson.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found.")
    return lesson


@router.get("/lessons/{lesson_id}", response_model=LessonOut)
def get_lesson(lesson_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> LessonOut:
    return _lesson_out(_owned_lesson(lesson_id, user, db))


@router.post("/lessons/{lesson_id}/check", response_model=CheckResult)
def answer_check(
    lesson_id: int,
    payload: CheckAnswer,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(coaching_limit),
) -> CheckResult:
    lesson = _owned_lesson(lesson_id, user, db)
    try:
        result = service.grade_lesson_check(db, user, lesson, payload.answer)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    return CheckResult(**result)


@router.post("/chat", response_model=CoachingText)
def coach_chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _limit: None = Depends(coaching_limit),
) -> CoachingText:
    response = service.chat(db, user, payload.message)
    db.commit()
    return CoachingText(
        text=response.text,
        source=response.source,
        language=response.language,
        requested_language=response.requested_language,
        language_fallback=response.language_fallback,
        notes=response.notes,
    )
