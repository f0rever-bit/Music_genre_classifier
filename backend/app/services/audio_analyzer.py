import librosa
import numpy as np
from typing import Dict, Optional
import logging
from concurrent.futures import ThreadPoolExecutor

from app.database import SessionLocal, get_settings
from app.models.audio_features import AudioFeatures
from app.models.music import (
    Music,
    SOURCE_LOCAL,
    ANALYSIS_STATUS_ANALYZING,
    ANALYSIS_STATUS_READY,
    ANALYSIS_STATUS_ERROR,
)
from app.utils.audio_utils import compute_perceptual_fingerprint
from app.services.storage import get_storage

settings = get_settings()

logger = logging.getLogger(__name__)


def run_analysis(music_id: int) -> bool:
    """
    Analyze a single track and persist the result.

    Designed to be called from FastAPI's ``BackgroundTasks`` AFTER the
    upload response is sent.  Opens its own DB session so it is fully
    decoupled from the request lifecycle.

    Updates ``Music.analysis_status`` as it goes:
        pending  → analyzing → ready  (on success)
        pending  → analyzing → error  (on failure; ``analysis_error`` set)

    Returns True on success, False on failure.  Never raises — failures
    are persisted to the DB so the frontend can show the user what
    went wrong.
    """
    db = SessionLocal()
    db.expire_on_commit = False
    try:
        logger.info("run_analysis: starting for music_id=%s", music_id)
        music = db.query(Music).filter(Music.id == music_id).first()
        if music is None:
            logger.warning("run_analysis: music_id=%s not found", music_id)
            return False

        # Idempotency: if we already have features, nothing to do.
        if music.audio_features is not None:
            music.analysis_status = ANALYSIS_STATUS_READY
            db.commit()
            logger.info("run_analysis: music_id=%s already has features, skipping", music_id)
            return True

        music.analysis_status = ANALYSIS_STATUS_ANALYZING
        music.analysis_error = None
        db.commit()
        logger.info("run_analysis: music_id=%s status set to analyzing", music_id)

        try:
            if not music.file_path:
                raise FileNotFoundError(
                    "file_path is None — file may have been purged; re-upload required"
                )
            analyzer = AudioAnalyzer()
            local_path = get_storage().get_local_path(music.file_path)
            logger.info("run_analysis: music_id=%s resolved local_path=%s", music_id, local_path)
            features = _analyze_with_timeout(analyzer, local_path)
            valence = analyzer.estimate_valence(features)
            if valence is not None:
                features["valence"] = valence

            audio_features = AudioFeatures(
                music_id=music_id,
                tempo=features.get("tempo"),
                duration=features.get("duration"),
                key=features.get("key"),
                mode=features.get("mode"),
                loudness=features.get("loudness"),
                energy=features.get("energy"),
                valence=features.get("valence"),
                spectral_centroid_mean=features.get("spectral_centroid_mean"),
                spectral_centroid_std=features.get("spectral_centroid_std"),
                spectral_bandwidth_mean=features.get("spectral_bandwidth_mean"),
                spectral_bandwidth_std=features.get("spectral_bandwidth_std"),
                spectral_rolloff_mean=features.get("spectral_rolloff_mean"),
                spectral_rolloff_std=features.get("spectral_rolloff_std"),
                mfcc_mean=features.get("mfcc_mean"),
                mfcc_std=features.get("mfcc_std"),
                zero_crossing_rate_mean=features.get("zero_crossing_rate_mean"),
                zero_crossing_rate_std=features.get("zero_crossing_rate_std"),
                chroma_stft_mean=features.get("chroma_stft_mean"),
                chroma_stft_std=features.get("chroma_stft_std"),
                perceptual_fingerprint=features.get("perceptual_fingerprint"),
            )

            if music.duration is None and features.get("duration"):
                music.duration = features["duration"]

            db.add(audio_features)
            music.analysis_status = ANALYSIS_STATUS_READY
            db.commit()

            # Best-effort K-Means auto-retrain — same hook used by the
            # manual /analyze route.  Failures must not bubble up here
            # because the analyze itself was successful.
            try:
                from app.services.ml_recommender import MLRecommender
                recommender = MLRecommender()
                recommender.load_models()
                recommender.auto_retrain_if_needed(db)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Auto-retrain after background analysis failed: %s", str(e)
                )

            logger.info(
                "Background analysis complete for music_id=%s (tempo=%s)",
                music_id, features.get("tempo"),
            )
            _purge_local_file(music, db)
            return True

        except Exception as e:  # noqa: BLE001
            logger.exception("Background analysis failed for music_id=%s", music_id)
            music.analysis_status = ANALYSIS_STATUS_ERROR
            # Truncate the error message so a malformed 50MB file does
            # not pollute the database.
            music.analysis_error = (str(e) or type(e).__name__)[:500]
            db.commit()
            # Keep the file on failure so the user can retry via
            # POST /api/analyze/{id} or the "Analyze" button.
            return False

    finally:
        db.close()


