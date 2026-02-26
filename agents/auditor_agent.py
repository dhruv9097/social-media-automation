import os
import json
import statistics
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

ACTOR_ID = "apidojo/twitter-scraper-lite"  # Twitter Scraper Unlimited: event-based pricing, ~$0.05/50 tweets

# ── Mock competitor benchmarks ────────────────────────────────────────────────
MOCK_BENCHMARKS = {
    "rodemics": {
        "avg_likes_per_tweet":   847,
        "avg_replies_per_tweet": 34,
        "top_performing_tweet":  "Introducing the Rode Wireless Pro -- 32-bit float recording, timecode sync, and 260m range. This changes everything for run-and-gun audio.",
    },
    "shure": {
        "avg_likes_per_tweet":   1203,
        "avg_replies_per_tweet": 89,
        "top_performing_tweet":  "The SM7B turns 50 this year. Still the gold standard. Some things don't need to be reinvented.",
    },
    "mkbhd": {
        "avg_likes_per_tweet":   18420,
        "avg_replies_per_tweet": 1204,
        "top_performing_tweet":  "Audio quality is the #1 thing that makes people stop watching. Bad video is forgiven. Bad audio is not.",
    },
    "podcastage": {
        "avg_likes_per_tweet":   312,
        "avg_replies_per_tweet": 28,
        "top_performing_tweet":  "Tested 47 USB mics under $100. Only 3 are worth your money. Full breakdown in the video.",
    },
    "elgato": {
        "avg_likes_per_tweet":   2104,
        "avg_replies_per_tweet": 176,
        "top_performing_tweet":  "Wave Neo -- studio-quality audio for streamers who don't want to deal with audio interfaces.",
    },
}

# ── Mock unanswered questions (content gaps) ──────────────────────────────────
MOCK_QUESTIONS = [
    "Does the SM7B really need a Cloudlifter or is that overkill for a Focusrite Scarlett?",
    "What's the actual difference between XLR and USB mics for a beginner podcast setup?",
    "Can you record a podcast remotely with Rode Wireless Pro without losing sync?",
    "Is the Rode PodMic worth it over just getting an AT2020 at half the price?",
    "Why does my SM7B sound thin even after EQ? Is it my interface gain?",
    "Best budget interface for SM7B that doesn't need a Cloudlifter?",
    "What mic do professional audiobook narrators actually use?",
    "Is wireless audio for podcasting ever actually broadcast quality?",
]

