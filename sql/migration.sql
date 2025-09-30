-- Migration to add video processing tables
-- Run this if you have an existing database

-- Create video_processing_log table
CREATE TABLE IF NOT EXISTS video_processing_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id uuid REFERENCES posts(id) ON DELETE CASCADE,
  status text CHECK (status IN ('pending','downloading','downloaded','uploading','completed','failed')),
  error_message text,
  download_url text,
  storage_path text,
  file_size_mb numeric,
  video_duration_sec numeric,
  processing_time_sec numeric,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_video_processing_status ON video_processing_log(status);
CREATE INDEX IF NOT EXISTS idx_video_processing_post_id ON video_processing_log(post_id);

-- Create video_analysis table (for Phase 2)
CREATE TABLE IF NOT EXISTS video_analysis (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id uuid REFERENCES posts(id) ON DELETE CASCADE,
  hook_transcript text,
  hook_visual_storyboard jsonb,
  hook_type text,
  hook_timestamp numeric,
  transcript jsonb,
  text_overlays jsonb,
  storyboard jsonb,
  key_moments jsonb,
  viral_factors jsonb,
  viral_explanation text,
  improvement_suggestions text,
  analysis_model text DEFAULT 'gemini-2.5-flash',
  analysis_tokens_used int,
  processing_time_sec numeric,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_video_analysis_post_id ON video_analysis(post_id);
