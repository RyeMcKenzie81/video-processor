# Viral Video Analysis to Yakety Pack Adaptation Workflow

This document outlines the complete workflow from scraping Instagram data to generating production-ready Yakety Pack video scripts.

---

## Overview

The workflow transforms viral Instagram videos into actionable content recommendations for Yakety Pack (conversation cards for gaming families) through statistical analysis, AI-powered video analysis, and strategic adaptation.

---

## Step 1: Data Collection & Scraping

### Input
- CSV file with Instagram post URLs
- Target: Parenting/family content creators

### Process
```bash
# 1. Import CSV with post URLs to database
python video_processor.py import --csv posts.csv

# This stores:
# - Post URLs
# - Account information
# - Initial metadata
```

### Output
- Posts stored in Supabase `posts` table
- Account data in `accounts` table

---

## Step 2: Statistical Outlier Detection

### Process
```bash
# Calculate outliers (3SD from trimmed mean per account)
python video_processor.py calculate-outliers
```

### What it does
1. **Groups posts by account** - Collects all posts for each creator
2. **Calculates account statistics**:
   - Mean views per account
   - Standard deviation per account
   - Trimmed mean (removes top/bottom 10%)
3. **Identifies outliers**: Posts ≥3 standard deviations above account mean
4. **Saves outlier list** for targeted processing

### Output
- `outliers_to_download.txt` - List of post IDs to process
- Database updated with outlier flags

---

## Step 3: Video Download & Processing

### Process
```bash
# Download only outlier videos
python video_processor.py process --unprocessed-outliers

# Or process all unprocessed videos
python video_processor.py process --unprocessed
```

### What it does
1. **Downloads video files** from Instagram
2. **Extracts audio** for transcription
3. **Generates video frames** for visual analysis
4. **Stores in Supabase Storage**:
   - Original video file
   - Audio file (MP3)
   - Frame images

### Output
- Videos stored in Supabase `videos` bucket
- Processing log in `video_processing_log` table
- Files ready for AI analysis

---

## Step 4: AI-Powered Video Analysis

### Process
```bash
# Analyze all unprocessed videos
python video_processor.py analyze

# Or test with one video
python video_processor.py analyze --test
```

### What Gemini AI analyzes
1. **Hook Analysis** (first 3 seconds):
   - Hook type (problem, curiosity, shock, story, etc.)
   - Hook transcript
   - Emotional impact

2. **Full Video Analysis**:
   - Complete transcript with timestamps
   - Text overlays with timestamps
   - Shot-by-shot storyboard
   - Key moments and timing

3. **Viral Pattern Analysis**:
   - Why it went viral (viral_explanation)
   - Viral factors (hook strength, emotional impact, relatability, etc.)
   - Overall viral score (1-10)

4. **Content Recommendations**:
   - Improvement suggestions
   - What to keep/change
   - Replicability insights

### Output
- Complete analysis in `video_analysis` table:
  - `hook_type`, `hook_transcript`
  - `full_transcript`, `text_overlays`
  - `storyboard`, `key_moments`
  - `viral_factors`, `viral_explanation`
  - `improvement_suggestions`

---

## Step 5: Yakety Pack Adaptation Evaluation

### Process
```bash
# Evaluate all analyzed videos for Yakety Pack potential
python yakety_pack_evaluator.py
```

### What it does
1. **Calculates account statistics** for outlier metrics
2. **For each video, evaluates**:
   - Hook relevance (1-10): Relates to parenting/gaming/communication?
   - Audience match (1-10): Likely to have gaming kids aged 6-15?
   - Transition ease (1-10): Can naturally pivot to Yakety Pack?
   - Viral replicability (1-10): Can we replicate this pattern?

3. **Gemini AI generates**:
   - Overall adaptation score (1-10)
   - Adaptation strategy (150 words)
   - **Complete Yakety Pack adaptation**:
     - Adapted hook (preserves original structure)
     - Full video script (same length/pacing)
     - Shot-by-shot storyboard with timestamps
     - Text overlays with timestamps
   - Transition idea (hook → product)
   - Best use case (gaming_parents, screen_time, etc.)

### Output
- `yakety_pack_evaluations.json` - Complete data for all 104 videos
- `YAKETY_PACK_RECOMMENDATIONS.md` - Top 20 recommendations with full details

---

## Step 6: Review & Select Content

### Manual Process
1. **Open** `YAKETY_PACK_RECOMMENDATIONS.md`
2. **Review top-ranked videos** (sorted by overall_score)
3. **Check outlier status**: Videos with higher σ are more exceptional
4. **Compare**:
   - Original video content (storyboard, transcript, overlays)
   - Yakety Pack adaptation (script, storyboard, overlays)

### Selection Criteria
- Overall score ≥ 7.0 (high potential)
- Hook relevance ≥ 7.0 (strongly relates to target audience)
- High SD from account mean (proven outlier performance)
- Transition ease ≥ 7.0 (natural product integration)

---

## Step 7: Video Production

### For each selected video:

