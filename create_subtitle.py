"""
Create Subtitle Module
Generates ASS subtitle files with karaoke-style word-by-word highlighting.
"""

import logging
import random

logger = logging.getLogger(__name__)


def format_time_ass(seconds: float) -> str:
    """Format time for ASS subtitles (h:mm:ss.cc)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def clean_words(words: list[dict]) -> list[dict]:
    """
    Clean up Whisper transcription artifacts.
    
    Fixes:
    - Merge $1 + ,000 -> $1,000
    - Join words starting with punctuation to previous word
    - Remove standalone punctuation words
    
    Args:
        words: List of word dicts with 'word', 'start', 'end' keys
    
    Returns:
        Cleaned list of word dicts
    """
    if not words:
        return words
    
    cleaned = []
    punctuation_starters = {',', '.', '?', '!', ';', ':', "'"}
    
    for word_info in words:
        word = word_info['word'].strip()
        
        # Skip empty words
        if not word:
            continue
        
        # Check if word starts with punctuation (like ",000" or ".5")
        if word and word[0] in punctuation_starters:
            if cleaned:
                # Merge with previous word
                prev = cleaned[-1]
                prev['word'] = prev['word'].rstrip() + word
                prev['end'] = word_info['end']  # Extend end time
                continue
        
        # Check if previous word ends with $ and current is a number
        if cleaned and cleaned[-1]['word'].rstrip().endswith('$'):
            if word and (word[0].isdigit() or word[0] in punctuation_starters):
                prev = cleaned[-1]
                prev['word'] = prev['word'].rstrip() + word
                prev['end'] = word_info['end']
                continue
        
        cleaned.append(word_info.copy())
    
    logger.debug(f"Cleaned {len(words)} words to {len(cleaned)} words")
    return cleaned


def create_ass_file(
    words: list[dict],
    filename: str = "captions.ass",
    chunk_size_min: int = 2,
    chunk_size_max: int = 3,
    font_color: str = "&H00FFFFFF",
    outline_color: str = "&H00FF0080",
    highlight_color: str = "&H00FF0080", 
    font_name: str = "Poppins",
    font_size: int = 80,
    margin_v: int = 600
) -> str:
    """
    Create ASS subtitle file with karaoke-style word-by-word highlighting.
    
    Args:
        words: List of word dicts with 'word', 'start', 'end' keys
        filename: Output ASS file path
        chunk_size_min: Minimum words per chunk (default: 2)
        chunk_size_max: Maximum words per chunk (default: 3)
        white_color: ASS color code for normal text
        black_outline: ASS color code for outline
        highlight_color: ASS color code for highlight background
        font_name: Font family name
        font_size: Font size in pixels
        margin_v: Vertical margin from bottom
    
    Returns:
        Path to created ASS file
    """
    with open(filename, "w", encoding="utf-8") as f:
        # Script info
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n")
        f.write("PlayResX: 1080\n")
        f.write("PlayResY: 1920\n")
        f.write("\n")
        
        # Styles
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        # Default style: white text with black outline (BorderStyle 1)
        f.write(f"Style: Default,{font_name},{font_size},{font_color},{font_color},{outline_color},{outline_color},-1,0,1,2,0,2,10,10,{margin_v},1\n")
        # Highlight style: white text with colored box background (BorderStyle 3 = opaque box)
        f.write(f"Style: Highlight,{font_name},{font_size},{font_color},{font_color},{highlight_color},{highlight_color},-1,0,3,8,0,2,10,10,{margin_v},1\n")
        f.write("\n")
        
        # Events
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        if not words:
            logger.warning("No words to create subtitles from")
            return filename

        # Clean up transcription artifacts (merge split numbers, fix punctuation)
        words = clean_words(words)

        # Chunk words into groups
        i = 0
        chunks = []
        while i < len(words):
            chunk_size = random.randint(chunk_size_min, chunk_size_max)
            chunk = words[i:i + chunk_size]
            if chunk:
                chunks.append(chunk)
            i += chunk_size

        # Create karaoke-style dialogue events
        for chunk_idx, chunk in enumerate(chunks):
            # Get the next chunk's start time (for gap filling at chunk end)
            if chunk_idx + 1 < len(chunks):
                next_chunk_start = chunks[chunk_idx + 1][0]['start']
            else:
                next_chunk_start = None
            
            for highlight_idx, highlighted_word in enumerate(chunk):
                start_time = highlighted_word['start']
                
                # Extend end time to next word's start (fill all gaps)
                is_last_word_in_chunk = (highlight_idx == len(chunk) - 1)
                
                if is_last_word_in_chunk:
                    # Last word in chunk - extend to next chunk start
                    if next_chunk_start is not None:
                        end_time = next_chunk_start
                    else:
                        end_time = highlighted_word['end']
                else:
                    # Not last word - extend to next word in same chunk
                    next_word = chunk[highlight_idx + 1]
                    end_time = next_word['start']
                
                start_str = format_time_ass(start_time)
                end_str = format_time_ass(end_time)

                # Build text with current word having highlight background
                text_parts = []
                for idx, word_info in enumerate(chunk):
                    word_text = word_info['word'].strip().upper()
                    if idx == highlight_idx:
                        # Switch to Highlight style (colored box background)
                        text_parts.append(f"{{\\rHighlight}}{word_text}{{\\rDefault}}")
                    else:
                        # Normal white text
                        text_parts.append(f"{word_text}")
                
                text_content = " ".join(text_parts)
                f.write(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text_content}\n")

    logger.info(f"Created subtitle file: {filename}")
    return filename
