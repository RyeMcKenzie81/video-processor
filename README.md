# Video Processor

Video Processor tool for Ryan's Viral Pattern Detector. Downloads Instagram videos from outliers, uploads to Supabase Storage, and prepares for Gemini AI analysis.

## Features

- **Download Instagram Videos**: Uses yt-dlp to download videos from Instagram URLs
- **Supabase Storage**: Uploads videos to organized Supabase Storage buckets
- **Database Integration**: Updates database with video URLs and processing status
- **Error Handling**: Gracefully handles private accounts, deleted videos, rate limits
- **Batch Processing**: Process multiple videos with progress tracking
- **Retry Failed**: Retry failed downloads with configurable attempts
- **Status Monitoring**: Check processing status and view error logs

## Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:
```bash
# Supabase Configuration
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key
SUPABASE_STORAGE_BUCKET=viral-videos

# Processing Configuration (defaults shown)
MAX_CONCURRENT_DOWNLOADS=3
DOWNLOAD_TIMEOUT_SEC=180
MAX_VIDEO_SIZE_MB=500
```

3. Run database migration in Supabase SQL Editor:
```bash
cat sql/migration.sql
```

Copy and run the SQL in your Supabase dashboard.

4. Create Supabase Storage Bucket:
   - Go to Supabase Dashboard → Storage
   - Create new bucket named `viral-videos`
   - Set to public (for easy access to videos)

## Usage

### Process Unprocessed Outliers

Process all outlier videos that haven't been downloaded yet:

```bash
python video_processor.py process --unprocessed-outliers
```

### Process from CSV Export

Process videos from Ryan's VPD outliers export:

```bash
python video_processor.py process --input ../ryan-viral-pattern-detector/exports/outliers_to_download_2025-09-30.csv
```

### Process Specific Posts

Process specific posts by ID:

```bash
python video_processor.py process --post-ids "uuid1,uuid2,uuid3"
```

### Retry Failed Downloads

Retry videos that failed to download:

```bash
python video_processor.py retry-failed --max-attempts 3
```

### Check Status

View processing status:

```bash
# Summary
python video_processor.py status

# Detailed (shows recent errors)
python video_processor.py status --detailed
```

### Cleanup Temp Files

Remove old temporary files:

```bash
# Remove files older than 7 days
python video_processor.py cleanup --keep-days 7
```

## CLI Commands

```
Usage: video_processor.py [OPTIONS] COMMAND [ARGS]...

Commands:
  process        Process videos: download, upload to storage, update database
  retry-failed   Retry failed downloads
  status         Check processing status
  cleanup        Clean up temporary files

Process Options:
  --input PATH              CSV file with posts to process
  --post-ids TEXT           Comma-separated post IDs to process
  --unprocessed-outliers    Process all unprocessed outliers
  --concurrent INTEGER      Concurrent processing (default: 1)

Status Options:
  --detailed                Show detailed status with recent errors

Cleanup Options:
  --keep-days INTEGER       Keep files from last N days (default: 7)
```

## Data Flow

```
Ryan's VPD (outliers) → Video Processor → Supabase Storage
         ↓                     ↓                  ↓
    posts table      video_file_url         Public URLs
                             ↓
                     video_processing_log
```

## Database Schema

### video_processing_log

Tracks video processing status:

```sql
- post_id: Reference to posts table
- status: pending|downloading|downloaded|uploading|completed|failed
- error_message: Error details if failed
- storage_path: Path in Supabase Storage
- file_size_mb: Video file size
- video_duration_sec: Video duration
- processing_time_sec: Time taken to process
```

### video_analysis (Phase 2)

Will store Gemini AI analysis results:
- Hook analysis with timestamps
- Full transcript
- Visual storyboard
- Viral factors scoring
- Improvement suggestions

## Error Handling

The tool handles common errors gracefully:

- **Private Account**: Marks as inaccessible, skips
- **Deleted Post**: Marks as deleted, skips
- **Rate Limited**: Implements exponential backoff
- **Download Timeout**: Retries with longer timeout
- **Storage Upload Fail**: Retries upload, keeps local copy

All errors are logged to `logs/processing_YYYY-MM-DD.log` and database.

## Storage Organization

Videos are organized in Supabase Storage:

