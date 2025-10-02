#!/usr/bin/env python3
"""
Evaluate viral videos for Yakety Pack content adaptation potential.

This script analyzes each video's hook and content to determine how easily
it could be adapted to promote Yakety Pack (conversation cards for gaming families).
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from supabase import create_client, Client
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/yakety_pack_eval_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize clients
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

YAKETY_PACK_CONTEXT = """
PRODUCT: Yakety Pack - Conversation Cards for Gaming Families

TARGET AUDIENCE: Parents with children aged 6-15 who play video games

KEY PROBLEMS SOLVED:
- Screen time arguments and battles
- Communication gap between parents and gaming kids
- Parents feeling disconnected from their child's gaming interests
- Difficulty having meaningful conversations about games
- Kids who won't talk about their day but will talk about Minecraft

PRODUCT FEATURES:
- 86 conversation cards (66 prompts + 20 design-your-own)
- Color-coded for different emotional depths
- Gaming-specific questions (Minecraft, Roblox, Fortnite, etc.)
- Transforms screen time into quality family time
- Research-backed by child psychology

PRICE: $39 core deck, $59 with expansion

KEY BENEFITS:
- Better parent-child communication
- Understanding your child's gaming world
- Reducing screen time conflicts
- Building emotional intelligence through gaming discussions
"""

EVALUATION_PROMPT = """
You are creating a complete Yakety Pack video adaptation based on a viral video's structure.

ORIGINAL VIDEO ANALYSIS:
Hook Type: {hook_type}
Hook Transcript: {hook_transcript}
Full Transcript: {full_transcript}
Storyboard: {storyboard}
Key Moments: {key_moments}
Caption: {caption}
Viral Explanation: {viral_explanation}
Username: @{username}
Views: {views:,}

{yakety_pack_context}

EVALUATION CRITERIA:

Rate this video on a scale of 1-10 for "Yakety Pack Adaptation Potential" based on:

1. HOOK RELEVANCE (1-10): Does the hook relate to parenting, kids, gaming, screen time,
   communication, family dynamics, or child development?

2. AUDIENCE MATCH (1-10): Is the content creator's audience likely to have gaming kids aged 6-15?

3. TRANSITION EASE (1-10): How naturally could this hook/problem lead into discussing
   Yakety Pack as a solution?

4. VIRAL PATTERN REPLICABILITY (1-10): Could we create a similar hook that's equally
   engaging but transitions to Yakety Pack?

Provide your response in this exact JSON format:
{{
  "overall_score": <1-10 float>,
  "hook_relevance": <1-10 float>,
  "audience_match": <1-10 float>,
  "transition_ease": <1-10 float>,
  "viral_replicability": <1-10 float>,
  "adaptation_strategy": "<150 word explanation of how to adapt this video for Yakety Pack>",
  "yakety_pack_hook": "<Adapt the original hook to relate to gaming/parenting/communication while preserving EXACT structure, pacing, and emotion>",
  "yakety_pack_full_script": "<Complete video script from start to finish, following the same structure and pacing as the original. Include hook, body, and CTA for Yakety Pack>",
  "yakety_pack_storyboard": "<Shot-by-shot visual description matching original's structure. Format: [0:00-0:03] Description\\n[0:03-0:07] Description, etc.>",
  "yakety_pack_text_overlays": "<List all text overlays with timestamps. Format: [0:00] Text here\\n[0:05] Next text, etc.>",
  "transition_idea": "<How to naturally transition from the hook to Yakety Pack in the video>",
  "confidence": "<high|medium|low>",
  "best_use_case": "<gaming_parents|screen_time|communication|family_bonding|other>"
}}

