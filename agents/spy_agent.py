import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from apify_client import ApifyClient

# Load environment variables
load_dotenv()

class SpyAgent:
    def __init__(self):
        # Initialize the Apify Client
        self.client = ApifyClient(os.getenv("APIFY_API_TOKEN"))
        
        # The specific niche keywords we are targeting
        self.keywords = [
            "shure sm7b", "rode wireless", "hyperx quadcast", 
            "best podcast mic", "audio interface suggestions",
            "mic peaking", "obs audio settings","rode wireless pro",
            "shure sm7b",
            "dji mic 2",
            "elgato wave 3",
            "hyperx quadcast",
            "best podcast mic",
            "dynamic vs condenser mic"
        ]
        
        # Using a reliable third-party Twitter scraper on Apify
        self.actor_id = "apidojo/tweet-scraper"

    def fetch_market_chatter(self):
        """Scans Twitter via Apify for recent organic conversations."""
        print(f"Spy Agent active. Deploying Apify Actor to scan: {self.keywords}...")
        
        collected_intel = []

        # Prepare the Apify Actor input
        run_input = {
            "searchTerms": self.keywords,
            "sort": "Latest",        # We want fresh data, not just historical top posts
            "maxItems": 50,          # Adjust this based on your budget/needs
            "includeSearchTerms": True,
            "onlyImage": False,
            "onlyVideo": False,
            "onlyVerifiedUsers": False
        }

        try:
            # 1. Run the Actor and wait for it to finish
            print(" Scraping in progress. This may take a minute or two depending on maxItems...")
            run = self.client.actor(self.actor_id).call(run_input=run_input)
            
            # 2. Fetch the results from the run's dataset
            dataset_id = run["defaultDatasetId"]
            items = self.client.dataset(dataset_id).iterate_items()

            for item in items:
                # Extract relevant metrics
                text = item.get("text", "")
                likes = item.get("likeCount", 0)
                replies = item.get("replyCount", 0)
                author = item.get("author", {}).get("userName", "unknown")
                tweet_id = item.get("id", "")
                created_at = item.get("createdAt", "")

                # LOGIC: 
                # 1. High Engagement = Trend Alert
                # 2. Contains Question + Low Engagement = Opportunity (Lead gen / helpful reply)
                is_viral = likes > 50 or replies > 10
                is_question = "?" in text
                
                intel_type = "NOISE"
                if is_viral: intel_type = "TREND_ALERT"
                elif is_question: intel_type = "OPPORTUNITY"

                # Keep only the data we care about
                if intel_type != "NOISE":
                    intel_entry = {
                        "id": tweet_id,
                        "url": f"https://x.com/{author}/status/{tweet_id}",
                        "author": author,
                        "text": text,
                        "metrics": {
                            "likes": likes,
                            "replies": replies
                        },
                        "type": intel_type,
                        "timestamp": created_at
                    }
                    collected_intel.append(intel_entry)

        except Exception as e:
            print(f"Error running Apify scraper: {e}")

        self._save_intel(collected_intel)
        return collected_intel

    def _save_intel(self, data):
        """Saves data to a JSON file for the Architect Agent to read."""
        if not data:
            print("No actionable intel found in this run.")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"data/raw_tweets_{timestamp}.json"
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                existing_data = json.load(f)
            # Avoid duplicates based on tweet ID
            existing_ids = {item['id'] for item in existing_data}
            new_data = [item for item in data if item['id'] not in existing_ids]
            existing_data.extend(new_data)
            data = existing_data

        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
            
        print(f"💾 Intel saved: {len(data)} high-value items stored in {filename}")

if __name__ == "__main__":
    agent = SpyAgent()
    agent.fetch_market_chatter()