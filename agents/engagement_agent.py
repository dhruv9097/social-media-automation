import os
import json
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

class EngagementAgent:
    def __init__(self):
        self.client = genai.Client()
        self.today = datetime.now().strftime("%Y-%m-%d")
        
        # We save engagement drafts to a separate file so it doesn't mix with your main content
        self.drafts_file = f"data/engagement_drafts_{self.today}.json"
        
        # Always use Flash for engagement - it needs to be lightning fast and cheap
        self.fast_model = "gemini-2.5-flash"

    def run_golden_hour_protocol(self, mock_mode=True):
        print(" Engagement Agent active. Initiating Golden Hour Protocol...")
        drafts = []

        # In production, this pulls from the Twitter API. We use mock data for testing.
        intel = self._get_engagement_data(mock=mock_mode)

        for item in intel:
            try:
                if item["type"] == "DEFENSIVE":
                    draft = self._draft_defensive_reply(item["text"])
                elif item["type"] == "OFFENSIVE":
                    draft = self._draft_offensive_reply(item["text"])
                else:
                    continue
                
                drafts.append({
                    "source_tweet_id": item["id"],
                    "source_author": item["author"],
                    "intent": "Engagement",
                    "strategy": item["type"],
                    "original_text": item["text"],
                    "draft_content": draft
                })
                print(f" Drafted {item['type']} reply for @{item['author']}")
                
            except Exception as e:
                print(f" Error drafting reply: {e}")

        self._save_drafts(drafts)

    def _get_engagement_data(self, mock=True):
        """Simulates fetching mentions and competitor tweets."""
        if mock:
            return [
                {
                    "id": "9998887771",
                    "author": "NewPodcaster22",
                    "type": "DEFENSIVE",
                    "text": "Great thread! But does the Focusrite 2i2 have enough gain for the SM7B without buying a Cloudlifter?"
                },
                {
                    "id": "9998887772",
                    "author": "mkbhd",
                    "type": "OFFENSIVE",
                    "text": "Just testing the new DJI Mic 2. The internal 32-bit float recording is wild. You literally cannot clip the audio anymore."
                }
            ]
        else:
            # Future home of your live Twitter API fetch logic
            return []

    def _draft_defensive_reply(self, user_comment):
        """Defensive: Keeps your own audience engaged in your comment section."""
        system_prompt = """
        You are the community manager for a top audio tech influencer.
        A follower just replied to your recent thread with a question.
        Write a helpful, highly technical, but concise reply.
        Answer their question directly to keep them engaged. No corporate speak. No emojis.
        """
        response = self.client.models.generate_content(
            model=self.fast_model,
            contents=f"Follower Comment: {user_comment}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.4)
        )
        return response.text.strip()

    def _draft_offensive_reply(self, competitor_tweet):
        """Offensive: Hijacks a massive creator's comment section."""
        system_prompt = """
        You are an elite audio tech influencer. A massive creator in your niche just posted a tweet.
        Write a highly authoritative, value-add reply to hijack their comment section.
        Do not just agree blindly. Add a new technical perspective, a caveat, or a slightly controversial take.
        Keep it punchy. No emojis.
        """
        response = self.client.models.generate_content(
            model=self.fast_model,
            contents=f"Competitor Tweet: {competitor_tweet}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.7)
        )
        return response.text.strip()

    def _save_drafts(self, drafts):
        os.makedirs(os.path.dirname(self.drafts_file), exist_ok=True)
        with open(self.drafts_file, 'w') as f:
            json.dump(drafts, f, indent=4)
        print(f"{len(drafts)} engagement drafts saved to {self.drafts_file}")

if __name__ == "__main__":
    agent = EngagementAgent()
    # Running in mock mode to bypass API limits during testing
    agent.run_golden_hour_protocol(mock_mode=True)