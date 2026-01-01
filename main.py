"""
YouTube Shorts Downloader

Downloads all Shorts from a YouTube channel and saves videos + metadata.
"""

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import yt_dlp


def sanitize_filename(title: str) -> str:
    """
    Sanitize filename by removing only invalid filesystem characters.
    Preserves emojis, hashtags, and spaces.
    """
    # Remove characters invalid on Windows: / \ : * ? " < > |
    invalid_chars = r'[\\/:*?"<>|]'
    sanitized = re.sub(invalid_chars, '', title)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip().strip('.')
    # Limit length to avoid filesystem issues (max 200 chars for safety)
    if len(sanitized) > 200:
        sanitized = sanitized[:200].strip()
    return sanitized


def get_shorts_list(channel_url: str) -> list[dict]:
    """
    Get list of all Shorts from a channel without downloading.
    
    Args:
        channel_url: YouTube channel Shorts URL (e.g., https://www.youtube.com/@username/shorts)
    
    Returns:
        List of dicts with video info (url, id, title)
    """
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'no_warnings': True,
    }
    
    print(f"📋 Fetching Shorts list from: {channel_url}")
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        
        if not info:
            print("❌ Could not fetch channel info")
            return []
        
        entries = info.get('entries', [])
        shorts_list = []
        
        for entry in entries:
            if entry:
                shorts_list.append({
                    'url': entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}",
                    'id': entry.get('id'),
                    'title': entry.get('title', 'Unknown'),
                })
        
        print(f"✅ Found {len(shorts_list)} Shorts")
        return shorts_list


def download_short(url: str, output_dir: Path, include_id: bool = True) -> dict | None:
    """
    Download a single Short in best quality and return metadata.
    
    Args:
        url: YouTube video URL
        output_dir: Directory to save the video
        include_id: Whether to include video ID in filename (prevents duplicates)
    
    Returns:
        Dict with video metadata or None if failed
    """
    # Choose filename template based on user preference
    if include_id:
        template = '%(title)s_%(id)s.%(ext)s'  # With ID (safe, prevents duplicates)
    else:
        template = '%(title)s.%(ext)s'  # Without ID (cleaner, may have conflicts)
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',  # Prefer MP4
        'merge_output_format': 'mp4',  # Force MP4 container
        'outtmpl': str(output_dir / template),
        'quiet': True,  # Suppress yt-dlp output
        'no_warnings': True,  # Suppress warnings
        'noprogress': True,  # No download progress bar
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if not info:
                return None
            
            # Get the actual filename that was saved
            title = info.get('title', 'Unknown')
            ext = info.get('ext', 'mp4')
            safe_title = sanitize_filename(title)
            
            # Rename file to sanitized version if needed
            original_path = output_dir / f"{title}.{ext}"
            sanitized_path = output_dir / f"{safe_title}.{ext}"
            
            if original_path.exists() and original_path != sanitized_path:
                try:
                    original_path.rename(sanitized_path)
                except OSError:
                    # If rename fails, file might already have been sanitized by yt-dlp
                    pass
            
            return {
                'id': info.get('id'),
                'title': title,
                'description': info.get('description', ''),
                'tags': info.get('tags', []),
                'hashtags': extract_hashtags(info),
                'filename': f"{safe_title}.{ext}",
                'duration': info.get('duration'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
            }
    except Exception as e:
        print(f"❌ Error downloading {url}: {e}")
        return None


def extract_hashtags(info: dict) -> list[str]:
    """
    Extract hashtags from video info (tags + description).
    """
    hashtags = set()
    
    # Get tags (usually correspond to hashtags)
    tags = info.get('tags', [])
    if tags:
        for tag in tags:
            if tag:
                hashtags.add(tag.lower())
    
    # Parse hashtags from description
    description = info.get('description', '')
    if description:
        found = re.findall(r'#(\w+)', description)
        for tag in found:
            hashtags.add(tag.lower())
    
    # Parse hashtags from title
    title = info.get('title', '')
    if title:
        found = re.findall(r'#(\w+)', title)
        for tag in found:
            hashtags.add(tag.lower())
    
    return sorted(list(hashtags))


def save_metadata(metadata_list: list[dict], output_dir: Path):
    """
    Save metadata to JSON and CSV files.
    """
    if not metadata_list:
        print("⚠️ No metadata to save")
        return
    
    # Save JSON
    json_path = output_dir / 'shorts_metadata.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(metadata_list, f, ensure_ascii=False, indent=2)
    print(f"📄 Saved metadata to: {json_path}")
    
    # Save CSV
    csv_path = output_dir / 'shorts_metadata.csv'
    df = pd.DataFrame(metadata_list)
    # Convert lists to comma-separated strings for CSV
    if 'tags' in df.columns:
        df['tags'] = df['tags'].apply(lambda x: ', '.join(x) if isinstance(x, list) else x)
    if 'hashtags' in df.columns:
        df['hashtags'] = df['hashtags'].apply(lambda x: ', '.join(x) if isinstance(x, list) else x)
    df.to_csv(csv_path, index=False, encoding='utf-8')
    print(f"📄 Saved metadata to: {csv_path}")


def main():
    """Main entry point for the YouTube Shorts downloader."""
    # Get channel URL from command line or prompt
    if len(sys.argv) > 1:
        channel_url = sys.argv[1]
    else:
        channel_url = input("Enter YouTube channel Shorts URL (e.g., https://www.youtube.com/@username/shorts): ").strip()
    
    if not channel_url:
        print("❌ No URL provided")
        sys.exit(1)
    
    # Normalize URL to ensure it points to Shorts tab
    if '/shorts' not in channel_url:
        # Try to add /shorts to the URL
        channel_url = channel_url.rstrip('/') + '/shorts'
        print(f"📝 Normalized URL to: {channel_url}")
    
    # Create output directory
    output_dir = Path('downloads')
    output_dir.mkdir(exist_ok=True)
    print(f"📁 Output directory: {output_dir.absolute()}")
    
    # Get list of Shorts
    shorts_list = get_shorts_list(channel_url)
    
    if not shorts_list:
        print("❌ No Shorts found")
        sys.exit(1)
    
    # Download each Short and collect metadata
    metadata_list = []
    total = len(shorts_list)
    
    for i, short in enumerate(shorts_list, 1):
        print(f"\n{'='*60}")
        print(f"⬇️  Downloading {i}/{total}: {short['title']}")
        print(f"{'='*60}")
        
        metadata = download_short(short['url'], output_dir)
        if metadata:
            metadata_list.append(metadata)
            print(f"✅ Downloaded: {metadata['filename']}")
        else:
            print(f"⚠️ Skipped: {short['title']}")
    
    # Save metadata
    print(f"\n{'='*60}")
    print("📊 Saving metadata...")
    print(f"{'='*60}")
    save_metadata(metadata_list, output_dir)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"🎉 Complete! Downloaded {len(metadata_list)}/{total} Shorts")
    print(f"📁 Videos saved to: {output_dir.absolute()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