1. **Script** → Use `yakety_pack_full_script` from recommendations
2. **Storyboard** → Follow `yakety_pack_storyboard` shot-by-shot
3. **Text overlays** → Use `yakety_pack_text_overlays` with exact timestamps
4. **Visual style** → Reference original `storyboard` for pacing/energy
5. **Hook** → Record `yakety_pack_hook` exactly as written (preserves viral pattern)

### Production Checklist
- [ ] Script matches recommended length/pacing
- [ ] Shot composition follows storyboard
- [ ] Text overlays appear at specified timestamps
- [ ] Hook captures same emotion/structure as original
- [ ] Transition to product feels natural
- [ ] Call-to-action is clear

---

## File Structure

```
video-processor/
├── video_processor.py              # Main processing script
├── yakety_pack_evaluator.py        # Adaptation evaluation script
├── yakety_pack_evaluations.json    # All evaluations data
├── YAKETY_PACK_RECOMMENDATIONS.md  # Top 20 recommendations
├── logs/                           # Processing & analysis logs
└── .env                            # API keys & credentials
```

---

## Key Data Fields

### video_analysis table
- `hook_type`: Type of hook used
- `hook_transcript`: First 3 seconds transcript
- `full_transcript`: Complete video transcript
- `text_overlays`: JSON with timestamps
- `storyboard`: Shot-by-shot description
- `key_moments`: Important timestamps
- `viral_factors`: Scores for various viral elements
- `viral_explanation`: Why it went viral
- `improvement_suggestions`: Recommendations

### yakety_pack_evaluations.json
- `overall_score`: Adaptation potential (1-10)
- `hook_relevance`, `audience_match`, `transition_ease`, `viral_replicability`: Individual scores
- `sd_from_account_mean`: Standard deviations above account mean
- `adaptation_strategy`: How to adapt the concept
- `yakety_pack_hook`: Adapted hook text
- `yakety_pack_full_script`: Complete video script
- `yakety_pack_storyboard`: Shot-by-shot with timestamps
- `yakety_pack_text_overlays`: On-screen text with timestamps
- `transition_idea`: How to pivot to product
- `best_use_case`: Primary use case category

---

## Example: Top Recommendation Breakdown

### #1. @thenewstepford - Score: 9.8/10
**Outlier:** 12.3σ above account mean

#### Original Video Content
```
Hook Type: problem
Hook Transcript: "Ever feel like you're just talking AT your kids instead of WITH them?"
Views: 2.4M
Original Storyboard: [0:00-0:03] Close-up, frustrated parent face...
```

#### Yakety Pack Adaptation
```
Yakety Pack Hook: "Ever feel like your gaming kid lives in a totally different world?"

Yakety Pack Full Script:
[0:00-0:03] Hook delivery
[0:03-0:08] Problem agitation - "Minecraft this, Roblox that..."
[0:08-0:15] Product introduction - "That's why we created Yakety Pack..."
[0:15-0:25] Benefits showcase - "Turn screen time into quality time..."
[0:25-0:30] Call to action - "Link in bio, $39..."

Yakety Pack Text Overlays:
[0:00] "Ever feel like you're speaking different languages?"
[0:08] "Yakety Pack"
[0:15] "86 conversation cards"
[0:25] "$39 • Link in bio"
```

---

## Workflow Summary

1. **Import CSV** → Posts in database
2. **Calculate outliers** → Identify 3SD videos per account
3. **Download & process** → Videos + audio + frames in storage
4. **AI analysis** → Complete video breakdown with Gemini
5. **Yakety Pack evaluation** → Adaptation scores + complete scripts
6. **Review recommendations** → Select top videos
7. **Produce content** → Follow adapted scripts/storyboards

---

## Success Metrics

- **104 videos analyzed** (100% of outliers)
- **103 successful adaptations** (99% success rate)
- **64 high-potential videos** (score ≥ 7.0)
- **Top 20 production-ready** with complete scripts

---

## Next Steps

1. Review `YAKETY_PACK_RECOMMENDATIONS.md`
2. Select 3-5 top videos to produce first
3. Film following exact scripts/storyboards
4. Test performance and iterate
5. Scale production based on results

---

## Technical Requirements

- Python 3.9+
- Supabase account
- Google Gemini API key
- FFmpeg (for video processing)
- ~50GB storage for 104 videos

---

## Maintenance

### Re-run analysis for new posts
```bash
# 1. Import new CSV
python video_processor.py import --csv new_posts.csv

# 2. Calculate new outliers
python video_processor.py calculate-outliers

# 3. Process new videos
python video_processor.py process --unprocessed-outliers

# 4. Analyze new videos
python video_processor.py analyze

# 5. Evaluate for Yakety Pack
python yakety_pack_evaluator.py
```

### Update existing evaluations
```bash
# Re-evaluate all videos with latest criteria
python yakety_pack_evaluator.py
```

---

**Generated:** October 1, 2025
**Videos Analyzed:** 104
**Success Rate:** 99%
**Production Ready:** Top 20 with complete scripts