class AuditorAgent:
    def __init__(self):
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise ValueError("[FAIL] GEMINI_API_KEY is missing from your .env file.")

        self.client      = genai.Client(api_key=gemini_key)
        self.heavy_model = "gemini-2.5-flash"

        self.today         = datetime.now().strftime("%Y-%m-%d")
        self.report_file   = f"data/competitor_report_{self.today}.json"
        self.spy_data_file = f"data/raw_tweets_{self.today}.json"

        # Only init Apify if we'll use it
        self._apify_ready = False
        apify_token = os.getenv("APIFY_API_TOKEN")
        if apify_token:
            try:
                from apify_client import ApifyClient
                self.apify_client = ApifyClient(apify_token)
                self.actor_id     = ACTOR_ID
                self._apify_ready = True
            except ImportError:
                print("[WARN] apify_client not installed. Mock mode only.")

        settings_path = "data/target_settings.json"
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
                self.competitors = settings.get("competitors", [])
                print(f"[OK] Loaded {len(self.competitors)} competitors: {self.competitors}")
        except FileNotFoundError:
            print("[WARN] target_settings.json not found. Using defaults.")
            self.competitors = ["mkbhd"]

    def _normalize(self, item: dict) -> dict:
        author_obj = item.get("author", item.get("user", {}))
        return {
            "id":      str(item.get("id", item.get("tweet_id", ""))),
            "text":    item.get("text", item.get("full_text", "")),
            "likes":   item.get("likeCount",  item.get("favorite_count", item.get("likes", 0))),
            "replies": item.get("replyCount", item.get("reply_count",    item.get("replies", 0))),
            "author":  author_obj.get("userName", author_obj.get("screen_name", "unknown")),
        }

    def run_full_audit(self, mock_mode=False):
        """
        mock_mode=True  → uses built-in mock data (no Apify credits consumed)
        mock_mode=False → calls Apify live (requires paid plan + credits)
        """
        print("[AUDITOR] Auditor Agent active. Initiating Phase 1 & 2 protocols...")

        if mock_mode:
            benchmarks = self._mock_benchmarks()
            gaps       = self._mock_content_gaps()
        else:
            benchmarks = self._audit_competitors_live()
            gaps       = self._find_content_gaps_live()

        trends = self._monitor_daily_trends()   # Always reads spy data file — no Apify call

        report = {
            "date":                  self.today,
            "competitor_benchmarks": benchmarks,
            "content_gaps":          gaps,
            "daily_trends":          trends,
            "mock_mode":             mock_mode,
        }

        self._save_report(report)
        print("[OK] Comprehensive Competitor & Trend Audit Complete.")
        return report

    # ── Mock methods ──────────────────────────────────────────────────────────

    def _mock_benchmarks(self):
        print("   -> [MOCK] Injecting competitor benchmark data...")
        # Filter to only tracked competitors
        result = {k: v for k, v in MOCK_BENCHMARKS.items() if k in self.competitors}
        for name in result:
            print(f"   [OK] Mock benchmark loaded for @{name}")
        return result

    def _mock_content_gaps(self):
        print("   -> [MOCK] Analysing mock unanswered questions with Gemini...")
        system_prompt = """
        You are an elite social media strategist. I will provide a list of raw questions 
        that users asked top tech influencers.
        Identify the 3 most common themes or most painful problems in these questions.
        Return ONLY a clean, bulleted list of 3 highly specific video/thread topics 
        we should create to fill this gap.
        """
        try:
            response = self.client.models.generate_content(
                model=self.heavy_model,
                contents=f"Raw Questions: {json.dumps(MOCK_QUESTIONS)}",
                config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.3),
            )
            result = response.text.strip()
            print("   [OK] Gap analysis complete.")
            return result
        except Exception as e:
            print(f"   [FAIL] Gemini gap analysis error: {type(e).__name__}: {e}")
            return "- Interface gain requirements for dynamic mics (SM7B + Cloudlifter debate)\n- XLR vs USB mic decision guide for new podcasters\n- Remote podcast recording quality with wireless mics"

    # ── Live methods ──────────────────────────────────────────────────────────

    def _audit_competitors_live(self):
        print("   -> Benchmarking competitor engagement (LIVE)...")
        benchmarks = {}
        if not self._apify_ready:
            print("   [FAIL] Apify not ready. Use mock_mode=True.")
            return benchmarks

        queries = [f"from:{c}" for c in self.competitors]
        run_input = {"searchTerms": queries, "maxItems": 50, "sort": "Latest", "tweetLanguage": "en"}

        try:
            run = self.apify_client.actor(self.actor_id).call(run_input=run_input)
            if not run or "defaultDatasetId" not in run:
                print("   [FAIL] Apify returned no dataset.")
                return benchmarks

            items = list(self.apify_client.dataset(run["defaultDatasetId"]).iterate_items())
            print(f"   -> Received {len(items)} raw tweets.")

            for target in self.competitors:
                tweets = [self._normalize(i) for i in items if self._normalize(i)["author"].lower() == target.lower()]
                if not tweets:
                    print(f"   [WARN] No tweets for @{target}")
                    continue
                likes   = [t["likes"]   for t in tweets]
                replies = [t["replies"] for t in tweets]
                benchmarks[target] = {
                    "avg_likes_per_tweet":   round(statistics.mean(likes)),
                    "avg_replies_per_tweet": round(statistics.mean(replies)),
                    "top_performing_tweet":  max(tweets, key=lambda x: x["likes"])["text"],
                }
        except Exception as e:
            print(f"   [FAIL] Competitor audit error: {type(e).__name__}: {e}")

        return benchmarks

    def _find_content_gaps_live(self):
        print("   -> Extracting content gaps (LIVE)...")
        if not self._apify_ready:
            print("   [FAIL] Apify not ready. Use mock_mode=True.")
            return "Gap analysis skipped -- Apify not available."

        queries   = [f"to:{c} ?" for c in self.competitors]
        run_input = {"searchTerms": queries, "maxItems": 50, "sort": "Latest", "tweetLanguage": "en"}
        raw_questions = []

        try:
            run = self.apify_client.actor(self.actor_id).call(run_input=run_input)
            if not run or "defaultDatasetId" not in run:
                return "Gap analysis scraping failed."
            for item in self.apify_client.dataset(run["defaultDatasetId"]).iterate_items():
                n = self._normalize(item)
                if n["replies"] < 2:
                    raw_questions.append(n["text"])
            print(f"   -> Collected {len(raw_questions)} unanswered questions.")
        except Exception as e:
            print(f"   [FAIL] Gap analysis error: {type(e).__name__}: {e}")

        if not raw_questions:
            return "No obvious content gaps found today."

        system_prompt = """
        You are an elite social media strategist. I will provide a list of raw questions 
        that users asked top tech influencers.
        Identify the 3 most common themes or most painful problems in these questions.
        Return ONLY a clean, bulleted list of 3 highly specific video/thread topics 
        we should create to fill this gap.
        """
        response = self.client.models.generate_content(
            model=self.heavy_model,
            contents=f"Raw Questions: {json.dumps(raw_questions)}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.3),
        )
        return response.text.strip()

    # ── Shared method (reads spy file — no Apify needed) ─────────────────────

    def _monitor_daily_trends(self):
        print("   -> Clustering daily macro trends...")

        if not os.path.exists(self.spy_data_file):
            msg = f"Spy Agent data not found at {self.spy_data_file}. Run spy_agent first."
            print(f"   [WARN] {msg}")
            return msg

        with open(self.spy_data_file, "r") as f:
            spy_data = json.load(f)

        trend_texts = [item["text"] for item in spy_data if item.get("type") == "TREND_ALERT"]
        print(f"   -> Found {len(trend_texts)} TREND_ALERT items in spy data.")

        if not trend_texts:
            return "No major trends detected in today's Spy data."

        system_prompt = """
        You are a data analyst. Review these trending tweets from the audio tech niche.
        Write a 2-sentence executive summary of exactly what the market is obsessed with today.
        Do not use corporate jargon.
        """
        try:
            response = self.client.models.generate_content(
                model=self.heavy_model,
                contents=f"Trending Tweets: {json.dumps(trend_texts)}",
                config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.2),
            )
            return response.text.strip()
        except Exception as e:
            print(f"   [FAIL] Trend analysis error: {type(e).__name__}: {e}")
            return "Trend analysis failed -- check Gemini quota."

    def _save_report(self, report_data: dict):
        os.makedirs(os.path.dirname(self.report_file), exist_ok=True)
        with open(self.report_file, "w") as f:
            json.dump(report_data, f, indent=4)
        print(f"[SAVED] Report -> {self.report_file}")


if __name__ == "__main__":
    auditor = AuditorAgent()
    auditor.run_full_audit(mock_mode=True)
    