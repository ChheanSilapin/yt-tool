"""
Subtitle Service
Orchestrates transcription + subtitle creation + burning for videos.
"""

import os
import shutil
import subprocess
import tempfile
import uuid
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# FFmpeg setup
import static_ffmpeg
static_ffmpeg.add_paths()

# Import modules
from transcribe_video import transcribe_video
from create_subtitle import create_ass_file


def burn_subtitles(video_path: str, ass_path: str, output_path: str, crf: int = 18):
    """
    Burn ASS subtitles into video using FFmpeg.
    
    Args:
        video_path: Input video path
        ass_path: ASS subtitle file path
        output_path: Output video path
        crf: Quality (18 = visually lossless, lower = better)
    """
    logger.info(f"Burning subtitles into: {output_path}")
    
    # Get just the filename for the ASS file to avoid path issues
    ass_filename = os.path.basename(ass_path)
    ass_dir = os.path.dirname(ass_path)
    
    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vf', f"subtitles={ass_filename}",
        '-c:v', 'libx264',
        '-crf', str(crf),
        '-preset', 'medium',
        '-c:a', 'copy',
        output_path
    ]
    
    # Run from the ASS file directory so relative path works
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ass_dir)
    
    if result.returncode != 0:
        logger.error(f"FFmpeg stderr: {result.stderr}")
        raise Exception(f"FFmpeg failed: {result.stderr}")
    
    logger.info(f"Output saved: {output_path}")


def process_single_video(
    input_path,
    output_path,
    model_size: str = "medium",
    language: str = None,
    vad_filter: bool = True,
    highlight_color: str = "&H0000FFFF"
) -> bool:
    """
    Process a single video: transcribe + create subtitles + burn.
    
    Args:
        input_path: Input video path
        output_path: Output video path
        model_size: Whisper model size
        language: Force language (e.g., "en") or None for auto
        vad_filter: Enable VAD to skip silence/music
        highlight_color: ASS color for highlight background
    
    Returns:
        True if successful, False otherwise
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    # Use temp directory with safe ASCII names to avoid emoji issues
    temp_dir = Path(tempfile.gettempdir()) / "subtitle_service"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    temp_id = str(uuid.uuid4())[:8]
    temp_input = temp_dir / f"{temp_id}_input{input_path.suffix}"
    temp_ass = temp_dir / f"{temp_id}.ass"
    temp_output = temp_dir / f"{temp_id}_output{input_path.suffix}"
    
    try:
        # Copy input to temp (safe path)
        shutil.copy2(input_path, temp_input)
        
        # Transcribe with VAD
        words = transcribe_video(
            str(temp_input),
            model_size=model_size,
            language=language,
            vad_filter=vad_filter
        )
        
        # Create subtitles
        create_ass_file(
            words,
            str(temp_ass),
            highlight_color=highlight_color
        )
        
        # Burn subtitles
        burn_subtitles(str(temp_input), str(temp_ass), str(temp_output))
        
        # Copy output back to original location
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temp_output, output_path)
        
        return True
    except Exception as e:
        logger.error(f"Error processing {input_path}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup temp files
        for f in [temp_input, temp_ass, temp_output]:
            if f.exists():
                f.unlink()


def process_folder(input_folder, output_folder, **kwargs):
    """Process all videos in a folder."""
    input_folder = Path(input_folder)
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    
    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm'}
    videos = [f for f in input_folder.iterdir() if f.suffix.lower() in video_extensions]
    
    if not videos:
        logger.warning(f"No videos found in {input_folder}")
        return
    
    logger.info(f"Found {len(videos)} videos")
    
    for i, video in enumerate(videos, 1):
        logger.info(f"[{i}/{len(videos)}] Processing: {video.name}")
        output_path = output_folder / video.name
        process_single_video(video, output_path, **kwargs)


def main():
    """Interactive CLI for subtitle service."""
    print("\n=== Subtitle Service ===")
    print("Add styled subtitles to your videos using faster-whisper\n")
    
    # Get input
    input_path = input("Enter input (video file or folder): ").strip()
    if not input_path:
        print("Error: No input provided")
        return
    
    input_path = Path(input_path)
    if not input_path.exists():
        print(f"Error: '{input_path}' does not exist")
        return
    
    # Get output
    if input_path.is_file():
        default_output_dir = input_path.parent
        output_dir = input(f"Enter output directory [{default_output_dir}]: ").strip()
        output_dir = Path(output_dir) if output_dir else default_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / input_path.name
        
        print(f"\nProcessing: {input_path}")
        print(f"Output: {output_path}")
        process_single_video(input_path, output_path)
    else:
        default_output = input_path / "output"
        output_path = input(f"Enter output folder [{default_output}]: ").strip()
        output_path = Path(output_path) if output_path else default_output
        
        process_folder(input_path, output_path)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
