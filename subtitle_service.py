"""
Subtitle Service CLI
Fast subtitle generation using faster-whisper with viral styling.
"""

import os
import sys
import logging
import random
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# FFmpeg setup
import static_ffmpeg
static_ffmpeg.add_paths()
import ffmpeg


def format_time_ass(seconds):
    """Format time for ASS subtitles (h:mm:ss.cc)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def create_ass_file(words, filename="captions.ass"):
    """Create ASS subtitle file with karaoke-style word-by-word highlighting.
    
    Shows 2-3 words at a time, with yellow background highlight moving
    from word to word as each is spoken.
    """
    # Colors in ASS format (BGR with alpha: &HAABBGGRR)
    white_color = "&H00FFFFFF"
    black_outline = "&H00000000"
    yellow_bg = "&H00FFFF00"  # Yellow (cyan in RGB order: 00 blue, FF green, FF red)

    with open(filename, "w", encoding="utf-8") as f:
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n")
        f.write("PlayResX: 1080\n")
        f.write("PlayResY: 1920\n")
        f.write("\n")
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        # Default style: white text with black outline (BorderStyle 1)
        f.write(f"Style: Default,Poppins,80,{white_color},{white_color},{black_outline},{black_outline},-1,0,1,3,0,2,10,10,600,1\n")
        # Highlight style: white text with yellow box background (BorderStyle 3 = opaque box)
        f.write(f"Style: Highlight,Poppins,80,{white_color},{white_color},{yellow_bg},{yellow_bg},-1,0,3,8,0,2,10,10,600,1\n")
        f.write("\n")
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        if not words:
            return filename

        # Chunk words into groups of 2-3
        i = 0
        chunks = []
        while i < len(words):
            chunk_size = random.randint(2, 3)
            chunk = words[i:i + chunk_size]
            if chunk:
                chunks.append(chunk)
            i += chunk_size

        # Create karaoke-style dialogue events
        for chunk in chunks:
            for highlight_idx, highlighted_word in enumerate(chunk):
                start_time = highlighted_word['start']
                end_time = highlighted_word['end']
                start_str = format_time_ass(start_time)
                end_str = format_time_ass(end_time)

                # Build text with current word having yellow background using style override
                text_parts = []
                for idx, word_info in enumerate(chunk):
                    word_text = word_info['word'].strip().upper()
                    if idx == highlight_idx:
                        # Switch to Highlight style (yellow box background)
                        text_parts.append(f"{{\\rHighlight}}{word_text}{{\\rDefault}}")
                    else:
                        # Normal white text
                        text_parts.append(f"{word_text}")
                
                text_content = " ".join(text_parts)
                f.write(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text_content}\n")

    logger.info(f"Created subtitle file: {filename}")
    return filename


def transcribe_video(video_path, model_size="medium"):
    """Transcribe video using faster-whisper."""
    from faster_whisper import WhisperModel
    
    logger.info(f"Loading faster-whisper model: {model_size}")
    
    # Try GPU first, fall back to CPU
    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
        logger.info("Using GPU (CUDA)")
    except Exception:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info("Using CPU")

    logger.info(f"Transcribing: {video_path}")
    segments, info = model.transcribe(video_path, word_timestamps=True)
    
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


import subprocess

def burn_subtitles(video_path, ass_path, output_path):
    """Burn ASS subtitles into video using FFmpeg (subprocess)."""
    logger.info(f"Burning subtitles into: {output_path}")
    
    # Get just the filename for the ASS file to avoid path issues
    ass_filename = os.path.basename(ass_path)
    ass_dir = os.path.dirname(ass_path)
    
    # Use subtitles filter with relative path (change to temp dir)
    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vf', f"subtitles={ass_filename}",
        '-c:v', 'libx264',
        '-c:a', 'copy',
        output_path
    ]
    
    # Run from the ASS file directory so relative path works
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ass_dir)
    
    if result.returncode != 0:
        logger.error(f"FFmpeg stderr: {result.stderr}")
        raise Exception(f"FFmpeg failed: {result.stderr}")
    
    logger.info(f"Output saved: {output_path}")


import shutil
import uuid
import tempfile

def process_single_video(input_path, output_path):
    """Process a single video: transcribe + burn subtitles."""
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
        
        # Transcribe
        words = transcribe_video(str(temp_input))
        
        # Create subtitles
        create_ass_file(words, str(temp_ass))
        
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


def process_folder(input_folder, output_folder):
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
        output_path = output_folder / f"{video.stem}_subtitled{video.suffix}"
        process_single_video(video, output_path)


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
        
        output_path = output_dir / f"{input_path.stem}_subtitled{input_path.suffix}"
        
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
