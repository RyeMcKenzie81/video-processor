#!/usr/bin/env python3
"""
Video Analyzer using Gemini AI
Analyzes viral videos to extract hooks, transcripts, and viral factors.
"""

import os
import logging
import time
import json
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass
import tempfile

import google.generativeai as genai
from dotenv import load_dotenv
from supabase import Client
from tqdm import tqdm

# Load environment
load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-flash-latest")
MAX_ANALYSIS_RETRIES = int(os.getenv("MAX_ANALYSIS_RETRIES", "3"))

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of video analysis."""
    post_id: str
    status: str
    hook_transcript: Optional[str] = None
    hook_visual_storyboard: Optional[Dict] = None
    hook_type: Optional[str] = None
    hook_timestamp: Optional[float] = None
    transcript: Optional[Dict] = None
    text_overlays: Optional[Dict] = None
    storyboard: Optional[Dict] = None
    key_moments: Optional[Dict] = None
    viral_factors: Optional[Dict] = None
    viral_explanation: Optional[str] = None
    improvement_suggestions: Optional[str] = None
    tokens_used: Optional[int] = None
    processing_time: Optional[float] = None
    error_message: Optional[str] = None


class VideoAnalyzer:
    """Analyzes videos using Gemini AI to extract viral patterns."""

    def __init__(self, supabase_client: Client):
        """Initialize the video analyzer."""
        self.supabase = supabase_client

        # Configure Gemini
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY must be set in .env")

        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(GEMINI_MODEL)

        logger.info(f"VideoAnalyzer initialized with model: {GEMINI_MODEL}")

    def get_unanalyzed_videos(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Get videos that have been processed but not yet analyzed.

        Args:
            limit: Maximum number of videos to return

        Returns:
            List of video records ready for analysis
        """
        logger.info("Fetching unanalyzed videos")

        # Get all completed videos
        processed_result = (self.supabase.table("video_processing_log")
                          .select("post_id, storage_path, file_size_mb, video_duration_sec, posts(id, post_url, caption, views, accounts(handle))")
                          .eq("status", "completed")
                          .execute())

        # Get all analyzed videos
        analyzed_result = self.supabase.table("video_analysis").select("post_id").execute()
        analyzed_post_ids = {row["post_id"] for row in analyzed_result.data}

        # Filter to get only unanalyzed
        unanalyzed = [v for v in processed_result.data if v["post_id"] not in analyzed_post_ids]

        # Apply limit if specified
        if limit:
            unanalyzed = unanalyzed[:limit]

        logger.info(f"Found {len(unanalyzed)} unanalyzed videos")
        return unanalyzed

    def download_video_from_storage(self, storage_path: str) -> Path:
        """
        Download video from Supabase Storage to temporary file.

        Args:
            storage_path: Path in Supabase Storage

        Returns:
            Path to downloaded temporary file
        """
        logger.info(f"Downloading video from storage: {storage_path}")

        # Get the video data from Supabase Storage
        bucket_name = os.getenv("SUPABASE_STORAGE_BUCKET", "videos")
        data = self.supabase.storage.from_(bucket_name).download(storage_path)

        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        temp_file.write(data)
        temp_file.close()

        logger.info(f"Video downloaded to: {temp_file.name}")
        return Path(temp_file.name)

    def analyze_video(self, video_path: Path, post_data: Dict) -> Dict:
        """
        Analyze a video using Gemini AI.

        Args:
            video_path: Path to video file
            post_data: Metadata about the post

        Returns:
            Analysis results as dict
        """
        logger.info(f"Analyzing video: {video_path}")

        # Upload video to Gemini
        video_file = genai.upload_file(path=str(video_path))
        logger.info(f"Uploaded file to Gemini: {video_file.uri}")

        # Wait for file to be processed
        while video_file.state.name == "PROCESSING":
            time.sleep(2)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            raise ValueError(f"Video processing failed: {video_file.state}")

        # Create comprehensive analysis prompt
        prompt = self._create_analysis_prompt(post_data)

        # Generate analysis
        response = self.model.generate_content(
            [video_file, prompt],
            request_options={"timeout": 600}
        )

        # Parse the response
        analysis = self._parse_analysis_response(response.text)

        # Clean up uploaded file
        genai.delete_file(video_file.name)
        logger.info("Deleted temporary Gemini file")

        return analysis

    def _create_analysis_prompt(self, post_data: Dict) -> str:
        """Create a comprehensive analysis prompt for Gemini."""

        caption = post_data.get('caption', 'No caption')
        views = post_data.get('views', 0)
        username = post_data.get('accounts', {}).get('handle', 'unknown')

        prompt = f"""Analyze this viral Instagram video and provide a comprehensive breakdown.

**Video Context:**
- Username: @{username}
- Caption: {caption}
- Views: {views:,}

**Your Task:**
Provide a detailed JSON analysis with the following structure:

{{
  "hook_analysis": {{
    "transcript": "What is said/shown in the first 3-5 seconds",
    "visual_description": "Detailed description of opening visuals",
    "hook_type": "question|shock|curiosity|problem|story|trend",
    "timestamp_end": 5.0,
    "effectiveness_score": 8.5
  }},

  "full_transcript": {{
    "segments": [
      {{"timestamp": 0.0, "text": "spoken or on-screen text", "speaker": "narrator|text_overlay"}},
    ]
  }},

  "text_overlays": {{
    "overlays": [
      {{"timestamp": 0.0, "text": "overlay text", "style": "bold|caption|animated"}}
    ]
  }},

  "visual_storyboard": {{
    "scenes": [
      {{"timestamp": 0.0, "description": "what's happening visually", "duration": 3.0}}
    ]
  }},

  "key_moments": {{
    "moments": [
      {{"timestamp": 5.0, "type": "reveal|transition|climax|cta", "description": "what makes this moment significant"}}
    ]
  }},

  "viral_factors": {{
    "hook_strength": 9.0,
    "emotional_impact": 8.5,
    "relatability": 9.5,
    "novelty": 7.0,
    "production_quality": 8.0,
    "pacing": 9.0,
    "overall_score": 8.5
  }},

  "viral_explanation": "2-3 sentences explaining WHY this video went viral. What specific elements drove engagement?",

  "improvement_suggestions": "3-5 specific, actionable suggestions for similar content creators to replicate this video's success"
}}

**Guidelines:**
- Be extremely specific and detailed
- Include exact timestamps for all events
- Identify the emotional triggers used
- Note any trends, memes, or cultural references
- Analyze pacing and editing choices
- Identify the target audience
- Note any call-to-action elements

Provide ONLY the JSON response, no additional text."""

        return prompt

    def _parse_analysis_response(self, response_text: str) -> Dict:
        """Parse Gemini's JSON response."""
        try:
            # Extract JSON from response (in case there's markdown formatting)
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            analysis = json.loads(response_text.strip())
            return analysis
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response text: {response_text[:500]}")
            # Return a fallback structure
            return {
                "error": "Failed to parse response",
                "raw_response": response_text[:1000]
            }

    def save_analysis(self, post_id: str, analysis: Dict, processing_time: float, tokens_used: int = 0) -> None:
        """
        Save analysis results to database.

        Args:
            post_id: UUID of the post
            analysis: Analysis results dict
            processing_time: Time taken for analysis
            tokens_used: Number of tokens consumed
        """
        logger.info(f"Saving analysis for post {post_id}")

        # Extract components from analysis
        hook = analysis.get("hook_analysis", {})
        transcript = analysis.get("full_transcript", {})
        overlays = analysis.get("text_overlays", {})
        storyboard = analysis.get("visual_storyboard", {})
        moments = analysis.get("key_moments", {})
        factors = analysis.get("viral_factors", {})

        # Prepare record
        record = {
            "post_id": post_id,
            "hook_transcript": hook.get("transcript"),
            "hook_visual_storyboard": json.dumps(hook) if hook else None,
            "hook_type": hook.get("hook_type"),
            "hook_timestamp": hook.get("timestamp_end"),
            "transcript": json.dumps(transcript) if transcript else None,
            "text_overlays": json.dumps(overlays) if overlays else None,
            "storyboard": json.dumps(storyboard) if storyboard else None,
            "key_moments": json.dumps(moments) if moments else None,
            "viral_factors": json.dumps(factors) if factors else None,
            "viral_explanation": analysis.get("viral_explanation"),
            "improvement_suggestions": analysis.get("improvement_suggestions"),
            "analysis_model": GEMINI_MODEL,
            "analysis_tokens_used": tokens_used,
            "processing_time_sec": processing_time
        }

        # Insert into video_analysis table
        result = self.supabase.table("video_analysis").insert(record).execute()
        logger.info(f"Analysis saved successfully: {len(result.data)} record(s)")

    def process_video(self, video_record: Dict) -> AnalysisResult:
        """
        Process a single video: download, analyze, save results.

        Args:
            video_record: Video record from database

        Returns:
            AnalysisResult with status
        """
        post_id = video_record['post_id']
        storage_path = video_record['storage_path']

        start_time = time.time()
        temp_path = None

        try:
            logger.info(f"Processing video for post {post_id}")

            # Download video from storage
            temp_path = self.download_video_from_storage(storage_path)

            # Get post data
            post_data = video_record.get('posts', {})

            # Analyze with Gemini
            analysis = self.analyze_video(temp_path, post_data)

            # Calculate processing time
            processing_time = time.time() - start_time

            # Save to database
            self.save_analysis(post_id, analysis, processing_time)

            return AnalysisResult(
                post_id=post_id,
                status="completed",
                hook_transcript=analysis.get("hook_analysis", {}).get("transcript"),
                hook_type=analysis.get("hook_analysis", {}).get("hook_type"),
                viral_explanation=analysis.get("viral_explanation"),
                processing_time=processing_time
            )

        except Exception as e:
            logger.error(f"Error processing video {post_id}: {e}")
            return AnalysisResult(
                post_id=post_id,
                status="failed",
                error_message=str(e),
                processing_time=time.time() - start_time
            )

        finally:
            # Clean up temporary file
            if temp_path and temp_path.exists():
                temp_path.unlink()
                logger.info(f"Deleted temporary file: {temp_path}")

    def process_batch(self, limit: Optional[int] = None, show_progress: bool = True) -> Dict[str, int]:
        """
        Process a batch of unanalyzed videos.

        Args:
            limit: Maximum number of videos to process
            show_progress: Whether to show progress bar

        Returns:
            Summary dict with counts
        """
        videos = self.get_unanalyzed_videos(limit=limit)

        if not videos:
            logger.info("No videos to analyze")
            return {"total": 0, "completed": 0, "failed": 0}

        results = {"completed": 0, "failed": 0}

        # Process with progress bar
        iterator = tqdm(videos, desc="Analyzing videos") if show_progress else videos

        for video in iterator:
            result = self.process_video(video)

            if result.status == "completed":
                results["completed"] += 1
            else:
                results["failed"] += 1

            # Add small delay to avoid rate limits
            time.sleep(2)

        results["total"] = len(videos)

        logger.info(f"Batch complete: {results['completed']} succeeded, {results['failed']} failed")
        return results
