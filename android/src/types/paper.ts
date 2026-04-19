export interface DailyJob {
  status: 'pending' | 'scraping' | 'rating' | 'done' | 'failed';
  scrape_count: number | null;
  rated_count: number | null;
  kept_count: number | null;
  high_priority_count: number | null;
  started_at: string | null;
  finished_at: string | null;
  error_msg: string | null;
}

export interface Paper {
  arxiv_id: string;
  title: string;
  summary: string;
  url: string;
  pdf_url: string | null;
  authors: string[];
  categories: string[];
  published_date: string | null;
  keep: boolean;
  keep_reason: string | null;
  interest_field: string | null;
  interest_subfield: string | null;
  tldr: string | null;
  tldr_zh: string | null;
  summary_zh: string | null;
  tags: string[];
  relevance_score: number | null;
  quality_score: number | null;
  novelty_claim_score: number | null;
  impact_score: number | null;
  overall_priority_score: number | null;
  tier: string | null;
  high_priority: boolean;
  high_priority_rank: number | null;
  signal_high_keywords: string[];
  signal_notable_authors: string[];
  is_bookmarked: boolean;
}

export interface PapersResponse {
  date: string;
  job: DailyJob | null;
  papers: Paper[];
}
