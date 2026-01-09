"""
Transcribe Video Module
Uses faster-whisper with VAD filtering for accurate speech-to-text.
"""

import logging

logger = logging.getLogger(__name__)

# Global model cache (load once, reuse)
_model = None
_model_size = None


def get_model(model_size: str = "medium"):
    """Get or create Whisper model (cached)."""
    global _model, _model_size
    
    if _model is not None and _model_size == model_size:
        return _model
    
    from faster_whisper import WhisperModel
    
    logger.info(f"Loading faster-whisper model: {model_size}")
    
    # Try GPU first, fall back to CPU
    try:
        _model = WhisperModel(model_size, device="cuda", compute_type="float16")
        logger.info("Using GPU (CUDA)")
    except Exception:
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info("Using CPU")
    
    _model_size = model_size
    return _model


def transcribe_video(
    video_path: str,
    model_size: str = "medium",
    language: str = None,
    vad_filter: bool = True,
    min_silence_duration_ms: int = 500
) -> list[dict]:
    """
    Transcribe video/audio using faster-whisper.
    
    Args:
        video_path: Path to video/audio file
        model_size: Whisper model size (tiny, base, small, medium, large-v3, distil-large-v3)
        language: Force specific language (e.g., "en") or None for auto-detect
        vad_filter: Enable Voice Activity Detection to skip silence/music
        min_silence_duration_ms: Minimum silence duration to skip (ms)
    
    Returns:
        List of word dictionaries with 'word', 'start', 'end' keys
    """
    model = get_model(model_size)
    
    logger.info(f"Transcribing: {video_path}")
    
    # Transcribe with VAD and word timestamps
    transcribe_opts = {
        "word_timestamps": True,
        "vad_filter": vad_filter,
    }
    
    if vad_filter:
        transcribe_opts["vad_parameters"] = {
            "min_silence_duration_ms": min_silence_duration_ms
        }
    
    if language:
        transcribe_opts["language"] = language
    
    segments, info = model.transcribe(video_path, **transcribe_opts)
    
    logger.info(f"Detected language '{info.language}' with probability {info.language_probability:.2f}")
    
    # Extract words from segments
    words = []
    for segment in segments:
        if segment.words:
            for word in segment.words:
                words.append({
                    'word': word.word,
                    'start': word.start,
                    'end': word.end
                })
    
    logger.info(f"Transcribed {len(words)} words")
    return words
