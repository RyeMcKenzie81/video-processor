#!/usr/bin/env python3
"""
Aggregate Video Analysis using Gemini AI
Analyzes patterns across all viral videos to extract key insights.
"""

import os
import json
import logging
from typing import Dict, List
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client

# Load environment
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-flash-latest")

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def get_all_analyses() -> List[Dict]:
    """Fetch all video analyses from database."""
    logger.info("Fetching all video analyses from database")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Get all analyses with post data
    result = supabase.table("video_analysis").select(
        """
        *,
        posts(
            id,
            caption,
            views,
            accounts(handle)
        )
        """
    ).execute()

    logger.info(f"Found {len(result.data)} analyses")
    return result.data


def prepare_aggregate_data(analyses: List[Dict]) -> Dict:
    """Prepare data for aggregate analysis."""
    logger.info("Preparing aggregate data")

    # Extract key data points
    aggregate = {
        "total_videos": len(analyses),
        "hook_types": {},
        "viral_factors": {
            "hook_strength": [],
            "emotional_impact": [],
            "relatability": [],
            "novelty": [],
            "production_quality": [],
            "pacing": [],
            "overall_score": []
        },
        "videos_sample": []
    }

    # Process each analysis
    for analysis in analyses:
        # Hook types
        hook_type = analysis.get("hook_type", "unknown")
        aggregate["hook_types"][hook_type] = aggregate["hook_types"].get(hook_type, 0) + 1

        # Viral factors
        if analysis.get("viral_factors"):
            try:
                factors = json.loads(analysis["viral_factors"])
                for key in aggregate["viral_factors"].keys():
                    if key in factors:
                        aggregate["viral_factors"][key].append(factors[key])
            except:
                pass

        # Sample data (first 20 for context)
        if len(aggregate["videos_sample"]) < 20:
            post_data = analysis.get("posts", {})
            aggregate["videos_sample"].append({
                "username": post_data.get("accounts", {}).get("handle", "unknown"),
                "views": post_data.get("views", 0),
                "hook_type": hook_type,
                "hook_transcript": analysis.get("hook_transcript", ""),
                "viral_explanation": analysis.get("viral_explanation", "")[:200] + "..." if analysis.get("viral_explanation") else ""
            })

    # Calculate averages
    factor_stats = {}
    for key, values in list(aggregate["viral_factors"].items()):
        if values:
            factor_stats[f"{key}_avg"] = sum(values) / len(values)
            factor_stats[f"{key}_min"] = min(values)
            factor_stats[f"{key}_max"] = max(values)

    aggregate["viral_factors"].update(factor_stats)

    return aggregate


def create_aggregate_prompt(data: Dict) -> str:
    """Create prompt for aggregate analysis."""

    prompt = f"""You are analyzing {data['total_videos']} viral Instagram videos to identify patterns and insights for content creators.

**AGGREGATE DATA:**

**Hook Types Distribution:**
{json.dumps(data['hook_types'], indent=2)}

**Viral Factors Averages:**
{json.dumps({k: v for k, v in data['viral_factors'].items() if '_avg' in k}, indent=2)}

**Sample Videos (showing 20 of {data['total_videos']}):**
{json.dumps(data['videos_sample'], indent=2)}

**YOUR TASK:**
Provide a comprehensive aggregate analysis in JSON format:

{{
  "key_findings": {{
    "most_effective_hook_types": [
      {{
        "type": "problem",
        "frequency": 35,
        "effectiveness": "High - creates immediate relatability and urgency",
        "example": "Brief example from data"
      }}
    ],
    "viral_factor_insights": {{
      "highest_scoring_factor": "relatability",
      "average_score": 8.5,
      "key_insight": "What this tells us about viral content"
    }},
    "common_patterns": [
      "Pattern 1: Describe what successful videos have in common",
      "Pattern 2: Another common element"
    ]
  }},

  "hook_strategy_analysis": {{
    "winning_formulas": [
      {{
        "formula": "Describe the pattern",
        "why_it_works": "Psychological/emotional reason",
        "example_hooks": ["Example 1", "Example 2"]
      }}
    ],
    "hook_timing": "Insights about hook length and pacing"
  }},

  "content_recommendations": {{
    "for_beginners": [
      "Actionable recommendation 1",
      "Actionable recommendation 2"
    ],
    "for_experienced_creators": [
      "Advanced technique 1",
      "Advanced technique 2"
    ],
    "universal_principles": [
      "Principle that works across all content"
    ]
  }},

  "viral_factor_breakdown": {{
    "emotional_impact": {{
      "average_score": 8.5,
      "best_practices": ["How to maximize emotional impact"],
      "common_mistakes": ["What to avoid"]
    }},
    "relatability": {{
      "average_score": 9.0,
      "best_practices": ["How to increase relatability"],
      "common_mistakes": ["What to avoid"]
    }}
    // ... for each viral factor
  }},

  "content_categories": {{
    "parenting_content": {{
      "characteristics": ["What makes parenting content viral"],
      "best_hook_types": ["Hook types that work best"],
      "key_themes": ["Common themes"]
    }}
    // ... for each major category found
  }},

  "actionable_insights": {{
    "immediate_wins": [
      "Quick changes creators can make today"
    ],
    "strategic_improvements": [
      "Longer-term content strategy changes"
    ],
    "content_gaps": [
      "Opportunities not being exploited"
    ]
  }},

  "executive_summary": "3-4 sentences summarizing the most important findings and recommendations"
}}

**GUIDELINES:**
- Be specific and data-driven
- Provide actionable insights, not just observations
- Identify patterns that creators can replicate
- Note any surprising or counterintuitive findings
- Consider the target audience (parents, based on sample data)
- Highlight what differentiates viral content from average content

Provide ONLY the JSON response, no additional text."""

    return prompt


