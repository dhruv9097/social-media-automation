import os
import json
import time
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

class EngagementAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("[FAIL] GEMINI_API_KEY is missing from your .env file.")
        self.client = genai.Client(api_key=api_key)

        self.today       = datetime.now().strftime("%Y-%m-%d")
        self.drafts_file = f"data/engagement_drafts_{self.today}.json"
        self.fast_model  = "gemini-2.0-flash"

    def run_golden_hour_protocol(self, mock_mode=True):
        print("[ENGAGEMENT] Engagement Agent active. Initiating Golden Hour Protocol...")
        drafts = []

        intel = self._get_engagement_data(mock=mock_mode)

        if not intel:
            print("[WARN] No engagement intel available. "
                  + ("Add live Twitter fetch logic to _get_engagement_data()." if not mock_mode
                     else "Mock data is empty."))
            self._save_drafts([])
            return []

        for item in intel:
            try:
                if item["type"] == "DEFENSIVE":
                    draft = self._draft_defensive_reply(item["text"])
                elif item["type"] == "OFFENSIVE":
                    draft = self._draft_offensive_reply(item["text"])
                else:
                    print(f"[WARN] Unknown type '{item['type']}' for @{item['author']} -- skipping.")
                    continue

                drafts.append({
                    "source_tweet_id": item["id"],
                    "source_author":   item["author"],
                    "intent":          "Engagement",
                    "strategy":        item["type"],
                    "original_text":   item["text"],
                    "draft_content":   draft,
                })
                time.sleep(2)
                print(f"[OK] Drafted {item['type']} reply for @{item['author']}")

            except Exception as e:
                print(f"[FAIL] Error drafting reply for @{item.get('author', '?')}: {type(e).__name__}: {e}")

        self._save_drafts(drafts)
        return drafts

    def _get_engagement_data(self, mock=True):
        if mock:
            return [
                {
                    "id":     "9998887771",
                    "author": "NewPodcaster22",
                    "type":   "DEFENSIVE",
                    "text":   "Great thread! But does the Focusrite 2i2 have enough gain for the SM7B without buying a Cloudlifter?",
                },
                {
                    "id":     "9998887772",
                    "author": "mkbhd",
                    "type":   "OFFENSIVE",
                    "text":   "Just testing the new DJI Mic 2. The internal 32-bit float recording is wild. You literally cannot clip the audio anymore.",
                },
            ]
        else:
            print("[WARN] Live engagement fetch not yet implemented. Returning empty list.")
            return []

    def _draft_defensive_reply(self, user_comment):
        system_prompt = """
        You are the community manager for a top audio tech influencer.
        A follower just replied to your recent thread with a question.
        Write a helpful, highly technical, but concise reply.
        Answer their question directly to keep them engaged. No corporate speak. No emojis.
        """
        response = self.client.models.generate_content(
            model=self.fast_model,
            contents=f"Follower Comment: {user_comment}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.4),
        )
        return response.text.strip()

    def _draft_offensive_reply(self, competitor_tweet):
        system_prompt = """
        You are an elite audio tech influencer. A massive creator in your niche just posted a tweet.
        Write a highly authoritative, value-add reply to hijack their comment section.
        Do not just agree blindly. Add a new technical perspective, a caveat, or a slightly controversial take.
        Keep it punchy. No emojis.
        """
        response = self.client.models.generate_content(
            model=self.fast_model,
            contents=f"Competitor Tweet: {competitor_tweet}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.7),
        )
        return response.text.strip()

    def _save_drafts(self, drafts):
        os.makedirs(os.path.dirname(self.drafts_file), exist_ok=True)
        with open(self.drafts_file, "w") as f:
            json.dump(drafts, f, indent=4)
        print(f"[SAVED] {len(drafts)} engagement draft(s) -> {self.drafts_file}")


if __name__ == "__main__":
    agent = EngagementAgent()
    agent.run_golden_hour_protocol(mock_mode=True)