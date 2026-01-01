# YouTube Shorts Downloader

Download all Shorts from a YouTube channel with metadata extraction.

## Features

- ✅ Downloads all Shorts from a channel URL
- ✅ Best quality MP4 without re-encoding
- ✅ Preserves full title (emojis + hashtags) as filename
- ✅ Extracts metadata: title, description, hashtags
- ✅ Saves to JSON and CSV

## Installation

```bash
# Clone the repo
git clone https://github.com/ChheanSilapin/yt-tool.git
cd yt-tool

# Install dependencies (requires uv)
uv sync
```

## Usage

```bash
# With URL argument
uv run python main.py https://www.youtube.com/@username/shorts

# Or run and enter URL when prompted
uv run python main.py
```

## Output

```
downloads/
├── The Elmo laugh 😂 #offroad #fordperformance #ford.mp4
├── Another Cool Short #viral #fyp.mp4
├── ...
├── shorts_metadata.json
└── shorts_metadata.csv
```

### Metadata Format

**JSON:**
```json
[
  {
    "id": "abc123",
    "title": "Video Title #shorts",
    "description": "Full description...",
    "hashtags": ["shorts", "viral", "fyp"],
    "duration": 30,
    "view_count": 1000000
  }
]
```

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- FFmpeg (for merging video/audio streams)

## License

MIT
