import os
import json
import statistics
from datetime import datetime
from dotenv import load_dotenv
from apify_client import ApifyClient
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

class AuditorAgent:
    def __init__(self):
        self.apify_client = ApifyClient(os.getenv("APIFY_API_TOKEN"))
        self.genai_client = genai.Client()
        self.analysis_model = "gemini-2.5-flash"
        
        # Top creators in the audio/tech niche
        self.targets = ["podcastage", "mkbhd", "harrisheller","rodemics",
            "shure",
            "elgato",
            "Podcastage",
            "mkbhd"]
        self.today = datetime.now().strftime("%Y-%m-%d")
        
        # File paths
        self.spy_file = f"data/raw_tweets_{self.today}.json"
        self.report_file = f"data/competitor_report_{self.today}.json"
        self.actor_id = "apidojo/tweet-scraper"

    def run_full_audit(self):
        """Executes the Phase 1 & 2 intelligence gathering."""
        print(" Auditor Agent active. Initiating Phase 1 & 2 protocols...")
        
        benchmarks = self._audit_competitors()
        gaps = self._find_content_gaps()
        trends = self._monitor_daily_trends()
        
        report = {
            "date": self.today,
            "competitor_benchmarks": benchmarks,
            "content_gaps": gaps,
            "daily_trends": trends
        }
        
        self._save_report(report)
        print(" Comprehensive Competitor & Trend Audit Complete.")

    def _audit_competitors(self):
        """Phase 1: Calculates average engagement baselines for top competitors."""
        print("   -> Benchmarking competitor engagement...")
        benchmarks = {}
        
        # Build search queries like "from:podcastage"
        queries = [f"from:{target}" for target in self.targets]
        
        run_input = {
            "searchTerms": queries,
            "maxItems": 50, # Fetch last 10 tweets per target to keep costs low
            "sort": "Latest"
        }
        
        try:
            run = self.apify_client.actor(self.actor_id).call(run_input=run_input)
            dataset_id = run["defaultDatasetId"]
            items = list(self.apify_client.dataset(dataset_id).iterate_items())
            
            for target in self.targets:
                target_tweets = [item for item in items if item.get("author", {}).get("userName", "").lower() == target.lower()]
                if not target_tweets:
                    continue
                    
                likes = [t.get("likeCount", 0) for t in target_tweets]
                replies = [t.get("replyCount", 0) for t in target_tweets]
                
                benchmarks[target] = {
                    "avg_likes_per_tweet": round(statistics.mean(likes)),
                    "avg_replies_per_tweet": round(statistics.mean(replies)),
                    "top_performing_tweet": max(target_tweets, key=lambda x: x.get("likeCount", 0)).get("text", "")
                }
        except Exception as e:
            print(f" Error during competitor audit: {e}")
            
        return benchmarks

    def _find_content_gaps(self):
        """Phase 1: Finds unanswered questions in competitor replies."""
        print("   -> Extracting audience gaps and unanswered questions...")
        
        # Build search queries like "to:podcastage ?"
        queries = [f"to:{target} ?" for target in self.targets]
        
        run_input = {
            "searchTerms": queries,
            "maxItems": 50,
            "sort": "Latest"
        }
        
        raw_questions = []
        try:
            run = self.apify_client.actor(self.actor_id).call(run_input=run_input)
            dataset_id = run["defaultDatasetId"]
            
            for item in self.apify_client.dataset(dataset_id).iterate_items():
                # Filter out tweets with high replies (meaning the creator probably answered it)
                if item.get("replyCount", 0) < 2: 
                    raw_questions.append(item.get("text", ""))
                    
        except Exception as e:
            print(f"Error during gap analysis scraping: {e}")

        if not raw_questions:
            return "No obvious content gaps found today."

        # Use Gemini to summarize the raw questions into 3 actionable content ideas
        system_prompt = """
        You are an elite social media strategist. I will provide a list of raw questions 
        that users asked top tech influencers. 
        
        Identify the 3 most common themes or most painful problems in these questions.
        Return ONLY a clean, bulleted list of 3 highly specific video/thread topics 
        we should create to fill this gap. 
        """
        
        response = self.genai_client.models.generate_content(
            model=self.analysis_model,
            contents=f"Raw Questions: {json.dumps(raw_questions)}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.3)
        )
        return response.text.strip()

    def _monitor_daily_trends(self):
        """Phase 2: Reads the Spy Agent data to cluster broader market trends."""
        print("   -> Clustering daily macro trends...")
        
        if not os.path.exists(self.spy_file):
            return "Spy Agent data not found. Run spy_agent.py first."
            
        with open(self.spy_file, 'r') as f:
            spy_data = json.load(f)
            
        trend_texts = [item["text"] for item in spy_data if item["type"] == "TREND_ALERT"]
        
        if not trend_texts:
            return "No major trends detected in today's Spy data."

        system_prompt = """
        You are a data analyst. Review these trending tweets from the audio tech niche.
        Write a 2-sentence executive summary of exactly what the market is obsessed with today.
        Do not use corporate jargon.
        """
        
        response = self.genai_client.models.generate_content(
            model=self.analysis_model,
            contents=f"Trending Tweets: {json.dumps(trend_texts)}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.2)
        )
        return response.text.strip()

    def _save_report(self, report_data):
        os.makedirs(os.path.dirname(self.report_file), exist_ok=True)
        with open(self.report_file, 'w') as f:
            json.dump(report_data, f, indent=4)
        print(f" Report saved to {self.report_file}")

if __name__ == "__main__":
    auditor = AuditorAgent()
    auditor.run_full_audit()