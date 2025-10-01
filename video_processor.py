#!/usr/bin/env python3
"""
Video Processor Tool for Ryan's Viral Pattern Detector
Downloads Instagram videos, uploads to Supabase Storage, and prepares for Gemini analysis.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import time
import json

import click
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client
from tqdm import tqdm
import yt_dlp

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "viral-videos")
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT_SEC", "180"))
MAX_VIDEO_SIZE_MB = int(os.getenv("MAX_VIDEO_SIZE_MB", "500"))
TEMP_DIR = Path(os.getenv("TEMP_DIR", "./temp"))
YTDLP_FORMAT = os.getenv("YTDLP_FORMAT", "best[ext=mp4]/best")
YTDLP_COOKIES_BROWSER = os.getenv("YTDLP_COOKIES_BROWSER", "chrome")
YTDLP_RETRIES = int(os.getenv("YTDLP_RETRIES", "3"))
MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
RETRY_BACKOFF_BASE = int(os.getenv("RETRY_BACKOFF_BASE", "60"))

# Setup logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"processing_{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of video processing."""
    post_id: str
    status: str
    video_url: Optional[str] = None
    error_message: Optional[str] = None
    file_size_mb: Optional[float] = None
    duration_sec: Optional[float] = None
    processing_time: Optional[float] = None


