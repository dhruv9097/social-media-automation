import os
import json
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

class ArchitectAgent:
    def __init__(self):
        self.client = genai.Client()
        self.today = datetime.now().strftime("%Y-%m-%d")
        
        # File paths
        self.intel_file = f"data/raw_tweets_{self.today}.json"
        self.report_file = f"data/competitor_report_{self.today}.json"
        self.drafts_file = f"data/drafts_{self.today}.json"
        
        # Models
        self.heavy_model = "gemini-2.5-flash"
        self.fast_model = "gemini-2.5-flash"

    def _load_json(self, filepath):
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r') as f:
            return json.load(f)

    def generate_content(self):
        print(" Architect Agent active. Processing intelligence feeds...")
        drafts = []

        # 1. PROCESS THE GAP ANALYSIS (PHASE 1 -> PHASE 3)
        report_data = self._load_json(self.report_file)
        if report_data and "content_gaps" in report_data:
            gaps = report_data["content_gaps"]
            # Ensure it's not the default "No gaps found" string
            if gaps and "No obvious" not in gaps:
                print("Architect: Gap Analysis found. Drafting Hero Thread...")
                try:
                    gap_draft = self._draft_gap_thread(gaps)
                    drafts.append({
                        "source_tweet_id": "GAP_ANALYSIS_HERO",
                        "source_author": "Competitor_Audience",
                        "intent": "Thread",
                        "draft_content": gap_draft
                    })
                    print(" Drafted Hero Thread based on Competitor Gaps.")
                except Exception as e:
                    print(f" Error drafting Gap Thread: {e}")

        # 2. PROCESS THE TRENDS & OPPORTUNITIES (PHASE 2 -> PHASE 3)
        intel_data = self._load_json(self.intel_file)
        if intel_data:
            for item in intel_data:
                tweet_type = item.get("type")
                raw_text = item.get("text")
                author = item.get("author")

                try:
                    if tweet_type == "TREND_ALERT":
                        draft = self._draft_thread(raw_text)
                        draft_type = "Thread"
                    elif tweet_type == "OPPORTUNITY":
                        draft = self._draft_reply(raw_text)
                        draft_type = "Reply"
                    else:
                        continue

                    drafts.append({
                        "source_tweet_id": item.get("id"),
                        "source_author": author,
                        "intent": draft_type,
                        "draft_content": draft
                    })
                    print(f" Drafted {draft_type} based on @{author}'s tweet.")
                    
                except Exception as e:
                    print(f" Error generating content for tweet {item.get('id')}: {e}")

        self._save_drafts(drafts)

    def _draft_gap_thread(self, gaps_context):
        """Uses Gemini to pitch a Master Thread targeting competitor weaknesses."""
        system_prompt = """
        You are an elite Twitter strategist for an audio/tech influencer.
        The data provided contains questions our competitors failed to answer.
        
        Pitch a 'Suggested Twitter Post' (a thread) to fill this gap.
        Format your exact response like this:

        STRATEGY: [1 sentence explaining why this topic will steal the competitor's audience]
        HOOK: [The punchy first tweet. Under 2 lines. No emojis.]
        DRAFT: 
        [Tweet 2: The technical breakdown]
        ---
        [Tweet 3: The actionable takeaway]
        """
        response = self.client.models.generate_content(
            model=self.heavy_model,
            contents=f"Competitor Gaps: {gaps_context}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.7)
        )
        return response.text.strip()

    def _draft_thread(self, topic_context):
        """Uses Gemini to pitch a thread based on daily market trends."""
        system_prompt = """
        You are an elite Twitter strategist for an audio/tech influencer. 
        Pitch a 'Suggested Twitter Post' based on the provided trending topic.
        
        Format your exact response like this:

        ANGLE: [1 sentence explaining why we should post about this trend today]
        HOOK: [The highly engaging first tweet. Under 2 lines.]
        DRAFT: 
        [Tweet 2: The value/technical explanation]
        ---
        [Tweet 3: The final verdict]
        """
        response = self.client.models.generate_content(
            model=self.heavy_model,
            contents=f"Trending Context: {topic_context}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.7)
        )
        return response.text.strip()

    def _draft_reply(self, question_context):
        system_prompt = """
        You are an elite audio tech expert replying to a user's question on Twitter.
        Rules:
        - Answer the question directly in the first sentence.
        - Keep it under 280 characters.
        - Tone: Helpful but highly authoritative.
        - No hashtags. No generic greetings. Just the raw answer.
        """
        response = self.client.models.generate_content(
            model=self.fast_model,
            contents=f"User's Question: {question_context}",
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.4)
        )
        return response.text.strip()

    def _save_drafts(self, drafts):
        if not drafts:
            print("No drafts generated today.")
            return
            
        os.makedirs(os.path.dirname(self.drafts_file), exist_ok=True)
        with open(self.drafts_file, 'w') as f:
            json.dump(drafts, f, indent=4)
        print(f" {len(drafts)} drafts successfully saved to {self.drafts_file} for Next.js UI review.")

if __name__ == "__main__":
    architect = ArchitectAgent()
    architect.generate_content()