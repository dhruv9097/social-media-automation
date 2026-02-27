"""
spy_agent.py v2.1 — Competitor Intelligence Gatherer

Place at: mic-growth-engine/agents/spy_agent.py

FIXES in v2.1:
  - Correct actor: apidojo~tweet-scraper (was twitter-scraper-lite → 403)
  - Correct input: twitterHandles + sort (was searchTerms + queryType)
  - Increased timeout: 120s (was 60s — too short for this actor)
  - Reply scraper also updated to correct actor + conversationIds field
"""

import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


class SpyAgent:
    def __init__(self):
        self.apify_token   = os.getenv("APIFY_API_TOKEN")
        self.today         = datetime.now().strftime("%Y-%m-%d")
        self.seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        self.output_file   = f"data/raw_tweets_{self.today}.json"

        self.competitors   = self._load_competitors()

        # ✅ CORRECT actor ID (tweet-scraper, not twitter-scraper-lite)
        self.actor_url = (
            "https://api.apify.com/v2/acts/apidojo~tweet-scraper"
            "/run-sync-get-dataset-items"
            f"?token={self.apify_token}&timeout=120&memory=256"
        )

    def _load_competitors(self):
        try:
            with open("config/brand_voice.json", "r") as f:
                config = json.load(f)
            competitors = config.get("competitor_accounts", [])
            print(f"[SPY] Loaded {len(competitors)} competitors: {competitors}")
            return competitors
        except FileNotFoundError:
            print("[WARN] brand_voice.json not found. Using defaults.")
            return ["podcastage", "therecordingrevolution"]

    def run(self, mock_mode=True):
        print(f"[SPY] Spy Agent active. Target window: {self.seven_days_ago} → {self.today}")

        if mock_mode:
            print("[SPY] MOCK mode — using synthetic data.")
            tweets = self._get_mock_data()
        else:
            tweets = self._fetch_live_data()

        self._save(tweets)
        return tweets

    # ─────────────────────────────────────────────────────
    # LIVE FETCHING
    # ─────────────────────────────────────────────────────
    def _fetch_live_data(self):
        if not self.apify_token:
            print("[FAIL] APIFY_API_TOKEN missing. Cannot run live mode.")
            return []

        all_tweets = []
        for account in self.competitors:
            print(f"[SPY] Scraping @{account} (last 7 days)...")
            tweets = self._scrape_account(account)
            enriched = self._enrich_with_comments(tweets)
            all_tweets.extend(enriched)
            reply_count = sum(len(t.get("raw_replies", [])) for t in enriched)
            print(f"[SPY] @{account}: {len(tweets)} posts, {reply_count} comments fetched")

        print(f"[SPY] Total: {len(all_tweets)} posts across {len(self.competitors)} accounts.")
        return all_tweets

    def _scrape_account(self, username):
        """
        Scrape tweets from one account using apidojo~tweet-scraper.

        ✅ Correct input format:
          twitterHandles: list of handles (no @)
          maxItems:       max tweets to return
          sort:           "Latest" (not queryType)
          start:          date filter (since:)
        """
        payload = {
            "twitterHandles": [username],
            "maxItems":       50,
            "sort":           "Latest",
            "start":          self.seven_days_ago,   # only posts from last 7 days
            "tweetLanguage":  "en",
        }

        try:
            response = requests.post(
                self.actor_url,
                json=payload,
                timeout=130,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            raw = response.json()

            return [
                {
                    "id":          item.get("id", ""),
                    "author":      username,
                    "text":        item.get("text", ""),
                    "created_at":  item.get("createdAt", ""),
                    "likes":       item.get("likeCount", 0),
                    "retweets":    item.get("retweetCount", 0),
                    "replies":     item.get("replyCount", 0),
                    "views":       item.get("viewCount", 0),
                    "media_urls":  [m.get("url", "") for m in item.get("media", []) if m.get("url")],
                    "has_images":  any(m.get("type") == "photo" for m in item.get("media", [])),
                    "type":        "TREND_ALERT" if item.get("likeCount", 0) > 100 else "OPPORTUNITY",
                    "raw_replies": [],
                }
                for item in raw
                if isinstance(item, dict) and not item.get("noResults")
            ]
        except Exception as e:
            print(f"[FAIL] Could not scrape @{username}: {e}")
            return []

    def _enrich_with_comments(self, tweets, max_comments=3):
        """Fetch reply threads for the top 3 highest-engagement posts."""
        if not tweets:
            return tweets

        top_ids = {
            t["id"] for t in sorted(
                tweets,
                key=lambda t: t.get("likes", 0) + t.get("replies", 0),
                reverse=True
            )[:3]
        }

        for tweet in tweets:
            if tweet["id"] not in top_ids or not tweet["id"]:
                continue

            # ✅ Correct field: conversationIds (not searchTerms with conversation_id:)
            payload = {
                "conversationIds": [tweet["id"]],
                "maxItems":        max_comments,
                "sort":            "Latest",
            }

            try:
                response = requests.post(
                    self.actor_url, json=payload, timeout=130,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                raw_replies = response.json()

                tweet["raw_replies"] = [
                    {
                        "author": r.get("author", {}).get("userName", "unknown"),
                        "text":   r.get("text", ""),
                        "likes":  r.get("likeCount", 0),
                    }
                    for r in raw_replies
                    if isinstance(r, dict) and r.get("id") != tweet["id"] and not r.get("noResults")
                ]
            except Exception as e:
                print(f"[WARN] Could not fetch comments for tweet {tweet['id']}: {e}")

        return tweets

    # ─────────────────────────────────────────────────────
    # MOCK DATA
    # ─────────────────────────────────────────────────────
    def _get_mock_data(self):
        return [
            {
                "id": "1001", "author": "podcastage",
                "text": "The Rode PodMic is the best value dynamic mic for podcasting right now. Better rejection than the SM7B at 1/3 the price. Change my mind.",
                "created_at": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "likes": 847, "retweets": 203, "replies": 91, "views": 45200,
                "media_urls": [], "has_images": False, "type": "TREND_ALERT",
                "raw_replies": [
                    {"author": "user_mike", "text": "But does it need a cloudlifter with a Scarlett 2i2?", "likes": 34},
                    {"author": "user_sarah", "text": "What interface are you pairing it with?", "likes": 22},
                ],
            },
            {
                "id": "1002", "author": "podcastage",
                "text": "USB vs XLR mics: stop framing this as a quality debate. It's a workflow debate. USB for simplicity. XLR for control. Neither is universally better.",
                "created_at": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "likes": 1240, "retweets": 398, "replies": 156, "views": 78300,
                "media_urls": ["https://example.com/mock_image.jpg"], "has_images": True,
                "type": "TREND_ALERT",
                "raw_replies": [
                    {"author": "user_james", "text": "Can you compare Blue Yeti vs SM7B?", "likes": 67},
                    {"author": "user_newbie", "text": "What USB mic for under $100?", "likes": 45},
                ],
            },
            {
                "id": "1003", "author": "therecordingrevolution",
                "text": "Your home studio recording sounds bad because of the room, not the gear. I cannot stress this enough.",
                "created_at": (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "likes": 2100, "retweets": 876, "replies": 203, "views": 125000,
                "media_urls": [], "has_images": False, "type": "TREND_ALERT",
                "raw_replies": [
                    {"author": "user_acoustic", "text": "How much acoustic foam for a 10x12 room?", "likes": 88},
                    {"author": "user_budget", "text": "Any treatment options under $50?", "likes": 72},
                ],
            },
            {
                "id": "1004", "author": "therecordingrevolution",
                "text": "Gain staging is the most underrated skill in home recording. Get it wrong and no plugin will fix it.",
                "created_at": (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "likes": 445, "retweets": 112, "replies": 38, "views": 22400,
                "media_urls": [], "has_images": False, "type": "OPPORTUNITY",
                "raw_replies": [
                    {"author": "user_newpro", "text": "Can you explain gain staging in simple terms?", "likes": 15},
                ],
            },
            {
                "id": "1005", "author": "podcastage",
                "text": "Condenser vs dynamic mic for podcasting — the answer depends entirely on your room, not your budget.",
                "created_at": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "likes": 678, "retweets": 167, "replies": 89, "views": 34100,
                "media_urls": ["https://example.com/condenser_dynamic.jpg"], "has_images": True,
                "type": "TREND_ALERT",
                "raw_replies": [
                    {"author": "user_musician", "text": "What about for music recording specifically?", "likes": 41},
                    {"author": "user_streamer", "text": "I stream in a noisy apartment. Dynamic or condenser?", "likes": 37},
                ],
            },
        ]

    def _save(self, tweets):
        os.makedirs("data", exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(tweets, f, indent=4, ensure_ascii=False)
        print(f"[SAVED] {len(tweets)} tweets → {self.output_file}")


if __name__ == "__main__":
    import sys
    SpyAgent().run(mock_mode="--live" not in sys.argv)