-- Video processing log table
create table if not exists video_processing_log (
  id uuid primary key default gen_random_uuid(),
  post_id uuid references posts(id) on delete cascade,
  status text check (status in ('pending','downloading','downloaded','uploading','completed','failed')),
  error_message text,
  download_url text,
  storage_path text,
  file_size_mb numeric,
  video_duration_sec numeric,
  processing_time_sec numeric,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_video_processing_status on video_processing_log(status);
create index if not exists idx_video_processing_post_id on video_processing_log(post_id);

-- Video analysis table (for Phase 2 - Gemini integration)
create table if not exists video_analysis (
  id uuid primary key default gen_random_uuid(),
  post_id uuid references posts(id) on delete cascade,

  -- Hook analysis (first 3-5 seconds)
  hook_transcript text,
  hook_visual_storyboard jsonb,
  hook_type text,
  hook_timestamp numeric,

  -- Full content extraction
  transcript jsonb,
  text_overlays jsonb,

  -- Visual storyboard (scene-by-scene)
  storyboard jsonb,

  -- Timestamps of key moments
  key_moments jsonb,

  -- Gemini's viral analysis
  viral_factors jsonb,
  viral_explanation text,
  improvement_suggestions text,

  -- Metadata
  analysis_model text default 'gemini-2.5-flash',
  analysis_tokens_used int,
  processing_time_sec numeric,
  created_at timestamptz default now()
);

create index if not exists idx_video_analysis_post_id on video_analysis(post_id);
