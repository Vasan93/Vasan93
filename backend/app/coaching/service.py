"""Coaching workflows: assemble facts, ask the brain for language, verify, record."""
from __future__ import annotations

import json
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coaching.brain import BrainError, CoachingResponse, LearnerContext, get_brain
from app.coaching.prompts import v1
from app.coaching.transcript import record
from app.coaching.validation import grade_answer, ground_answer, legal_position, validate_lesson
from app.core.logging import get_logger
from app.engines import boardlib as bl
from app.engines.stockfish import get_analysis_engine
from app.models import AnalyzedMove, Game, Lesson, User
from app.weakness.service import load_profile
from app.weakness.taxonomy import TAXONOMY, label as taxonomy_label

log = get_logger(__name__)

import chess


def learner_context(db: Session, user: User, weakness_limit: int = 4) -> LearnerContext:
    profile = load_profile(db, user.id)
    active = sorted(
        (score for score in profile.values() if score.status in ("active", "improving")),
        key=lambda score: -score.confidence,
    )[:weakness_limit]
    return LearnerContext(
        name=user.display_name,
        language=user.preferred_language,
        rating=user.current_rating_estimate,
        goal=user.goal,
        weaknesses=[taxonomy_label(score.taxonomy_key) for score in active],
    )


def log_exchange(db: Session, user: User, kind: str, response: CoachingResponse, notes: str = "") -> None:
    """Record one coaching exchange for later quality review."""
    record(
        db,
        user_id=user.id,
        kind=kind,
        system_prompt=response.system_prompt,
        user_prompt=response.user_prompt,
        response=response.text,
        source=response.source,
        model=response.model,
        language=response.language,
        prompt_version=response.prompt_version,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_ms=response.latency_ms,
        guardrail_notes=notes,
    )


# ------------------------------------------------------------ mistake explanation
def explain_move(db: Session, user: User, move: AnalyzedMove) -> CoachingResponse:
    """Explain one reviewed move in the learner's language."""
    phase = "middlegame"
    if legal_position(move.fen):
        phase = bl.game_phase(chess.Board(move.fen))

    facts = {
        "fen": move.fen,
        "played_move": move.played_move,
        "best_move": move.best_move,
        "best_line": move.best_line.split() if move.best_line else [],
        "cp_loss": move.cp_loss,
        "eval_cp_before": move.eval_cp_before,
        "eval_cp_after": move.eval_cp_after,
        "detected_motif": move.detected_motif,
        "phase": phase,
    }
    learner = learner_context(db, user)
    brain = get_brain()
    try:
        response = brain.explain_mistake(learner, facts)
    except BrainError as exc:
        log.warning("Coaching brain failed, falling back to template: %s", exc)
        from app.coaching.brain import TemplateBrain

        response = TemplateBrain().explain_mistake(learner, facts)
        response.notes.append(str(exc))
    log_exchange(db, user, "mistake", response)
    return response


# ------------------------------------------------------------------- lessons
def _own_mistake_positions(db: Session, user: User, taxonomy_key: str, limit: int = 3) -> list[AnalyzedMove]:
    """The learner's own mistakes of this kind. The best teaching material there is."""
    rows = db.scalars(
        select(AnalyzedMove)
        .join(Game, Game.id == AnalyzedMove.game_id)
        .where(Game.user_id == user.id)
        .where(AnalyzedMove.taxonomy_keys.contains(taxonomy_key))
        .order_by(AnalyzedMove.cp_loss.desc())
        .limit(limit)
    ).all()
    return list(rows)


def _lesson_from_own_games(db: Session, user: User, taxonomy_key: str) -> dict | None:
    """Build a lesson body without an LLM, using the learner's own positions."""
    entry = TAXONOMY[taxonomy_key]
    examples = []
    for move in _own_mistake_positions(db, user, taxonomy_key, limit=2):
        examples.append(
            {
                "fen": move.fen,
                "move": move.best_move,
                "explanation": (
                    f"You played {move.played_move} here. {move.best_move} was the move, and this is exactly "
                    f"the pattern we are working on."
                ),
                "from_your_game": True,
            }
        )
    if not examples:
        return None

    check_source = examples[0]
    return {
        "title": entry.teaching_topic,
        "opening": f"{entry.description} Here it is in your own games.",
        "sections": [
            {"heading": entry.label, "body": entry.description},
            {"heading": "What to do instead", "body": f"Focus on this: {entry.teaching_topic}."},
        ],
        "examples": examples,
        "check": {
            "fen": check_source["fen"],
            "question": "This position came from your own game. Find the move you missed.",
            "answer": check_source["move"],
            "hint": entry.teaching_topic,
        },
    }