def _analyze_with_timeout(analyzer: "AudioAnalyzer", path: str, timeout: int = 120) -> Dict:
    """Run feature extraction with a wall-clock timeout.

    On cloud hosts ``librosa.load`` has occasionally been seen to hang with no
    Python traceback (decoder/OOM).  Running it in a worker thread lets us
    abort the *wait* after ``timeout`` so the track is recorded as 'error'
    instead of being stranded in 'analyzing' forever.  (The underlying thread
    may keep running until it unblocks, but it no longer blocks the request
    lifecycle or leaves the DB in a stuck state.)
    """
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(analyzer.analyze, path)
        try:
            return fut.result(timeout=timeout)
        except TimeoutError:
            logger.error(
                "run_analysis: analysis timed out after %ss for %s", timeout, path
            )
            raise TimeoutError(
                f"Audio analysis exceeded the {timeout}s limit (likely a decoder "
                f"hang or out-of-memory in the audio backend)."
            )


def _purge_local_file(music: Music, db) -> None:
    """Delete the uploaded file from storage once it's no longer needed.

    Only applies to ``source='local'`` tracks when ``DELETE_LOCAL_AFTER_ANALYZE``
    is enabled (free-hosting friendly: we keep only the features).  Catalog
    tracks have no file and are skipped.  Failures are logged, never raised.
    """
    if not settings.delete_local_after_analyze:
        return
    if music.source != SOURCE_LOCAL or not music.file_path:
        return
    try:
        get_storage().delete(music.file_path)
        music.file_path = None
        db.commit()
        logger.info("Purged local file for music_id=%s", music.id)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Failed to purge local file for music_id=%s: %s", music.id, str(e)
        )


