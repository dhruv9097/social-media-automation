"""
auditor_agent.py v2.0 — Deep Competitive Intelligence Analyst

Place this file at: mic-growth-engine/agents/auditor_agent.py

WHAT'S NEW in v2.0:
  - Tone fingerprint analysis per competitor
  - Content pillar mapping
  - Engagement pattern detection (what post types win)
  - Audience gap detection from comment threads
  - Image post brief extraction feed
  - Reads brand context from config/brand_voice.json
"""

import os
import json
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv
from agents.gemini_utils import gemini_with_retry

load_dotenv()


class AuditorAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("[FAIL] GEMINI_API_KEY missing from .env")
        self.client = genai.Client(api_key=api_key)

        self.today = datetime.now().strftime("%Y-%m-%d")
        self.intel_file  = f"data/raw_tweets_{self.today}.json"
        self.report_file = f"data/competitor_report_{self.today}.json"

        self.brand_voice = self._load_brand_voice()

    def _load_brand_voice(self):
        try:
            with open("config/brand_voice.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print("[WARN] config/brand_voice.json not found. Running without brand context.")
            return {}

    def run(self):
        print("[AUDITOR] Auditor Agent active. Running deep competitive analysis...")

        tweets = self._load_intel()
        if not tweets:
            print("[WARN] No tweet data found. Run Spy Agent first.")
            self._save_report({})
            return {}

        print(f"[AUDITOR] Analyzing {len(tweets)} posts from last 7 days...")

        # Build analysis context
        context = self._build_analysis_context(tweets)

        # Run all analysis passes
        report = {
            "generated_at":       self.today,
            "posts_analyzed":     len(tweets),
            "content_gaps":       self._analyze_content_gaps(context),
            "tone_fingerprints":  self._analyze_tone_fingerprints(context),
            "engagement_patterns":self._analyze_engagement_patterns(tweets),
            "audience_questions": self._extract_audience_questions(tweets),
            "image_post_briefs":  self._analyze_image_posts(tweets),
            "competitor_pillars": self._map_content_pillars(context),
            "our_opportunities":  self._identify_our_opportunities(context),
        }

        self._save_report(report)
        return report

    # ─────────────────────────────────────────────
    # CONTEXT BUILDER
    # ─────────────────────────────────────────────

    def _build_analysis_context(self, tweets):
        """Build a condensed text summary of all competitor posts for Gemini analysis."""
        lines = []
        for t in tweets:
            engagement = t.get("likes", 0) + t.get("retweets", 0) * 2 + t.get("replies", 0) * 3
            replies_text = ""
            if t.get("raw_replies"):
                top_replies = t["raw_replies"][:3]
                replies_text = " | Comments: " + " / ".join(r["text"] for r in top_replies)

            lines.append(
                f"@{t['author']} [score:{engagement}]: {t['text']}{replies_text}"
            )

        brand_pillars = ", ".join(self.brand_voice.get("content_pillars", []))
        return "\n".join(lines) + f"\n\nOUR BRAND PILLARS: {brand_pillars}"

    # ─────────────────────────────────────────────
    # ANALYSIS METHODS
    # ─────────────────────────────────────────────

    def _analyze_content_gaps(self, context):
        """Find topics the audience asks about that competitors don't fully answer."""
        print("[AUDITOR] Detecting content gaps...")

        brand_name = self.brand_voice.get("brand_name", "MIC")
        niche = self.brand_voice.get("niche", "audio technology")

        prompt = f"""
You are a content strategist for {brand_name}, a brand in {niche}.

Here is the last 7 days of competitor posts and their audience comments:

{context}

TASK: Identify the top 3 CONTENT GAPS — topics the audience is clearly asking about
in the comments that competitors never properly answered.

For each gap:
1. What is the unanswered question?
2. Why is this a high-value gap to fill?
3. What should {brand_name} post to own this topic?

Be specific. No vague advice. Reference actual posts and comments where possible.
Format: Numbered list, 3 gaps max.
"""
        return gemini_with_retry(
            self.client,
            lambda model: self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.5)
            ).text.strip()
        )

    def _analyze_tone_fingerprints(self, context):
        """Map the tone and writing style of each competitor."""
        print("[AUDITOR] Mapping competitor tone fingerprints...")

        prompt = f"""
Analyze the writing style and tone of each competitor in these posts:

{context}

For each competitor account, identify:
- Tone (e.g. educational, hype-driven, casual, authoritative)
- Typical hook style (how they open posts)
- What makes their content engaging or weak
- One sentence: their brand voice in plain English

Keep each analysis to 3-4 bullet points.
"""
        return gemini_with_retry(
            self.client,
            lambda model: self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.4)
            ).text.strip()
        )

    def _analyze_engagement_patterns(self, tweets):
        """Detect what post types and topics drive the most engagement."""
        print("[AUDITOR] Detecting engagement patterns...")

        # Sort by engagement score
        scored = sorted(tweets,
                        key=lambda t: t.get("likes", 0) + t.get("retweets", 0) * 2 + t.get("replies", 0) * 3,
                        reverse=True)

        top_5 = scored[:5]
        bottom_5 = scored[-5:]

        top_text = "\n".join(f"- [{t['author']}] {t['text'][:120]}... (likes:{t.get('likes',0)})" for t in top_5)
        bot_text = "\n".join(f"- [{t['author']}] {t['text'][:120]}... (likes:{t.get('likes',0)})" for t in bottom_5)

        prompt = f"""
TOP 5 highest-engagement competitor posts this week:
{top_text}

BOTTOM 5 lowest-engagement posts this week:
{bot_text}

TASK: What specific patterns explain why the top posts outperform the bottom posts?
Focus on: hook structure, topic type, length, controversy level, and educational value.
Give 3-5 specific, actionable patterns. No generic advice.
"""
        return gemini_with_retry(
            self.client,
            lambda model: self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.4)
            ).text.strip()
        )

    def _extract_audience_questions(self, tweets):
        """Pull all audience questions from comment threads — these are content goldmines."""
        print("[AUDITOR] Extracting audience questions from comments...")

        questions = []
        for tweet in tweets:
            for reply in tweet.get("raw_replies", []):
                text = reply.get("text", "")
                # Simple question detection
                if "?" in text or any(kw in text.lower() for kw in ["how", "what", "why", "which", "does", "can", "should", "best"]):
                    questions.append({
                        "question":    text,
                        "post_author": tweet["author"],
                        "post_text":   tweet["text"][:100],
                        "likes":       reply.get("likes", 0),
                    })

        # Sort by likes — most upvoted questions first
        questions.sort(key=lambda q: q["likes"], reverse=True)
        return questions[:15]  # Top 15 questions

    def _analyze_image_posts(self, tweets):
        """
        Identify competitor posts that have images — flag them for the Image Analyst.
        Returns a list of posts with images for further processing.
        """
        print("[AUDITOR] Flagging image posts for visual analysis...")

        image_posts = [t for t in tweets if t.get("has_images")]
        flagged = []
        for post in image_posts:
            flagged.append({
                "id":         post["id"],
                "author":     post["author"],
                "text":       post["text"],
                "media_urls": post.get("media_urls", []),
                "likes":      post.get("likes", 0),
                "status":     "pending_visual_analysis",
            })

        print(f"[AUDITOR] Found {len(flagged)} image posts to analyze.")
        return flagged

    def _map_content_pillars(self, context):
        """Map what topics each competitor keeps returning to."""
        print("[AUDITOR] Mapping competitor content pillars...")

        prompt = f"""
Based on these competitor posts from the last 7 days:

{context}

What are the 3-5 recurring CONTENT PILLARS for each competitor?
(A content pillar is a topic they post about repeatedly.)

Then identify: Which pillars do they NOT cover that our audience would value?
"""
        return gemini_with_retry(
            self.client,
            lambda model: self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.4)
            ).text.strip()
        )

    def _identify_our_opportunities(self, context):
        """Given competitor data and our brand, what should we post this week?"""
        print("[AUDITOR] Identifying our best opportunities this week...")

        brand_name = self.brand_voice.get("brand_name", "MIC")
        pillars = ", ".join(self.brand_voice.get("content_pillars", []))
        hook_styles = ", ".join(self.brand_voice.get("hook_styles", []))
        tone = self.brand_voice.get("tone", {}).get("adjectives", [])
        examples = self.brand_voice.get("example_posts", [])
        example_text = "\n".join(f'- "{e}"' for e in examples[:2])

        prompt = f"""
You are a senior content strategist for {brand_name}.

OUR BRAND:
- Voice: {", ".join(tone)}
- Pillars: {pillars}
- Hook styles we use: {hook_styles}

OUR VOICE EXAMPLES:
{example_text}

COMPETITOR LANDSCAPE THIS WEEK:
{context}

TASK: Identify the TOP 3 post opportunities for {brand_name} this week.
For each opportunity:
1. What should we post? (topic + angle)
2. Why will this win? (vs what competitors posted)
3. Which hook style should we use?
4. What format? (thread / single tweet / image post)

Be specific. Reference actual competitor gaps or weaknesses where possible.
"""
        return gemini_with_retry(
            self.client,
            lambda model: self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.6)
            ).text.strip()
        )

    # ─────────────────────────────────────────────
    # SAVE
    # ─────────────────────────────────────────────

    def _load_intel(self):
        if not os.path.exists(self.intel_file):
            print(f"[WARN] Intel file not found: {self.intel_file}")
            return None
        with open(self.intel_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_report(self, report):
        os.makedirs("data", exist_ok=True)
        with open(self.report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4, ensure_ascii=False)
        print(f"[SAVED] Deep analysis report → {self.report_file}")


if __name__ == "__main__":
    agent = AuditorAgent()
    agent.run()