def create_lesson(db: Session, user: User, taxonomy_key: str, reason: str = "") -> Lesson:
    """Generate, verify and store a lesson on one weakness."""
    if taxonomy_key not in TAXONOMY:
        raise ValueError(f"Unknown topic: {taxonomy_key}")

    entry = TAXONOMY[taxonomy_key]
    learner = learner_context(db, user)
    reason = reason or f"This has come up repeatedly in their games ({entry.label})."
    engine = get_analysis_engine()
    brain = get_brain()
    notes: list[str] = []

    body: dict | None = None
    response: CoachingResponse
    try:
        response = brain.build_lesson(learner, entry.teaching_topic, reason)
        body = response.structured
    except BrainError as exc:
        log.warning("Lesson generation failed: %s", exc)
        from app.coaching.brain import TemplateBrain

        response = TemplateBrain().build_lesson(learner, entry.teaching_topic, reason)
        notes.append(str(exc))

    if body:
        body, report = validate_lesson(body, engine)
        notes.extend(report.problems)
        if not report.ok:
            notes.append("Generated lesson failed verification; used the learner's own positions instead.")
            body = None

    if body is None:
        body = _lesson_from_own_games(db, user, taxonomy_key)
        if body is None:
            raise ValueError(
                "There is not enough material for this lesson yet. Review a game containing this mistake first."
            )
        grounded = ground_answer(engine, body["check"]["fen"], body["check"]["answer"])
        if grounded is None:
            raise ValueError("The example position could not be verified.")
        body["check"]["answer"] = grounded.answer_san
        body["check"]["answer_uci"] = grounded.answer_uci

    lesson = Lesson(
        user_id=user.id,
        topic=taxonomy_key,
        language=response.language,
        transcript=json.dumps({**body, "intro": response.text, "source": response.source}),
        comprehension_checks=json.dumps([body["check"]]),
    )
    db.add(lesson)
    db.flush()
    log_exchange(db, user, "lesson", response, notes="; ".join(notes))
    return lesson


def lesson_body(lesson: Lesson) -> dict:
    return json.loads(lesson.transcript)


def grade_lesson_check(db: Session, user: User, lesson: Lesson, student_answer: str) -> dict:
    """Grade against the engine, then ask the brain only for the wording."""
    checks = json.loads(lesson.comprehension_checks or "[]")
    if not checks:
        raise ValueError("This lesson has no comprehension check.")
    check = checks[0]
    engine = get_analysis_engine()

    try:
        correct, best_move, cp_loss = grade_answer(engine, check["fen"], student_answer)
    except ValueError as exc:
        raise ValueError(f"That is not a legal move here: {exc}") from exc

    learner = learner_context(db, user)
    facts = {
        "fen": check["fen"],
        "question": check.get("question", ""),
        "answer": check["answer"],
        "student_answer": student_answer,
        "correct": correct,
        "engine_note": (
            "" if correct else f"The engine's move is {best_move}; the student's move loses {cp_loss} centipawns."
        ),
    }
    brain = get_brain()
    try:
        response = brain.check_feedback(learner, facts)
    except BrainError as exc:
        from app.coaching.brain import TemplateBrain

        response = TemplateBrain().check_feedback(learner, facts)
        response.notes.append(str(exc))

    lesson.score = 1.0 if correct else 0.0
    lesson.passed = correct
    db.flush()
    log_exchange(db, user, "check", response)

    return {
        "correct": correct,
        "best_move": best_move,
        "cp_loss": cp_loss,
        "feedback": response.text,
        "source": response.source,
        "language_fallback": response.language_fallback,
    }


# ---------------------------------------------------------------------- chat
def chat(db: Session, user: User, message: str, history: list[dict[str, str]] | None = None) -> CoachingResponse:
    learner = learner_context(db, user)
    brain = get_brain()
    try:
        response = brain.chat(learner, message, history or [])
    except BrainError as exc:
        from app.coaching.brain import TemplateBrain

        response = TemplateBrain().chat(learner, message, history or [])
        response.notes.append(str(exc))
    log_exchange(db, user, "chat", response)
    return response


def summarise_assessment(db: Session, user: User, facts: dict) -> CoachingResponse:
    learner = learner_context(db, user)
    brain = get_brain()
    try:
        response = brain.assessment_summary(learner, facts)
    except BrainError as exc:
        from app.coaching.brain import TemplateBrain

        response = TemplateBrain().assessment_summary(learner, facts)
        response.notes.append(str(exc))
    log_exchange(db, user, "summary", response)
    return response


def response_payload(response: CoachingResponse) -> dict:
    data = asdict(response)
    # The prompt itself is for the transcript, not for the client.
    data.pop("system_prompt", None)
    data.pop("user_prompt", None)
    return data


__all__ = [
    "chat",
    "log_exchange",
    "create_lesson",
    "explain_move",
    "grade_lesson_check",
    "learner_context",
    "lesson_body",
    "response_payload",
    "summarise_assessment",
    "v1",
]