class VideoProcessor:
    """Main video processing orchestrator."""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.temp_downloads = TEMP_DIR / "downloads"
        self.temp_downloads.mkdir(parents=True, exist_ok=True)
        self.bucket_name = SUPABASE_BUCKET

    def get_supabase_client() -> Client:
        """Initialize Supabase client."""
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        return create_client(SUPABASE_URL, SUPABASE_KEY)

    def get_unprocessed_posts(self, source: str = "outliers") -> List[Dict]:
        """
        Get posts that need video processing.

        Args:
            source: "outliers" | "all" | "failed"

        Returns:
            List of posts needing processing
        """
        logger.info(f"Fetching unprocessed posts (source: {source})")

        if source == "outliers":
            # Get outliers without video URLs - need to go through posts table
            # First get post_ids from post_review
            review_result = (self.supabase.table("post_review")
                           .select("post_id")
                           .eq("outlier", True)
                           .is_("video_file_url", "null")
                           .execute())

            if not review_result.data:
                return []

            post_ids = [row["post_id"] for row in review_result.data]

            # Then get full post details with account info
            posts_result = (self.supabase.table("posts")
                          .select("id, post_url, post_id, caption, views, accounts(handle)")
                          .in_("id", post_ids)
                          .execute())

            posts = []
            for post in posts_result.data:
                account = post.get("accounts", {})
                posts.append({
                    "id": post.get("id"),
                    "post_url": post.get("post_url"),
                    "post_id": post.get("post_id"),
                    "caption": post.get("caption"),
                    "views": post.get("views"),
                    "handle": account.get("handle")
                })

        elif source == "failed":
            # Get failed processing attempts
            result = (self.supabase.table("video_processing_log")
                     .select("post_id, download_url")
                     .eq("status", "failed")
                     .execute())

            post_ids = [row["post_id"] for row in result.data]
            if not post_ids:
                return []

            # Get post details
            posts_result = (self.supabase.table("posts")
                           .select("id, post_url, post_id, caption, views, accounts(handle)")
                           .in_("id", post_ids)
                           .execute())

            posts = []
            for post in posts_result.data:
                account = post.get("accounts", {})
                posts.append({
                    "id": post.get("id"),
                    "post_url": post.get("post_url"),
                    "post_id": post.get("post_id"),
                    "caption": post.get("caption"),
                    "views": post.get("views"),
                    "handle": account.get("handle")
                })

        else:  # all
            # Get all posts without video URLs
            result = (self.supabase.table("posts")
                     .select("id, post_url, post_id, caption, views, accounts(handle)")
                     .is_("video_file_url", "null")
                     .execute())

            posts = []
            for post in result.data:
                account = post.get("accounts", {})
                posts.append({
                    "id": post.get("id"),
                    "post_url": post.get("post_url"),
                    "post_id": post.get("post_id"),
                    "caption": post.get("caption"),
                    "views": post.get("views"),
                    "handle": account.get("handle")
                })

        logger.info(f"Found {len(posts)} posts to process")
        return posts

    def download_video(self, post_url: str, output_path: Path) -> Dict:
        """
        Download video from Instagram using yt-dlp.

        Args:
            post_url: Instagram post URL
            output_path: Where to save video

        Returns:
            Dict with download metadata (duration, size, format)
        """
        logger.info(f"Downloading video from {post_url}")

        ydl_opts = {
            'outtmpl': str(output_path),
            'quiet': False,
            'no_warnings': False,
            'format': YTDLP_FORMAT,
            'retries': YTDLP_RETRIES,
            'fragment_retries': YTDLP_RETRIES,
            'ignoreerrors': False,
            'extract_flat': False,
            'socket_timeout': DOWNLOAD_TIMEOUT,
        }

        # Try to use cookies from browser for better access
        try:
            ydl_opts['cookiesfrombrowser'] = (YTDLP_COOKIES_BROWSER,)
        except Exception as e:
            logger.warning(f"Could not load cookies from {YTDLP_COOKIES_BROWSER}: {e}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(post_url, download=True)

                # Get metadata
                duration = info.get('duration', 0)
                filesize = info.get('filesize', 0) or info.get('filesize_approx', 0)

                # Check if file was actually downloaded
                if not output_path.exists():
                    # yt-dlp might have added extension
                    possible_files = list(output_path.parent.glob(f"{output_path.stem}.*"))
                    if possible_files:
                        actual_path = possible_files[0]
                        filesize = actual_path.stat().st_size
                    else:
                        raise Exception("Downloaded file not found")
                else:
                    filesize = output_path.stat().st_size

                file_size_mb = filesize / (1024 * 1024) if filesize else 0

                logger.info(f"Download complete: {file_size_mb:.2f}MB, {duration}s")

                return {
                    "duration_sec": duration,
                    "file_size_mb": file_size_mb,
                    "format": info.get('ext', 'mp4'),
                    "success": True
                }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download failed: {error_msg}")

            # Classify error type
            if "private" in error_msg.lower() or "login" in error_msg.lower():
                error_type = "private_account"
            elif "not available" in error_msg.lower() or "removed" in error_msg.lower():
                error_type = "deleted_post"
            elif "timeout" in error_msg.lower():
                error_type = "download_timeout"
            elif "429" in error_msg or "rate" in error_msg.lower():
                error_type = "rate_limit"
            else:
                error_type = "unknown_error"

            return {
                "success": False,
                "error": error_msg,
                "error_type": error_type
            }

    def upload_to_storage(self, local_path: Path, post_id: str, username: str) -> str:
        """
        Upload video to Supabase Storage.

        Args:
            local_path: Path to video file
            post_id: Post ID for organization
            username: Account username

        Returns:
            Public URL of uploaded video
        """
        # Find the actual file (yt-dlp might add extension)
        if not local_path.exists():
            possible_files = list(local_path.parent.glob(f"{local_path.stem}.*"))
            if not possible_files:
                raise FileNotFoundError(f"No file found matching {local_path.stem}")
            local_path = possible_files[0]

        logger.info(f"Uploading {local_path.name} to Supabase Storage")

        # Generate storage path: {year}/{month}/{username}_{post_id}_{timestamp}.mp4
        now = datetime.now()
        timestamp = int(now.timestamp())
        storage_path = f"{now.year}/{now.month:02d}/{username}_{post_id}_{timestamp}{local_path.suffix}"

        try:
            # Read file
            with open(local_path, 'rb') as f:
                file_data = f.read()

            # Upload to Supabase Storage
            result = self.supabase.storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=file_data,
                file_options={"content-type": "video/mp4"}
            )

            # Get public URL
            public_url = self.supabase.storage.from_(self.bucket_name).get_public_url(storage_path)

            logger.info(f"Upload complete: {public_url}")
            return public_url, storage_path

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise

    def update_database(self, post_id: str, video_url: str, storage_path: str, metadata: Dict, processing_time: float):
        """
        Update post_review with video URL and processing log.

        Args:
            post_id: Post UUID
            video_url: Supabase Storage public URL
            storage_path: Storage path
            metadata: Video metadata (size, duration, etc.)
            processing_time: Time taken to process
        """
        logger.info(f"Updating database for post {post_id}")

        try:
            # Update post_review with video URL
            self.supabase.table("post_review").update({
                "video_file_url": video_url,
                "updated_at": datetime.now().isoformat()
            }).eq("post_id", post_id).execute()

            # Log processing completion
            self.supabase.table("video_processing_log").insert({
                "post_id": post_id,
                "status": "completed",
                "download_url": video_url,
                "storage_path": storage_path,
                "file_size_mb": metadata.get("file_size_mb"),
                "video_duration_sec": metadata.get("duration_sec"),
                "processing_time_sec": processing_time,
                "updated_at": datetime.now().isoformat()
            }).execute()

            logger.info("Database updated successfully")

        except Exception as e:
            logger.error(f"Database update failed: {e}")
            raise

    def log_processing_error(self, post_id: str, error_msg: str, error_type: str):
        """
        Log processing error to database.

        Args:
            post_id: Post UUID
            error_msg: Error message
            error_type: Error classification
        """
        try:
            self.supabase.table("video_processing_log").insert({
                "post_id": post_id,
                "status": "failed",
                "error_message": f"[{error_type}] {error_msg}",
                "updated_at": datetime.now().isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log error: {e}")

    def process_video(self, post: Dict) -> ProcessingResult:
        """
        Process a single video: download, upload, update database.

        Args:
            post: Post data dict

        Returns:
            ProcessingResult
        """
        start_time = time.time()
        post_id = post["id"]
        post_url = post["post_url"]
        username = post.get("handle", "unknown")

        logger.info(f"Processing post {post_id} from @{username}")

        try:
            # Generate temp file path
            temp_file = self.temp_downloads / f"{post_id}.mp4"

            # Download video
            download_result = self.download_video(post_url, temp_file)

            if not download_result.get("success"):
                # Handle download failure
                error_msg = download_result.get("error", "Unknown error")
                error_type = download_result.get("error_type", "unknown_error")
                self.log_processing_error(post_id, error_msg, error_type)

                return ProcessingResult(
                    post_id=post_id,
                    status="failed",
                    error_message=f"[{error_type}] {error_msg}"
                )

            # Upload to storage
            try:
                video_url, storage_path = self.upload_to_storage(temp_file, post_id, username)
            except Exception as e:
                error_msg = f"Upload failed: {str(e)}"
                self.log_processing_error(post_id, error_msg, "storage_upload_fail")
                return ProcessingResult(
                    post_id=post_id,
                    status="failed",
                    error_message=error_msg
                )

            # Update database
            processing_time = time.time() - start_time
            self.update_database(
                post_id=post_id,
                video_url=video_url,
                storage_path=storage_path,
                metadata=download_result,
                processing_time=processing_time
            )

            # Cleanup temp file
            try:
                # Find and remove the actual downloaded file
                if temp_file.exists():
                    temp_file.unlink()
                else:
                    # Look for file with extension added by yt-dlp
                    for f in self.temp_downloads.glob(f"{post_id}.*"):
                        f.unlink()
            except Exception as e:
                logger.warning(f"Could not cleanup temp file: {e}")

            return ProcessingResult(
                post_id=post_id,
                status="completed",
                video_url=video_url,
                file_size_mb=download_result.get("file_size_mb"),
                duration_sec=download_result.get("duration_sec"),
                processing_time=processing_time
            )

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            self.log_processing_error(post_id, error_msg, "unexpected_error")

            return ProcessingResult(
                post_id=post_id,
                status="failed",
                error_message=error_msg
            )

    def process_batch(self, posts: List[Dict], show_progress: bool = True) -> Dict:
        """
        Process multiple videos sequentially with progress tracking.

        Args:
            posts: List of post records
            show_progress: Show progress bar

        Returns:
            Processing summary
        """
        results = {
            "total": len(posts),
            "completed": 0,
            "failed": 0,
            "errors": []
        }

        iterator = tqdm(posts, desc="Processing videos") if show_progress else posts

        for post in iterator:
            result = self.process_video(post)

            if result.status == "completed":
                results["completed"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({
                    "post_id": result.post_id,
                    "error": result.error_message
                })

        return results


def get_supabase_client() -> Client:
    """Initialize Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@click.group()
def cli():
    """Video Processor - Download and process Instagram videos for viral analysis."""
    pass


@cli.command()
@click.option('--input', 'input_file', type=click.Path(exists=True), help='CSV file with posts to process')
@click.option('--post-ids', help='Comma-separated post IDs to process')
@click.option('--unprocessed-outliers', is_flag=True, help='Process all unprocessed outliers')
@click.option('--concurrent', default=1, type=int, help='Concurrent processing (currently sequential)')
def process(input_file, post_ids, unprocessed_outliers, concurrent):
    """Process videos: download, upload to storage, update database."""
    try:
        supabase = get_supabase_client()
        processor = VideoProcessor(supabase)

        # Determine which posts to process
        if input_file:
            logger.info(f"Loading posts from {input_file}")
            df = pd.read_csv(input_file)

            # Get post details from database
            post_urls = df['post_url'].tolist() if 'post_url' in df.columns else []
            if not post_urls:
                click.echo("Error: CSV must have 'post_url' column")
                return

            # Look up posts in database
            posts = []
            for url in post_urls:
                result = supabase.table("posts").select(
                    "id, post_url, post_id, caption, views, accounts(handle)"
                ).eq("post_url", url).execute()

                if result.data:
                    post = result.data[0]
                    account = post.get("accounts", {})
                    posts.append({
                        "id": post["id"],
                        "post_url": post["post_url"],
                        "post_id": post["post_id"],
                        "caption": post.get("caption"),
                        "views": post.get("views"),
                        "handle": account.get("handle")
                    })

        elif post_ids:
            logger.info(f"Processing specific post IDs")
            id_list = [id.strip() for id in post_ids.split(',')]

            result = supabase.table("posts").select(
                "id, post_url, post_id, caption, views, accounts(handle)"
            ).in_("id", id_list).execute()

            posts = []
            for post in result.data:
                account = post.get("accounts", {})
                posts.append({
                    "id": post["id"],
                    "post_url": post["post_url"],
                    "post_id": post["post_id"],
                    "caption": post.get("caption"),
                    "views": post.get("views"),
                    "handle": account.get("handle")
                })

        elif unprocessed_outliers:
            logger.info("Processing unprocessed outliers")
            posts = processor.get_unprocessed_posts(source="outliers")

        else:
            click.echo("Error: Must specify --input, --post-ids, or --unprocessed-outliers")
            return

        if not posts:
            click.echo("No posts to process")
            return

        click.echo(f"\nProcessing {len(posts)} videos...")

        # Process batch
        results = processor.process_batch(posts)

        # Print summary
        click.echo(f"\n{'='*60}")
        click.echo(f"Processing Complete")
        click.echo(f"{'='*60}")
        click.echo(f"Total: {results['total']}")
        click.echo(f"Completed: {results['completed']}")
        click.echo(f"Failed: {results['failed']}")

        if results['errors']:
            click.echo(f"\nErrors:")
            for error in results['errors'][:10]:  # Show first 10
                click.echo(f"  - {error['post_id']}: {error['error']}")
            if len(results['errors']) > 10:
                click.echo(f"  ... and {len(results['errors']) - 10} more")

    except Exception as e:
        logger.error(f"Process command failed: {e}")
        click.echo(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.option('--max-attempts', default=3, type=int, help='Maximum retry attempts')
def retry_failed(max_attempts):
    """Retry failed downloads."""
    try:
        supabase = get_supabase_client()
        processor = VideoProcessor(supabase)

        posts = processor.get_unprocessed_posts(source="failed")

        if not posts:
            click.echo("No failed downloads to retry")
            return

        click.echo(f"Retrying {len(posts)} failed downloads...")
        results = processor.process_batch(posts)

        click.echo(f"\nRetry Complete: {results['completed']} succeeded, {results['failed']} failed")

    except Exception as e:
        logger.error(f"Retry command failed: {e}")
        click.echo(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.option('--detailed', is_flag=True, help='Show detailed status')
def status(detailed):
    """Check processing status."""
    try:
        supabase = get_supabase_client()

        # Get status summary
        result = supabase.table("video_processing_log").select(
            "status, created_at, processing_time_sec"
        ).execute()

        if not result.data:
            click.echo("No processing records found")
            return

        # Count by status
        status_counts = {}
        for row in result.data:
            status = row.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        click.echo("\nProcessing Status:")
        click.echo(f"{'='*40}")
        for status, count in sorted(status_counts.items()):
            click.echo(f"{status}: {count}")

        if detailed:
            # Get recent failures
            failures = supabase.table("video_processing_log").select(
                "post_id, error_message, created_at"
            ).eq("status", "failed").order("created_at", desc=True).limit(10).execute()

            if failures.data:
                click.echo(f"\nRecent Failures:")
                click.echo(f"{'='*40}")
                for f in failures.data:
                    click.echo(f"{f.get('created_at')}: {f.get('error_message')}")

    except Exception as e:
        logger.error(f"Status command failed: {e}")
        click.echo(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.option('--keep-days', default=7, type=int, help='Keep files from last N days')
def cleanup(keep_days):
    """Clean up temporary files."""
    try:
        temp_dir = TEMP_DIR / "downloads"
        if not temp_dir.exists():
            click.echo("No temp directory to clean")
            return

        cutoff_time = datetime.now() - timedelta(days=keep_days)
        removed_count = 0

        for file in temp_dir.iterdir():
            if file.is_file() and datetime.fromtimestamp(file.stat().st_mtime) < cutoff_time:
                file.unlink()
                removed_count += 1

        click.echo(f"Cleaned up {removed_count} files older than {keep_days} days")

    except Exception as e:
        logger.error(f"Cleanup command failed: {e}")
        click.echo(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
