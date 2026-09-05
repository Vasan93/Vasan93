"""Engine endpoints. These expose ground truth, never coaching language."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import RateLimit, get_current_user
from app.engines.sparring import get_sparring_engine
from app.engines.stockfish import EngineUnavailable, get_analysis_engine
from app.models import User
from app.schemas.engine import AnalysisOut, AnalyzeRequest, ClassifyRequest, SparringInfo, VerdictOut

router = APIRouter(prefix="/engine", tags=["engine"])

analysis_limit = RateLimit(limit=120, window_seconds=60, name="engine-analyze")


@router.post("/analyze", response_model=AnalysisOut)
def analyze(
    payload: AnalyzeRequest,
    _user: User = Depends(get_current_user),
    _limit: None = Depends(analysis_limit),
) -> AnalysisOut:
    try:
        result = get_analysis_engine().analyze(payload.fen, depth=payload.depth, multipv=payload.multipv)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except EngineUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return AnalysisOut.from_result(result)


@router.post("/classify", response_model=VerdictOut)
def classify(
    payload: ClassifyRequest,
    _user: User = Depends(get_current_user),
    _limit: None = Depends(analysis_limit),
) -> VerdictOut:
    try:
        verdict = get_analysis_engine().classify_move(payload.fen, payload.move, depth=payload.depth)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except EngineUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return VerdictOut.from_verdict(verdict)


@router.get("/sparring-info", response_model=SparringInfo)
def sparring_info(_user: User = Depends(get_current_user)) -> SparringInfo:
    return SparringInfo(**get_sparring_engine().describe())  # type: ignore[arg-type]