```
/viral-videos/
    /2025/
        /09/
            username_postid_timestamp.mp4
        /10/
            username_postid_timestamp.mp4
```

## Logging

Logs are written to:
- Console (real-time)
- `logs/processing_YYYY-MM-DD.log` (daily log files)
- Database (`video_processing_log` table)

## Troubleshooting

### "yt-dlp cannot access video"

The video may be from a private account or have been deleted. The tool will log this and skip.

### "Rate limited"

Instagram has rate limits. The tool will automatically back off and retry. You can also:
- Reduce `MAX_CONCURRENT_DOWNLOADS`
- Increase wait time between batches

### "Storage upload failed"

Check:
1. Supabase Storage bucket exists and is named correctly
2. Service role key has storage permissions
3. Network connection is stable

### "Could not load cookies"

The tool tries to use browser cookies for better access. If this fails:
1. Make sure the browser specified in `YTDLP_COOKIES_BROWSER` is installed
2. Try a different browser (chrome, firefox, safari, edge)
3. Or disable by removing this option (may reduce success rate)

## Integration with Ryan's VPD

1. Run VPD to identify outliers:
```bash
cd ../ryan-viral-pattern-detector
python ryan_vpd.py analyze
python ryan_vpd.py export --format outliers
```

2. Process the outlier videos:
```bash
cd ../video-processor
python video_processor.py process --input ../ryan-viral-pattern-detector/exports/outliers_to_download_*.csv
```

3. Check processing status:
```bash
python video_processor.py status --detailed
```

4. Videos are now ready for Gemini analysis (Phase 2)

## Phase 2: Gemini AI Analysis

**Status**: In Development

Analyze downloaded videos with Gemini AI to extract viral patterns and actionable insights.

### Features

- **Hook Analysis**: Extract and analyze the first 3-5 seconds
  - Transcript of spoken/on-screen content
  - Visual description of opening
  - Hook type classification (question, shock, curiosity, etc.)
  - Effectiveness scoring

- **Full Content Extraction**:
  - Complete transcript with timestamps
  - Text overlay detection and extraction
  - Scene-by-scene visual storyboard
  - Key moments identification

- **Viral Factors Analysis**:
  - Multi-dimensional scoring (hook strength, emotional impact, relatability, novelty, etc.)
  - Explanation of why the video went viral
  - Pattern matching with successful viral content
  - Improvement suggestions for content creators

### Usage

```bash
# Check analysis status
python video_processor.py analyze-status

# Test analysis on 1 video
python video_processor.py analyze --test

# Analyze specific number of videos
python video_processor.py analyze --limit 10

# Analyze all unanalyzed videos
python video_processor.py analyze
```

### Configuration

Add to `.env`:
```bash
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=models/gemini-flash-latest
MAX_ANALYSIS_RETRIES=3
```

### Output

Analysis results are stored in the `video_analysis` table with:
- Hook transcript and storyboard
- Full transcript with timestamps
- Text overlays
- Visual storyboard
- Key moments
- Viral factors scoring
- Viral explanation
- Improvement suggestions

## Phase 1 Status: ✅ COMPLETED

**Date**: September 30, 2025
**Videos Processed**: 104/104 (100% success rate)
**Total Data**: ~1.2GB of video content
**Processing Time**: ~21 minutes
**Storage**: All videos uploaded to Supabase Storage at `videos/2025/09/`

All outlier videos have been successfully:
- ✅ Downloaded from Instagram using yt-dlp
- ✅ Uploaded to Supabase Storage with organized folder structure
- ✅ Database updated with public URLs in `post_review.video_file_url`
- ✅ Processing logs created in `video_processing_log` table

Videos are now ready for Phase 2: Gemini AI Analysis.

## Performance

- **Download Speed**: Depends on Instagram and network
- **Upload Speed**: ~10MB/s to Supabase Storage (typical)
- **Processing Time**: ~12 seconds per video (average, tested with 104 videos)
- **Success Rate**: 100% (104/104 videos successfully processed)

## Requirements

- Python 3.8+
- Supabase account with Storage enabled
- Internet connection
- Browser installed (for cookie extraction)

## License

Part of Ryan's Viral Pattern Detector toolkit.