class AudioAnalyzer:
    """
    Audio analysis service using librosa for feature extraction.

    Extracts various audio features including:
    - Temporal: tempo, duration
    - Tonal: key, mode
    - Energy: loudness, energy
    - Mood: valence
    - Spectral: centroid, bandwidth, rolloff
    - Timbre: MFCCs
    - Rhythm: zero-crossing rate
    - Harmony: chroma features
    """

    def __init__(self, sr: int = 22050, n_mfcc: int = 20):
        """
        Initialize AudioAnalyzer.

        Args:
            sr: Sample rate for audio loading (default: 22050 Hz)
            n_mfcc: Number of MFCC coefficients to extract (default: 20)
        """
        self.sr = sr
        self.n_mfcc = n_mfcc

    def analyze(self, file_path: str) -> Dict:
        """
        Analyze an audio file and extract all features.

        Args:
            file_path: Path to the audio file

        Returns:
            Dictionary containing all extracted features

        Raises:
            Exception: If audio file cannot be loaded or analyzed
        """
        try:
            import warnings
            import soundfile as sf
            import time as _time

            _t0 = _time.monotonic()
            logger.info("analyze: loading file=%s", file_path)

            # Get actual duration before clipping the load
            # Use soundfile directly instead of librosa.get_duration(path=...)
            # because librosa falls back to audioread which decodes the entire
            # file into memory just to find the length, causing OOMs on 512MB RAM!
            actual_duration = None
            try:
                info = sf.info(file_path)
                actual_duration = info.duration
                logger.info("analyze: sf.info ok duration=%.2fs", actual_duration)
            except Exception as e:
                logger.warning("Could not get actual duration from path: %s", e)

            # Load audio file (max 45 seconds to prevent OOM on free-tier hosting).
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                logger.info("analyze: calling librosa.load (sr=%s, duration=45.0)", self.sr)
                y, sr = librosa.load(file_path, sr=self.sr, duration=45.0)
            logger.info(
                "analyze: librosa.load done in %.2fs (samples=%d, sr=%d)",
                _time.monotonic() - _t0, len(y), sr,
            )

            # Precompute spectrogram once to save CPU and Memory.
            # Doing this prevents each librosa.feature.* call from re-running STFT
            # which caused multiple allocations of large complex matrices.
            logger.info("analyze: computing STFT")
            S = np.abs(librosa.stft(y))**2
            logger.info("analyze: STFT done in %.2fs", _time.monotonic() - _t0)

            # Extract all features
            features = {
                **self._extract_temporal_features(y, sr),
                **self._extract_tonal_features(y, sr, S=S),
                **self._extract_energy_features(y, sr),
                **self._extract_spectral_features(y, sr, S=S),
                **self._extract_timbre_features(y, sr),
                **self._extract_rhythm_features(y, sr),
                **self._extract_harmony_features(y, sr, S=S),
            }
            logger.info("analyze: feature extraction done in %.2fs", _time.monotonic() - _t0)

            # Override with actual duration
            if actual_duration:
                features["duration"] = float(actual_duration)

            fingerprint = compute_perceptual_fingerprint(y, sr)
            features["perceptual_fingerprint"] = fingerprint
            logger.info("analyze: fingerprint done in %.2fs", _time.monotonic() - _t0)

            return features

        except Exception as e:
            logger.error(f"Error analyzing audio file {file_path}: {str(e)}")
            raise

    def _extract_temporal_features(self, y: np.ndarray, sr: int) -> Dict:
        """Extract tempo and duration."""
        try:
            # Tempo detection
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

            # Duration in seconds
            duration = librosa.get_duration(y=y, sr=sr)

            return {
                "tempo": float(tempo),
                "duration": float(duration)
            }
        except Exception as e:
            logger.warning(f"Error extracting temporal features: {str(e)}")
            return {"tempo": None, "duration": None}

    def _extract_tonal_features(self, y: np.ndarray, sr: int, S: Optional[np.ndarray] = None) -> Dict:
        """Extract key and mode."""
        try:
            # Compute chromagram
            chroma = librosa.feature.chroma_stft(y=y, sr=sr, S=S)

            # Get the most prominent pitch class
            key = int(np.argmax(np.sum(chroma, axis=1)))

            # Estimate mode (major=1, minor=0) based on chord structure
            # Simplified approach: check if major third (4 semitones) is stronger than minor third (3 semitones)
            major_third = chroma[(key + 4) % 12].mean()
            minor_third = chroma[(key + 3) % 12].mean()
            mode = 1 if major_third > minor_third else 0

            return {
                "key": key,  # 0=C, 1=C#, 2=D, ..., 11=B
                "mode": mode  # 0=minor, 1=major
            }
        except Exception as e:
            logger.warning(f"Error extracting tonal features: {str(e)}")
            return {"key": None, "mode": None}

    def _extract_energy_features(self, y: np.ndarray, sr: int) -> Dict:
        """Extract loudness and energy."""
        try:
            rms = librosa.feature.rms(y=y)[0]
            mean_rms = float(np.mean(rms))
            max_rms = float(np.max(rms))

            loudness = float(librosa.amplitude_to_db(mean_rms, ref=max_rms))

            energy_normalized = min(mean_rms / 0.4, 1.0)

            return {
                "loudness": loudness,
                "energy": energy_normalized
            }
        except Exception as e:
            logger.warning(f"Error extracting energy features: {str(e)}")
            return {"loudness": None, "energy": None}

    def _extract_spectral_features(self, y: np.ndarray, sr: int, S: Optional[np.ndarray] = None) -> Dict:
        """Extract spectral centroid, bandwidth, and rolloff."""
        try:
            # Spectral centroid
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr, S=S)[0]

            # Spectral bandwidth
            spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr, S=S)[0]

            # Spectral rolloff
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, S=S)[0]

            return {
                "spectral_centroid_mean": float(np.mean(spectral_centroids)),
                "spectral_centroid_std": float(np.std(spectral_centroids)),
                "spectral_bandwidth_mean": float(np.mean(spectral_bandwidth)),
                "spectral_bandwidth_std": float(np.std(spectral_bandwidth)),
                "spectral_rolloff_mean": float(np.mean(spectral_rolloff)),
                "spectral_rolloff_std": float(np.std(spectral_rolloff))
            }
        except Exception as e:
            logger.warning(f"Error extracting spectral features: {str(e)}")
            return {
                "spectral_centroid_mean": None,
                "spectral_centroid_std": None,
                "spectral_bandwidth_mean": None,
                "spectral_bandwidth_std": None,
                "spectral_rolloff_mean": None,
                "spectral_rolloff_std": None
            }

    def _extract_timbre_features(self, y: np.ndarray, sr: int) -> Dict:
        """Extract MFCC (Mel-frequency cepstral coefficients) for timbre."""
        try:
            # Extract MFCCs
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=self.n_mfcc)

            # Compute mean and std for each coefficient
            mfcc_mean = np.mean(mfccs, axis=1).tolist()
            mfcc_std = np.std(mfccs, axis=1).tolist()

            return {
                "mfcc_mean": mfcc_mean,
                "mfcc_std": mfcc_std
            }
        except Exception as e:
            logger.warning(f"Error extracting timbre features: {str(e)}")
            return {"mfcc_mean": None, "mfcc_std": None}

    def _extract_rhythm_features(self, y: np.ndarray, sr: int) -> Dict:
        """Extract zero-crossing rate."""
        try:
            # Zero-crossing rate
            zcr = librosa.feature.zero_crossing_rate(y)[0]

            return {
                "zero_crossing_rate_mean": float(np.mean(zcr)),
                "zero_crossing_rate_std": float(np.std(zcr))
            }
        except Exception as e:
            logger.warning(f"Error extracting rhythm features: {str(e)}")
            return {
                "zero_crossing_rate_mean": None,
                "zero_crossing_rate_std": None
            }

    def _extract_harmony_features(self, y: np.ndarray, sr: int, S: Optional[np.ndarray] = None) -> Dict:
        """Extract chroma STFT features."""
        try:
            # Chroma STFT (12 pitch classes)
            chroma_stft = librosa.feature.chroma_stft(y=y, sr=sr, S=S)

            # Compute mean and std for each pitch class
            chroma_mean = np.mean(chroma_stft, axis=1).tolist()
            chroma_std = np.std(chroma_stft, axis=1).tolist()

            return {
                "chroma_stft_mean": chroma_mean,
                "chroma_stft_std": chroma_std
            }
        except Exception as e:
            logger.warning(f"Error extracting harmony features: {str(e)}")
            return {"chroma_stft_mean": None, "chroma_stft_std": None}

    def estimate_valence(self, features: Dict) -> Optional[float]:
        """
        Estimate valence (musical positivity) from extracted features.

        Weighted heuristic using:
        - Mode (major = more positive, weight 1.5)
        - Tempo (faster = more positive, weight 0.8)
        - Energy (higher = more positive, weight 1.2)
        - Loudness (louder = more positive, weight 0.5)
        - Spectral centroid (brighter = more positive, weight 0.4)
        - Zero-crossing rate (more texture = more positive, weight 0.3)

        Returns:
            Valence score (0.0-1.0) or None if no features available
        """
        try:
            score = 0.0
            total_weight = 0.0

            # Mode: major (1) is more positive than minor (0)  [weight 1.5]
            if features.get("mode") is not None:
                score += 1.5 * features["mode"]
                total_weight += 1.5

            # Tempo: normalise 40-200 BPM → [0, 1], clip  [weight 0.8]
            if features.get("tempo") is not None:
                tempo_n = (features["tempo"] - 40) / 160.0
                score += 0.8 * max(0.0, min(tempo_n, 1.0))
                total_weight += 0.8

            # Energy: already [0, 1]  [weight 1.2]
            if features.get("energy") is not None:
                score += 1.2 * features["energy"]
                total_weight += 1.2

            # Loudness: -60..0 dB → [0, 1]  [weight 0.5]
            if features.get("loudness") is not None:
                loud_n = (features["loudness"] + 60.0) / 60.0
                score += 0.5 * max(0.0, min(loud_n, 1.0))
                total_weight += 0.5

            # Spectral centroid: 0-8000 Hz → [0, 1]  [weight 0.4]
            if features.get("spectral_centroid_mean") is not None:
                cent_n = features["spectral_centroid_mean"] / 8000.0
                score += 0.4 * max(0.0, min(cent_n, 1.0))
                total_weight += 0.4

            # Zero-crossing rate: 0-0.5 → [0, 1]  [weight 0.3]
            if features.get("zero_crossing_rate_mean") is not None:
                zcr_n = features["zero_crossing_rate_mean"] * 2.0
                score += 0.3 * max(0.0, min(zcr_n, 1.0))
                total_weight += 0.3

            if total_weight == 0:
                return None

            return float(score / total_weight)

        except Exception as e:
            logger.warning(f"Error estimating valence: {str(e)}")
            return None
