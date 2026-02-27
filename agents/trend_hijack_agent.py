"""
trend_hijack_agent.py — Trend Intelligence & Content Engine

Place this file at: mic-growth-engine/agents/trend_hijack_agent.py

HOW IT WORKS:
  1. Fetches current trending topics (from Apify or mock data in dev)
  2. Sends top 10 trends to Gemini — asks it to rate each trend 1-10
     for how naturally it connects to audio/creator niche
  3. For trends scoring ≥ 7, drafts creative posts that tie the trend
     to MIC's content and expertise
  4. Saves output to data/trend_analysis_YYYY-MM-DD.json

EXAMPLE:
  Trend: "Penguin viral video"
  Score: 8/10
  Angle: Penguins communicate via clicks across 100Hz-16kHz — the exact range
         you're capturing with your SM7B. Nature built the first podcast mic.
  Draft: "A penguin's vocal range beats most $50 USB mics on frequency response."
"""

import os
import json
import time
import requests
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv
from agents.gemini_utils import gemini_with_retry

load_dotenv()


class TrendHijackAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("[FAIL] GEMINI_API_KEY missing from .env")
        self.client = genai.Client(api_key=api_key)

        self.apify_token = os.getenv("APIFY_API_TOKEN")
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.output_file = f"data/trend_analysis_{self.today}.json"

        self.brand_voice = self._load_brand_voice()
        self.score_threshold = self.brand_voice.get("trend_score_threshold", 7)

    def _load_brand_voice(self):
        try:
            with open("config/brand_voice.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print("[WARN] config/brand_voice.json not found.")
            return {}

    # ─────────────────────────────────────────────
    # MAIN RUN
    # ─────────────────────────────────────────────

    def run(self, mock_mode=True):
        print(f"[TRENDS] Trend Hijack Agent active. Score threshold: {self.score_threshold}/10")

        # Step 1: Get trending topics
        trends = self._get_trends(mock=mock_mode)
        print(f"[TRENDS] Fetched {len(trends)} trending topics.")

        # Step 2: Score each trend for audio/creator niche relevance
        scored_trends = self._score_trends(trends)

        # Step 3: Filter to threshold
        approved = [t for t in scored_trends if t.get("score", 0) >= self.score_threshold]
        rejected = [t for t in scored_trends if t.get("score", 0) < self.score_threshold]

        print(f"[TRENDS] {len(approved)} trends approved (score ≥ {self.score_threshold}), "
              f"{len(rejected)} rejected.")

        # Step 4: Draft posts for approved trends
        for trend in approved:
            print(f"[TRENDS] Drafting post for: {trend['topic']} (score: {trend['score']})")
            try:
                trend["draft"] = self._draft_trend_post(trend)
                trend["status"] = "draft_ready"
                time.sleep(2)
            except Exception as e:
                print(f"[FAIL] Could not draft for '{trend['topic']}': {e}")
                trend["draft"] = None
                trend["status"] = "draft_failed"

        for trend in rejected:
            trend["status"] = "rejected_low_score"
            trend["draft"] = None

        result = {
            "generated_at": self.today,
            "total_trends_analyzed": len(scored_trends),
            "approved_count": len(approved),
            "approved": approved,
            "rejected": rejected,
        }

        self._save(result)
        return result

    # ─────────────────────────────────────────────
    # TREND FETCHING
    # ─────────────────────────────────────────────

    def _get_trends(self, mock=True):
        if mock:
            return self._mock_trends()

        if not self.apify_token:
            print("[WARN] No APIFY_API_TOKEN — cannot fetch live trends. Using mock.")
            return self._mock_trends()

        # Apify Twitter trending topics scraper
        url = (
            f"https://api.apify.com/v2/acts/fastcrawler~x-twitter-trends-scraper-2025/run-sync-get-dataset-items"
            f"?token={self.apify_token}&timeout=60&memory=256"
        )
        payload = {"country": "United States", "maxItems": 15}

        try:
            response = requests.post(url, json=payload, timeout=60,
                                     headers={"Content-Type": "application/json"})
            response.raise_for_status()
            raw = response.json()
            return [
                {
                    "topic":       item.get("name", ""),
                    "tweet_count": item.get("tweetCount", 0),
                    "category":    item.get("category", ""),
                }
                for item in raw
            ]
        except Exception as e:
            print(f"[FAIL] Could not fetch live trends: {e}. Using mock data.")
            return self._mock_trends()

    def _mock_trends(self):
        """Mock trends for development — includes viral events, pop culture, tech topics."""
        return [
            {"topic": "Penguin viral video", "tweet_count": 580000, "category": "Animals"},
            {"topic": "Apple M4 MacBook", "tweet_count": 340000, "category": "Technology"},
            {"topic": "Spotify layoffs", "tweet_count": 210000, "category": "Business"},
            {"topic": "Super Bowl halftime show", "tweet_count": 890000, "category": "Entertainment"},
            {"topic": "Tesla Cybertruck recall", "tweet_count": 450000, "category": "Automotive"},
            {"topic": "Sabrina Carpenter new album", "tweet_count": 720000, "category": "Music"},
            {"topic": "ChatGPT voice mode", "tweet_count": 390000, "category": "Technology"},
            {"topic": "NBA trade deadline", "tweet_count": 540000, "category": "Sports"},
            {"topic": "ASMR YouTube ban", "tweet_count": 180000, "category": "Creator Economy"},
            {"topic": "Home recording tips", "tweet_count": 45000, "category": "Audio"},
        ]

    # ─────────────────────────────────────────────
    # SCORING
    # ─────────────────────────────────────────────

    def _score_trends(self, trends):
        """Ask Gemini to score each trend for audio/creator niche relevance."""
        brand_name  = self.brand_voice.get("brand_name", "MIC")
        niche       = self.brand_voice.get("niche", "audio technology, podcast equipment")
        pillars     = ", ".join(self.brand_voice.get("content_pillars", []))
        trend_list  = "\n".join(f"{i+1}. {t['topic']} ({t.get('tweet_count', 0):,} tweets)" 
                                for i, t in enumerate(trends))

        prompt = f"""
You are a creative content strategist for {brand_name}, a brand in {niche}.
Our content pillars are: {pillars}

Here are today's trending topics:
{trend_list}

TASK: For each trend, find a creative angle that connects it to audio technology, 
microphones, podcast equipment, studio recording, or creator culture.

Rate each trend 1-10:
- 9-10: Natural, obvious connection. Will resonate strongly.
- 7-8: Creative but believable connection. Worth posting.
- 5-6: Forced connection. Only post if it's very clever.
- 1-4: No meaningful connection. Skip.

Respond ONLY in valid JSON array format, no markdown, no explanation:
[
  {{
    "topic": "exact trend name",
    "score": 8,
    "angle": "The creative connection to audio/creator world in 1-2 sentences",
    "hook": "A specific tweet hook (under 280 chars) that uses this trend"
  }}
]
"""
        try:
            raw_response = gemini_with_retry(
                self.client,
                lambda model: self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.7)
                ).text.strip()
            )

            # Clean JSON response
            clean = raw_response.replace("```json", "").replace("```", "").strip()
            scored = json.loads(clean)

            # Merge scores back into original trend data
            scored_dict = {s["topic"]: s for s in scored}
            result = []
            for trend in trends:
                topic = trend["topic"]
                if topic in scored_dict:
                    merged = {**trend, **scored_dict[topic]}
                else:
                    merged = {**trend, "score": 0, "angle": "", "hook": ""}
                result.append(merged)

            return sorted(result, key=lambda t: t.get("score", 0), reverse=True)

        except Exception as e:
            print(f"[FAIL] Trend scoring failed: {e}")
            # Return all trends with score 0 so they get rejected
            return [{**t, "score": 0, "angle": "", "hook": ""} for t in trends]

    # ─────────────────────────────────────────────
    # DRAFTING
    # ─────────────────────────────────────────────

    def _draft_trend_post(self, trend):
        brand_name = self.brand_voice.get("brand_name", "MIC")
        tone_adj   = ", ".join(self.brand_voice.get("tone", {}).get("adjectives", ["direct", "technical"]))
        never_do   = ", ".join(self.brand_voice.get("tone", {}).get("never_do", [])[:3])
        examples   = "\n".join(f'"{e}"' for e in self.brand_voice.get("example_posts", [])[:2])

        system = f"""
You are writing for {brand_name}. Voice: {tone_adj}.
Never: {never_do}.

Voice examples:
{examples}

Write a Twitter post that:
1. Hooks with the trending topic in the FIRST line
2. Pivots naturally to an audio/creator insight in line 2
3. The connection must feel clever, not forced
4. Under 280 characters OR a 3-tweet thread
5. No emojis unless they serve the joke
6. Strong opinion or surprising fact — not a generic take
"""
        content = (
            f"Trending topic: {trend['topic']}\n"
            f"Creative angle: {trend['angle']}\n"
            f"Suggested hook: {trend['hook']}"
        )

        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model,
            contents=content,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.8)
        ).text.strip())

    # ─────────────────────────────────────────────
    # SAVE
    # ─────────────────────────────────────────────

    def _save(self, result):
        os.makedirs("data", exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        print(f"[SAVED] Trend analysis → {self.output_file}")


if __name__ == "__main__":
    agent = TrendHijackAgent()
    agent.run(mock_mode=True)