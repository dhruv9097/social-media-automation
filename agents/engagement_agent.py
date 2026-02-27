"""
engagement_agent.py v2.0 — Community Engagement Engine

Place this file at: mic-growth-engine/agents/engagement_agent.py

WHAT'S NEW in v2.0:
  - Brand voice injected from brand_voice.json
  - Consistent MIC character across all replies
  - Reads audience questions from auditor's report
  - Defensive replies (answer follower questions)
  - Offensive replies (hijack competitor comment sections)
"""

import os
import json
import time
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv
from agents.gemini_utils import gemini_with_retry

load_dotenv()


class EngagementAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("[FAIL] GEMINI_API_KEY missing from .env")
        self.client      = genai.Client(api_key=api_key)
        self.today       = datetime.now().strftime("%Y-%m-%d")
        self.drafts_file = f"data/engagement_drafts_{self.today}.json"
        self.report_file = f"data/competitor_report_{self.today}.json"
        self.intel_file  = f"data/raw_tweets_{self.today}.json"

        self.brand_voice = self._load_brand_voice()
        self.brand_prompt_block = self._build_brand_prompt_block()

    def _load_brand_voice(self):
        try:
            with open("config/brand_voice.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print("[WARN] config/brand_voice.json not found.")
            return {}

    def _build_brand_prompt_block(self):
        bv = self.brand_voice
        name     = bv.get("brand_name", "MIC")
        niche    = bv.get("niche", "audio technology")
        tone_adj = ", ".join(bv.get("tone", {}).get("adjectives", ["direct", "technical"]))
        style    = bv.get("tone", {}).get("writing_style", "")
        never_do = "\n  - ".join(bv.get("tone", {}).get("never_do", []))
        examples = "\n".join(f'  "{e}"' for e in bv.get("example_posts", [])[:2])

        return f"""
BRAND: {name} — {niche}
VOICE: {tone_adj}
STYLE: {style}

VOICE EXAMPLES (match this tone):
{examples}

NEVER DO:
  - {never_do}
"""

    # ─────────────────────────────────────────────
    # MAIN RUN
    # ─────────────────────────────────────────────

    def run_golden_hour_protocol(self, mock_mode=True):
        print("[ENGAGEMENT] Engagement Agent active. Initiating Golden Hour Protocol...")
        drafts = []

        # Get engagement targets
        intel = self._get_engagement_targets(mock=mock_mode)
        if not intel:
            print("[WARN] No engagement targets available.")
            self._save_drafts([])
            return []

        print(f"[ENGAGEMENT] Processing {len(intel)} engagement targets...")

        for item in intel:
            try:
                item_type = item.get("type")
                if item_type == "DEFENSIVE":
                    draft = self._draft_defensive_reply(item["text"], item.get("context", ""))
                elif item_type == "OFFENSIVE":
                    draft = self._draft_offensive_reply(item["text"], item.get("author", ""))
                elif item_type == "AUDIENCE_QUESTION":
                    draft = self._draft_audience_answer(item["text"], item.get("context", ""))
                else:
                    print(f"[WARN] Unknown type '{item_type}' — skipping.")
                    continue

                drafts.append({
                    "generated_at":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "source_tweet_id": item.get("id", ""),
                    "source_author":   item.get("author", ""),
                    "intent":          "Engagement",
                    "strategy":        item_type,
                    "original_text":   item["text"],
                    "draft_content":   draft,
                    "status":          "pending_review",
                })
                print(f"[OK] Drafted {item_type} reply for @{item.get('author', '?')}")
                time.sleep(2)

            except Exception as e:
                print(f"[FAIL] Error for @{item.get('author', '?')}: {type(e).__name__}: {e}")

        self._save_drafts(drafts)
        return drafts

    # ─────────────────────────────────────────────
    # ENGAGEMENT TARGET SOURCES
    # ─────────────────────────────────────────────

    def _get_engagement_targets(self, mock=True):
        if mock:
            return self._mock_targets()

        targets = []

        # Source 1: Audience questions from auditor report
        if os.path.exists(self.report_file):
            with open(self.report_file, "r") as f:
                report = json.load(f)
            questions = report.get("audience_questions", [])[:3]
            for q in questions:
                targets.append({
                    "id":      "aud_q",
                    "author":  "audience_member",
                    "type":    "AUDIENCE_QUESTION",
                    "text":    q["question"],
                    "context": q.get("post_text", ""),
                })

        # Source 2: Top competitor posts for offensive replies
        if os.path.exists(self.intel_file):
            with open(self.intel_file, "r") as f:
                tweets = json.load(f)
            top_posts = sorted(tweets,
                               key=lambda t: t.get("likes", 0),
                               reverse=True)[:2]
            for post in top_posts:
                targets.append({
                    "id":     post["id"],
                    "author": post["author"],
                    "type":   "OFFENSIVE",
                    "text":   post["text"],
                })

        if not targets:
            print("[WARN] No live engagement data found. Add real data in live mode.")
        return targets

    def _mock_targets(self):
        return [
            {
                "id":      "q001",
                "author":  "NewPodcaster22",
                "type":    "DEFENSIVE",
                "text":    "Does the Focusrite 2i2 have enough gain for the SM7B without a Cloudlifter?",
                "context": "Discussion about interface gain requirements",
            },
            {
                "id":      "q002",
                "author":  "mkbhd",
                "type":    "OFFENSIVE",
                "text":    "Just tested the DJI Mic 2. The 32-bit float recording is wild — you literally cannot clip the audio anymore.",
                "context": "",
            },
            {
                "id":      "q003",
                "author":  "audio_beginner_99",
                "type":    "AUDIENCE_QUESTION",
                "text":    "What USB mic would you recommend for under $100 for podcasting?",
                "context": "USB vs XLR mic discussion",
            },
        ]

    # ─────────────────────────────────────────────
    # REPLY DRAFTERS
    # ─────────────────────────────────────────────

    def _draft_defensive_reply(self, question, context=""):
        system = f"""
{self.brand_prompt_block}

A follower asked a technical question. Write a community reply that:
- Answers the question DIRECTLY in the first sentence
- Includes at least one specific spec, product name, or number
- Under 280 characters total
- Never starts with "Great question!" or generic openers
- Tone: Knowledgeable friend, not a customer service rep
"""
        content = f"Question: {question}"
        if context:
            content += f"\nContext: {context}"

        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model,
            contents=content,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.4)
        ).text.strip())

    def _draft_offensive_reply(self, competitor_tweet, competitor_handle=""):
        system = f"""
{self.brand_prompt_block}

A large creator just posted the tweet below. Write a reply designed to:
- Add a technical insight or data point they completely missed
- Be subtly more authoritative than their post
- Drive their audience to follow us
- Under 280 characters
- NOT just agree — add a perspective shift or deeper fact
- No emojis. No "Nice!" or validation openers.
"""
        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model,
            contents=f"@{competitor_handle} posted: {competitor_tweet}",
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.6)
        ).text.strip())

    def _draft_audience_answer(self, question, context=""):
        system = f"""
{self.brand_prompt_block}

An audience member posted a question in the audio/creator community.
Write a helpful, expert reply that:
- Answers directly with a specific recommendation
- Mentions a concrete product or spec
- Under 280 characters
- Sounds like the most knowledgeable person in the thread
"""
        content = f"Question: {question}"
        if context:
            content += f"\nContext: {context}"

        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model,
            contents=content,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.4)
        ).text.strip())

    # ─────────────────────────────────────────────
    # SAVE
    # ─────────────────────────────────────────────

    def _save_drafts(self, drafts):
        os.makedirs("data", exist_ok=True)
        with open(self.drafts_file, "w", encoding="utf-8") as f:
            json.dump(drafts, f, indent=4, ensure_ascii=False)
        print(f"[SAVED] {len(drafts)} engagement draft(s) → {self.drafts_file}")


if __name__ == "__main__":
    agent = EngagementAgent()
    agent.run_golden_hour_protocol(mock_mode=True)