IMPORTANT:
- The yakety_pack_hook should preserve what made the original viral (emotion, structure, pacing)
- yakety_pack_full_script should be the complete video script, same length/structure as original
- yakety_pack_storyboard should have timestamps and match the original's visual pacing
- yakety_pack_text_overlays should include all on-screen text with precise timestamps
"""


def calculate_account_stats():
    """Calculate mean and SD for each account."""
    logger.info("Calculating account statistics...")

    # Get all posts grouped by account
    response = supabase.from_('posts').select('account_id, views').execute()

    account_stats = {}
    account_posts = {}

    for post in response.data:
        account_id = post['account_id']
        views = post.get('views', 0)

        if account_id not in account_posts:
            account_posts[account_id] = []
        account_posts[account_id].append(views)

    # Calculate mean and SD for each account
    for account_id, views_list in account_posts.items():
        if len(views_list) > 1:
            mean = sum(views_list) / len(views_list)
            variance = sum((x - mean) ** 2 for x in views_list) / len(views_list)
            sd = variance ** 0.5
            account_stats[account_id] = {'mean': mean, 'sd': sd}
        else:
            account_stats[account_id] = {'mean': views_list[0] if views_list else 0, 'sd': 0}

    return account_stats


def get_all_videos() -> List[Dict]:
    """Fetch all analyzed videos from Supabase."""
    logger.info("Fetching all analyzed videos...")

    response = supabase.from_('video_analysis').select(
        """
        *,
        posts(
            id,
            post_url,
            post_id,
            caption,
            views,
            account_id,
            accounts(handle)
        )
        """
    ).execute()

    logger.info(f"Retrieved {len(response.data)} videos")
    return response.data


def evaluate_video(video: Dict, account_stats: Dict = None) -> Optional[Dict]:
    """Evaluate a single video for Yakety Pack adaptation potential."""
    post_id = video['post_id']
    username = video['posts']['accounts']['handle'] if video['posts']['accounts'] else 'unknown'

    # Calculate SD from account mean if stats provided
    sd_from_mean = None
    if account_stats and video['posts'].get('account_id'):
        account_id = video['posts']['account_id']
        views = video['posts'].get('views', 0)

        if account_id in account_stats:
            stats = account_stats[account_id]
            if stats['sd'] > 0:
                sd_from_mean = (views - stats['mean']) / stats['sd']

    logger.info(f"Evaluating video {post_id} from @{username}")

    try:
        # Prepare prompt with full video data
        prompt = EVALUATION_PROMPT.format(
            hook_type=video.get('hook_type') or 'N/A',
            hook_transcript=video.get('hook_transcript') or 'N/A',
            full_transcript=video.get('full_transcript') or 'N/A',
            storyboard=video.get('storyboard') or 'N/A',
            key_moments=video.get('key_moments') or 'N/A',
            caption=video['posts'].get('caption') or 'N/A',
            viral_explanation=video.get('viral_explanation') or 'N/A',
            username=username,
            views=video['posts'].get('views', 0),
            yakety_pack_context=YAKETY_PACK_CONTEXT
        )

        # Call Gemini API
        model = genai.GenerativeModel(os.getenv('GEMINI_MODEL', 'models/gemini-flash-latest'))
        response = model.generate_content(prompt)

        # Parse JSON response
        response_text = response.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]

        evaluation = json.loads(response_text.strip())

        # Add metadata and original video data
        evaluation['post_id'] = post_id
        evaluation['username'] = username
        evaluation['views'] = video['posts'].get('views', 0)
        evaluation['sd_from_account_mean'] = sd_from_mean
        evaluation['post_url'] = video['posts'].get('post_url')
        evaluation['caption'] = video['posts'].get('caption')
        evaluation['original_hook_type'] = video.get('hook_type')
        evaluation['original_hook_transcript'] = video.get('hook_transcript')
        evaluation['original_transcript'] = video.get('full_transcript')
        evaluation['original_storyboard'] = video.get('storyboard')
        evaluation['original_key_moments'] = video.get('key_moments')
        evaluation['original_text_overlays'] = video.get('text_overlays')
        evaluation['evaluated_at'] = datetime.now().isoformat()

        logger.info(f"✓ Evaluated {post_id}: Overall Score = {evaluation['overall_score']:.1f}/10")
        return evaluation

    except Exception as e:
        logger.error(f"✗ Failed to evaluate {post_id}: {e}")
        return None


def save_evaluations(evaluations: List[Dict], output_file: str = 'yakety_pack_evaluations.json'):
    """Save all evaluations to JSON file."""
    output_path = os.path.join(os.path.dirname(__file__), output_file)

    # Sort by overall score descending
    sorted_evals = sorted(evaluations, key=lambda x: x['overall_score'], reverse=True)

    output_data = {
        'generated_at': datetime.now().isoformat(),
        'total_videos': len(sorted_evals),
        'evaluations': sorted_evals,
        'summary': {
            'high_potential': len([e for e in sorted_evals if e['overall_score'] >= 7]),
            'medium_potential': len([e for e in sorted_evals if 4 <= e['overall_score'] < 7]),
            'low_potential': len([e for e in sorted_evals if e['overall_score'] < 4]),
            'top_10': sorted_evals[:10]
        }
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    logger.info(f"Saved evaluations to {output_path}")
    return output_path


def generate_markdown_report(evaluations: List[Dict], output_file: str = 'YAKETY_PACK_RECOMMENDATIONS.md'):
    """Generate a markdown report with top recommendations."""
    output_path = os.path.join(os.path.dirname(__file__), output_file)

    # Sort by overall score
    sorted_evals = sorted(evaluations, key=lambda x: x['overall_score'], reverse=True)
    top_20 = sorted_evals[:20]

    with open(output_path, 'w') as f:
        f.write("# Yakety Pack Video Adaptation Recommendations\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n")
        f.write(f"**Total Videos Analyzed:** {len(evaluations)}\n\n")

        f.write("## Summary\n\n")
        high = len([e for e in evaluations if e['overall_score'] >= 7])
        medium = len([e for e in evaluations if 4 <= e['overall_score'] < 7])
        low = len([e for e in evaluations if e['overall_score'] < 4])

        f.write(f"- **High Potential (7-10):** {high} videos\n")
        f.write(f"- **Medium Potential (4-6.9):** {medium} videos\n")
        f.write(f"- **Low Potential (1-3.9):** {low} videos\n\n")

        f.write("## Top 20 Videos for Yakety Pack Adaptation\n\n")

        for i, eval in enumerate(top_20, 1):
            f.write(f"### #{i}. @{eval['username']} - Score: {eval['overall_score']:.1f}/10\n\n")

            # Add SD from account mean if available
            sd_info = ""
            if eval.get('sd_from_account_mean') is not None:
                sd_info = f" | **Outlier:** {eval['sd_from_account_mean']:.1f}σ above account mean"

            f.write(f"**Views:** {eval['views']:,} | **Hook Type:** {eval['original_hook_type']}{sd_info}\n\n")

            if eval.get('post_url'):
                f.write(f"**Original Video:** {eval['post_url']}\n\n")

            f.write(f"**Scores:**\n")
            f.write(f"- Hook Relevance: {eval['hook_relevance']:.1f}/10\n")
            f.write(f"- Audience Match: {eval['audience_match']:.1f}/10\n")
            f.write(f"- Transition Ease: {eval['transition_ease']:.1f}/10\n")
            f.write(f"- Viral Replicability: {eval['viral_replicability']:.1f}/10\n\n")

            # Original video content
            f.write(f"---\n\n")
            f.write(f"#### ORIGINAL VIDEO CONTENT\n\n")

            if eval.get('caption'):
                f.write(f"**Original Caption:**\n{eval['caption']}\n\n")

            if eval.get('original_hook_transcript'):
                f.write(f"**Original Hook Transcript:**\n> {eval['original_hook_transcript']}\n\n")

            if eval.get('original_key_moments'):
                f.write(f"**Original Key Moments:**\n{eval['original_key_moments']}\n\n")

            if eval.get('original_storyboard'):
                f.write(f"**Original Storyboard:**\n{eval['original_storyboard']}\n\n")

            if eval.get('original_transcript'):
                f.write(f"**Original Full Transcript:**\n{eval['original_transcript']}\n\n")

            if eval.get('original_text_overlays'):
                f.write(f"**Original Text Overlays:**\n{eval['original_text_overlays']}\n\n")

            # Yakety Pack adaptation
            f.write(f"---\n\n")
            f.write(f"#### YAKETY PACK ADAPTATION\n\n")
            f.write(f"**Adaptation Strategy:**\n{eval['adaptation_strategy']}\n\n")

            if eval.get('yakety_pack_hook'):
                f.write(f"**Yakety Pack Hook:**\n> {eval['yakety_pack_hook']}\n\n")

            if eval.get('yakety_pack_full_script'):
                f.write(f"**Yakety Pack Full Script:**\n```\n{eval['yakety_pack_full_script']}\n```\n\n")

            if eval.get('yakety_pack_storyboard'):
                f.write(f"**Yakety Pack Storyboard:**\n```\n{eval['yakety_pack_storyboard']}\n```\n\n")

            if eval.get('yakety_pack_text_overlays'):
                f.write(f"**Yakety Pack Text Overlays:**\n```\n{eval['yakety_pack_text_overlays']}\n```\n\n")

            f.write(f"**Transition Idea:**\n{eval['transition_idea']}\n\n")
            f.write(f"**Best Use Case:** {eval['best_use_case']}\n\n")
            f.write("---\n\n")

    logger.info(f"Generated markdown report: {output_path}")
    return output_path


def main():
    """Main execution function."""
    logger.info("Starting Yakety Pack video evaluation...")

    # Calculate account statistics
    account_stats = calculate_account_stats()

    # Get all videos
    videos = get_all_videos()

    # Evaluate each video
    evaluations = []
    for video in videos:
        eval_result = evaluate_video(video, account_stats)
        if eval_result:
            evaluations.append(eval_result)

    # Save results
    if evaluations:
        json_path = save_evaluations(evaluations)
        md_path = generate_markdown_report(evaluations)

        logger.info(f"\n✓ Evaluation complete!")
        logger.info(f"  - JSON data: {json_path}")
        logger.info(f"  - Report: {md_path}")
        logger.info(f"  - Total evaluated: {len(evaluations)}/{len(videos)}")
    else:
        logger.error("No evaluations completed successfully")


if __name__ == '__main__':
    main()
