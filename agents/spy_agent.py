import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

ACTOR_ID              = "apidojo/twitter-scraper-lite"  # Twitter Scraper Unlimited: event-based pricing, ~$0.05/50 tweets
TREND_ALERT_LIKES     = 10
TREND_ALERT_REPLIES   = 3

# ── Mock data: realistic podcast/audio niche tweets ──────────────────────────
MOCK_INTEL = [
    {
        "id": "mock_001",
        "url": "https://x.com/PodGearNerd/status/mock_001",
        "author": "PodGearNerd",
        "text": "The Rode Wireless Pro just destroyed my Sennheiser G4 setup. 32-bit float internal recording means I literally cannot clip on location. Game over for traditional wireless.",
        "metrics": {"likes": 312, "replies": 47},
        "type": "TREND_ALERT",
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    },
    {
        "id": "mock_002",
        "url": "https://x.com/StudioTalkDaily/status/mock_002",
        "author": "StudioTalkDaily",
        "text": "Hot take: The SM7B is massively overrated for beginners. You need a clean preamp with 60dB of gain to make it shine — most interfaces can't deliver that. Fight me.",
        "metrics": {"likes": 891, "replies": 203},
        "type": "TREND_ALERT",
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    },
    {
        "id": "mock_003",
        "url": "https://x.com/NewPodcasterJen/status/mock_003",
        "author": "NewPodcasterJen",
        "text": "Does the best podcast mic under $200 actually exist or is it all marketing? Every review says something different and I'm losing my mind trying to decide.",
        "metrics": {"likes": 4, "replies": 2},
        "type": "OPPORTUNITY",
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    },
    {
        "id": "mock_004",
        "url": "https://x.com/AudioEngineerPro/status/mock_004",
        "author": "AudioEngineerPro",
        "text": "Shure SM7B vs Rode PodMic USB — I've recorded 400+ podcast episodes on both. Here's the honest breakdown nobody gives you. Thread incoming.",
        "metrics": {"likes": 1204, "replies": 88},
        "type": "TREND_ALERT",
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    },
    {
        "id": "mock_005",
        "url": "https://x.com/RemoteRecorder/status/mock_005",
        "author": "RemoteRecorder",
        "text": "Anyone using the Rode Wireless Pro for interview work? Wondering if the onboard recording actually saves you when the receiver drops signal?",
        "metrics": {"likes": 8, "replies": 1},
        "type": "OPPORTUNITY",
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    },
]

class SpyAgent:
    def __init__(self):
        self.today         = datetime.now().strftime("%Y-%m-%d")
        self.data_dir      = "data"
        self.raw_data_file = os.path.join(self.data_dir, f"raw_tweets_{self.today}.json")

        settings_path = "data/target_settings.json"
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
                self.keywords = settings.get("keywords", [])
                print(f"[OK] Loaded {len(self.keywords)} keywords: {self.keywords}")
        except FileNotFoundError:
            print("[WARN] target_settings.json not found. Using defaults.")
            self.keywords = ["podcast mic"]

        # Only import Apify if we're going live — avoids crashes when token is missing
        self._apify_ready = False
        apify_token = os.getenv("APIFY_API_TOKEN")
        if apify_token:
            try:
                from apify_client import ApifyClient
                self.client   = ApifyClient(apify_token)
                self.actor_id = ACTOR_ID
                self._apify_ready = True
            except ImportError:
                print("[WARN] apify_client not installed. Mock mode only.")

    def _normalize(self, item: dict) -> dict:
        author_obj = item.get("author", item.get("user", {}))
        return {
            "id":         str(item.get("id", item.get("tweet_id", ""))),
            "text":       item.get("text", item.get("full_text", "")),
            "likes":      item.get("likeCount",  item.get("favorite_count", item.get("likes", 0))),
            "replies":    item.get("replyCount", item.get("reply_count",    item.get("replies", 0))),
            "author":     author_obj.get("userName", author_obj.get("screen_name", "unknown")),
            "created_at": item.get("createdAt",  item.get("created_at", "")),
        }

    def fetch_market_chatter(self, mock_mode=False):
        """
        mock_mode=True  → uses built-in mock data (no Apify credits consumed)
        mock_mode=False → calls Apify live (requires paid plan + credits)
        """
        if mock_mode:
            return self._fetch_mock()
        return self._fetch_live()

    def _fetch_mock(self):
        print("[SPY] Running in MOCK MODE -- no Apify credits consumed.")
        print(f"[SPY] Injecting {len(MOCK_INTEL)} realistic mock tweets...")
        self._save_intel(MOCK_INTEL)
        return MOCK_INTEL

    def _fetch_live(self):
        if not self._apify_ready:
            print("[FAIL] Apify client not ready. Check APIFY_API_TOKEN in .env")
            self._save_intel([])
            return []

        print(f"[SPY] LIVE MODE -- Scanning: {self.keywords}")

        run_input = {
            "searchTerms":        self.keywords,
            "sort":               "Latest",
            "maxItems":           50,
            "includeSearchTerms": True,
            "onlyImage":          False,
            "onlyVideo":          False,
            "onlyVerifiedUsers":  False,
            "tweetLanguage":      "en",
        }

        collected_intel = []
        try:
            print("[SPY] Scraping in progress. This may take 1-2 minutes...")
            run = self.client.actor(self.actor_id).call(run_input=run_input)

            if not run or "defaultDatasetId" not in run:
                print("[FAIL] Apify run returned no dataset.")
                self._save_intel([])
                return []

            items = list(self.client.dataset(run["defaultDatasetId"]).iterate_items())
            print(f"[SPY] Raw items received: {len(items)}")

            noise_count = 0
            for item in items:
                n = self._normalize(item)
                is_viral    = n["likes"] >= TREND_ALERT_LIKES or n["replies"] >= TREND_ALERT_REPLIES
                is_question = "?" in n["text"]

                intel_type = "NOISE"
                if is_viral:      intel_type = "TREND_ALERT"
                elif is_question: intel_type = "OPPORTUNITY"

                if intel_type != "NOISE":
                    collected_intel.append({
                        "id":        n["id"],
                        "url":       f"https://x.com/{n['author']}/status/{n['id']}",
                        "author":    n["author"],
                        "text":      n["text"],
                        "metrics":   {"likes": n["likes"], "replies": n["replies"]},
                        "type":      intel_type,
                        "timestamp": n["created_at"],
                    })
                else:
                    noise_count += 1

            print(f"[SPY] Results: {len(collected_intel)} actionable, {noise_count} noise")

        except Exception as e:
            print(f"[FAIL] Apify scraper error: {type(e).__name__}: {e}")
            self._save_intel([])
            return []

        self._save_intel(collected_intel)
        return collected_intel

    def _save_intel(self, data: list):
        os.makedirs(self.data_dir, exist_ok=True)

        existing_data = []
        if os.path.exists(self.raw_data_file):
            with open(self.raw_data_file, "r") as f:
                existing_data = json.load(f)

        existing_ids = {item["id"] for item in existing_data}
        new_items    = [item for item in data if item["id"] not in existing_ids]
        merged       = existing_data + new_items

        with open(self.raw_data_file, "w") as f:
            json.dump(merged, f, indent=4)

        print(f"[SAVED] {len(merged)} total items -> {self.raw_data_file} (+{len(new_items)} new)")


if __name__ == "__main__":
    agent = SpyAgent()
    agent.fetch_market_chatter(mock_mode=True)