def analyze_aggregate_patterns(data: Dict) -> Dict:
    """Use Gemini to analyze aggregate patterns."""
    logger.info("Analyzing aggregate patterns with Gemini")

    # Configure Gemini
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    # Create prompt
    prompt = create_aggregate_prompt(data)

    # Generate analysis
    logger.info("Sending to Gemini for analysis...")
    response = model.generate_content(prompt)

    # Parse response
    response_text = response.text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]

    analysis = json.loads(response_text.strip())

    logger.info("Aggregate analysis complete")
    return analysis


def save_aggregate_analysis(analysis: Dict, raw_data: Dict):
    """Save aggregate analysis to file and database."""
    logger.info("Saving aggregate analysis")

    # Save to JSON file
    output = {
        "aggregate_data": raw_data,
        "ai_analysis": analysis,
        "metadata": {
            "total_videos": raw_data["total_videos"],
            "analysis_model": GEMINI_MODEL
        }
    }

    output_file = "aggregate_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    logger.info(f"Aggregate analysis saved to {output_file}")

    # Also save a readable markdown version
    md_file = "AGGREGATE_INSIGHTS.md"
    with open(md_file, 'w') as f:
        f.write("# Viral Video Analysis: Aggregate Insights\n\n")
        f.write(f"**Total Videos Analyzed:** {raw_data['total_videos']}\n\n")

        f.write("## Executive Summary\n\n")
        f.write(f"{analysis.get('executive_summary', 'N/A')}\n\n")

        f.write("## Key Findings\n\n")
        key_findings = analysis.get('key_findings', {})

        f.write("### Most Effective Hook Types\n\n")
        for hook in key_findings.get('most_effective_hook_types', []):
            f.write(f"**{hook['type'].title()}** ({hook['frequency']} videos)\n")
            f.write(f"- {hook['effectiveness']}\n")
            f.write(f"- Example: \"{hook.get('example', 'N/A')}\"\n\n")

        f.write("### Common Patterns\n\n")
        for pattern in key_findings.get('common_patterns', []):
            f.write(f"- {pattern}\n")
        f.write("\n")

        f.write("## Hook Strategy Analysis\n\n")
        hook_strategy = analysis.get('hook_strategy_analysis', {})
        for formula in hook_strategy.get('winning_formulas', []):
            f.write(f"### {formula['formula']}\n\n")
            f.write(f"**Why it works:** {formula['why_it_works']}\n\n")
            f.write("**Examples:**\n")
            for example in formula.get('example_hooks', []):
                f.write(f"- \"{example}\"\n")
            f.write("\n")

        f.write("## Content Recommendations\n\n")
        recommendations = analysis.get('content_recommendations', {})

        f.write("### For Beginners\n\n")
        for rec in recommendations.get('for_beginners', []):
            f.write(f"- {rec}\n")
        f.write("\n")

        f.write("### For Experienced Creators\n\n")
        for rec in recommendations.get('for_experienced_creators', []):
            f.write(f"- {rec}\n")
        f.write("\n")

        f.write("### Universal Principles\n\n")
        for principle in recommendations.get('universal_principles', []):
            f.write(f"- {principle}\n")
        f.write("\n")

        f.write("## Actionable Insights\n\n")
        insights = analysis.get('actionable_insights', {})

        f.write("### Immediate Wins\n\n")
        for win in insights.get('immediate_wins', []):
            f.write(f"- {win}\n")
        f.write("\n")

        f.write("### Strategic Improvements\n\n")
        for improvement in insights.get('strategic_improvements', []):
            f.write(f"- {improvement}\n")
        f.write("\n")

        f.write("### Content Gaps (Opportunities)\n\n")
        for gap in insights.get('content_gaps', []):
            f.write(f"- {gap}\n")
        f.write("\n")

    logger.info(f"Readable insights saved to {md_file}")


def main():
    """Main execution."""
    logger.info("Starting aggregate video analysis")

    # Fetch all analyses
    analyses = get_all_analyses()

    if not analyses:
        logger.error("No analyses found in database")
        return

    # Prepare aggregate data
    aggregate_data = prepare_aggregate_data(analyses)

    # Analyze patterns with Gemini
    analysis = analyze_aggregate_patterns(aggregate_data)

    # Save results
    save_aggregate_analysis(analysis, aggregate_data)

    logger.info("Aggregate analysis complete!")
    print("\n" + "="*80)
    print("AGGREGATE ANALYSIS COMPLETE")
    print("="*80)
    print(f"Total videos analyzed: {aggregate_data['total_videos']}")
    print(f"\nResults saved to:")
    print("  - aggregate_analysis.json (full data)")
    print("  - AGGREGATE_INSIGHTS.md (readable summary)")
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
