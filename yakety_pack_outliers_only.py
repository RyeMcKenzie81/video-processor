#!/usr/bin/env python3
"""
Re-evaluate only the statistical outlier videos (3SD from trimmed mean) for Yakety Pack.
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client
import numpy as np
from scipy import stats

# Add parent directory to path to import from yakety_pack_evaluator
sys.path.insert(0, os.path.dirname(__file__))
from yakety_pack_evaluator import evaluate_video, save_evaluations, generate_markdown_report
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Supabase
supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)


def get_outlier_videos():
    """Get videos that are 3SD from trimmed mean based on views."""
    logger.info("Fetching all posts to calculate outliers...")

    # Get all posts with views
    response = supabase.from_('posts').select('post_id, views').execute()
    posts = response.data

    # Calculate trimmed mean and SD
    views = [p['views'] for p in posts if p['views']]
    trimmed_mean = stats.trim_mean(views, 0.1)  # Trim 10% from each end
    std_dev = np.std(views)
    threshold = trimmed_mean + (3 * std_dev)

    logger.info(f"Trimmed Mean: {trimmed_mean:,.0f}")
    logger.info(f"Standard Deviation: {std_dev:,.0f}")
    logger.info(f"Threshold (3SD above): {threshold:,.0f}")

    # Get outlier post_ids
    outlier_post_ids = [p['post_id'] for p in posts if p['views'] and p['views'] >= threshold]
    logger.info(f"Found {len(outlier_post_ids)} outlier videos")

    # Fetch full video analysis for outliers
    logger.info("Fetching video analysis for outliers...")
    response = supabase.from_('video_analysis').select(
        """
        *,
        posts(
            id,
            post_url,
            post_id,
            caption,
            views,
            accounts(handle)
        )
        """
    ).in_('post_id', outlier_post_ids).execute()

    logger.info(f"Retrieved {len(response.data)} outlier video analyses")
    return response.data


def main():
    """Main execution function."""
    logger.info("Starting Yakety Pack outlier video evaluation...")

    # Get outlier videos
    videos = get_outlier_videos()

    # Evaluate each video
    evaluations = []
    for video in videos:
        eval_result = evaluate_video(video)
        if eval_result:
            evaluations.append(eval_result)

    # Save results
    if evaluations:
        json_path = save_evaluations(evaluations, 'yakety_pack_outliers_evaluations.json')
        md_path = generate_markdown_report(evaluations, 'YAKETY_PACK_OUTLIERS_RECOMMENDATIONS.md')

        logger.info(f"\n✓ Outlier evaluation complete!")
        logger.info(f"  - JSON data: {json_path}")
        logger.info(f"  - Report: {md_path}")
        logger.info(f"  - Total evaluated: {len(evaluations)}/{len(videos)}")
    else:
        logger.error("No evaluations completed successfully")


if __name__ == '__main__':
    main()
