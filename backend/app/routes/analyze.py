from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import update as _sa_update
import logging
from datetime import datetime, timedelta

from app.database import get_db
from app.models.user import User
from app.models.music import (
    Music,
    SOURCE_SPOTIFY,
    ANALYSIS_STATUS_ANALYZING,
    ANALYSIS_STATUS_PENDING,
)
from app.models.audio_features import AudioFeatures
from app.schemas.audio_features import AudioFeaturesResponse
from app.utils.auth import get_current_active_user
from app.utils.slug import resolve_music
from app.services.audio_analyzer import run_analysis as run_audio_analysis

router = APIRouter(prefix="/api/analyze", tags=["analysis"])
logger = logging.getLogger(__name__)


@router.post("/{id_or_slug}", response_model=AudioFeaturesResponse)
async def analyze_music(
    id_or_slug: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Manually trigger (or retry) audio analysis for a track by ID or slug.

    This endpoint is what powers the "Analyze" button on the dashboard.
    After upload, the same logic runs as a BackgroundTask — this route
    exists for retries (e.g. when a previous attempt landed in the
    ``error`` state).

    The actual work is delegated to ``services.audio_analyzer.run_analysis``
    so upload and manual retries share the exact same code path.
    """
    # 1. Authorization (404 before 403 — standard REST).  Accepts either a
    #    numeric ID or a per-user slug.
    music = resolve_music(db, current_user, id_or_slug)

    # 2. Catalog tracks (e.g. Spotify) already carry features from the
    #    source API — there is no local file to analyze.  Refuse the
    #    request with a clear message instead of failing on a missing
    #    ``file_path`` deep inside librosa.
    if music.source == SOURCE_SPOTIFY:
        # If a Spotify track is stuck in analyzing (e.g. from an aborted background task)
        # but already has its base features, we can recover it by marking it ready.
        if music.analysis_status == "analyzing" and music.audio_features:
            music.analysis_status = "ready"
            db.commit()
            return music.audio_features
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This track's features come from the source catalog; "
                   "local re-analysis is not available.",
        )

    # 3. Delegate.  We do this synchronously in the request (so the
    # caller gets the AudioFeatures back in the response).  The
    # background-task path is used by the upload route for the common
    # case of fresh uploads.
    success = run_audio_analysis(music.id)

    if not success:
        # Re-fetch in case the runner just wrote an error message we
        # want to surface.
        db.refresh(music)
        detail = "Audio analysis failed"
        if music.analysis_error:
            detail = f"Audio analysis failed: {music.analysis_error}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )

    features = (
        db.query(AudioFeatures)
        .filter(AudioFeatures.music_id == music.id)
        .first()
    )
    if not features:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis reported success but no features were saved",
        )
    return features


@router.get("/features/{id_or_slug}", response_model=AudioFeaturesResponse)
def get_audio_features(
    id_or_slug: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get audio features for a music track by ID or slug.

    Returns audio features if the track has been analyzed.
    """
    # Get music record + enforce ownership (404 before 403).
    music = resolve_music(db, current_user, id_or_slug)

    # Get features
    features = db.query(AudioFeatures).filter(
        AudioFeatures.music_id == music.id
    ).first()

    if not features:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio features not found. Run analysis first."
        )

    return features


@router.post("/recover", response_model=dict)
def recover_stuck_analysis(
    max_age_seconds: int = 300,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Re-run analysis for tracks left stuck in ``analyzing``."""
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
    stuck = (
        db.query(Music)
        .filter(
            Music.user_id == current_user.id,
            Music.analysis_status == ANALYSIS_STATUS_ANALYZING,
            Music.updated_at < cutoff,
        )
        .all()
    )
    recovered = 0
    for music in stuck:
        logger.info(
            "recover: resetting stuck track music_id=%s (analyzing since before %s)",
            music.id, cutoff.isoformat(),
        )
        music.analysis_status = ANALYSIS_STATUS_PENDING
        music.analysis_error = None
        db.commit()
        try:
            run_audio_analysis(music.id)
            recovered += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("recover: analysis failed for music_id=%s", music.id)
    return {"checked": len(stuck), "recovered": recovered}
