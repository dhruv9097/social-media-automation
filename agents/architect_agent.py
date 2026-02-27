"""
architect_agent.py v2.1 — Content Creation Engine

Place at: mic-growth-engine/agents/architect_agent.py

FIXES in v2.1:
  - Phase 5 now ALWAYS generates drafts, even when Phase 1-2 data is missing.
  - Falls back to trend data from Phase 4 when no intel data exists.
  - Trend-based drafts are now a primary output, not a fallback.
  - Competitor response drafts skip gracefully if no intel data.
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


class ArchitectAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("[FAIL] GEMINI_API_KEY missing from .env")
        self.client = genai.Client(api_key=api_key)

        self.today       = datetime.now().strftime("%Y-%m-%d")
        self.intel_file  = f"data/raw_tweets_{self.today}.json"
        self.report_file = f"data/competitor_report_{self.today}.json"
        self.trend_file  = f"data/trend_analysis_{self.today}.json"
        self.drafts_file = f"data/drafts_{self.today}.json"

        self.brand_voice      = self._load_brand_voice()
        self.brand_prompt_block = self._build_brand_prompt_block()

    def _load_brand_voice(self):
        try:
            with open("config/brand_voice.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print("[WARN] brand_voice.json not found.")
            return {}

    def _build_brand_prompt_block(self):
        bv       = self.brand_voice
        name     = bv.get("brand_name", "MIC")
        niche    = bv.get("niche", "audio technology")
        audience = bv.get("target_audience", "podcasters and creators")
        tone_adj = ", ".join(bv.get("tone", {}).get("adjectives", ["direct", "technical"]))
        style    = bv.get("tone", {}).get("writing_style", "")
        never_do = "\n  - ".join(bv.get("tone", {}).get("never_do", []))
        examples = "\n".join(f'  "{e}"' for e in bv.get("example_posts", [])[:3])
        hooks    = "\n  - ".join(bv.get("hook_styles", []))

        return f"""
BRAND: {name}
NICHE: {niche}
AUDIENCE: {audience}
VOICE: {tone_adj}
WRITING STYLE: {style}

VOICE EXAMPLES (match this tone exactly):
{examples}

HOOK STYLES TO USE:
  - {hooks}

NEVER DO:
  - {never_do}
"""

    # ─────────────────────────────────────────────────────
    # MAIN RUN
    # ─────────────────────────────────────────────────────
    def run(self):
        print("[ARCHITECT] Architect Agent active.")
        drafts = []

        report_data = self._load_json(self.report_file)
        intel_data  = self._load_json(self.intel_file)
        trend_data  = self._load_json(self.trend_file)

        has_intel  = bool(intel_data and len(intel_data) > 0)
        has_report = bool(report_data and report_data.get("content_gaps"))
        has_trends = bool(trend_data and trend_data.get("approved"))

        if not has_intel and not has_report and not has_trends:
            print("[ARCHITECT] No data from any phase. Nothing to draft.")
            self._save_drafts([])
            return []

        # ── 1. GAP-BASED HERO THREAD ──────────────────────
        # (requires Phase 2 report)
        if has_report:
            gaps = report_data["content_gaps"]
            print("[ARCHITECT] Drafting Hero Thread from content gaps...")
            try:
                draft = self._draft_gap_thread(gaps)
                drafts.append(self._package("GAP_HERO", "Competitor_Audience", "Thread", draft,
                    "Generated from 7-day competitor gap analysis"))
                print("[OK] Hero Thread drafted.")
                time.sleep(2)
            except Exception as e:
                print(f"[FAIL] Gap Thread: {e}")

        # ── 2. AUDIENCE QUESTION REPLIES ──────────────────
        # (requires Phase 2 report)
        if has_report and report_data.get("audience_questions"):
            for q in report_data["audience_questions"][:3]:
                try:
                    draft = self._draft_audience_reply(q["question"], q.get("post_text", ""))
                    drafts.append(self._package(
                        q.get("post_text", "")[:50], "Audience", "Reply", draft,
                        f"Audience question ({q.get('likes', 0)} likes)"))
                    print(f"[OK] Reply: {q['question'][:60]}...")
                    time.sleep(2)
                except Exception as e:
                    print(f"[FAIL] Audience reply: {e}")

        # ── 3. OPPORTUNITY THREAD ─────────────────────────
        # (requires Phase 2 report)
        if has_report and report_data.get("our_opportunities"):
            try:
                draft = self._draft_opportunity_thread(report_data["our_opportunities"])
                drafts.append(self._package("OPPORTUNITY", "Market_Analysis", "Thread", draft,
                    "Proactive content from weekly opportunity analysis"))
                print("[OK] Opportunity Thread drafted.")
                time.sleep(2)
            except Exception as e:
                print(f"[FAIL] Opportunity Thread: {e}")

        # ── 4. COMPETITOR RESPONSE DRAFTS ─────────────────
        # (requires Phase 1 intel)
        if has_intel:
            top_posts = sorted(intel_data,
                key=lambda t: t.get("likes", 0) + t.get("retweets", 0) * 2,
                reverse=True)[:2]
            print(f"[ARCHITECT] Drafting competitor responses for top {len(top_posts)} posts...")
            for post in top_posts:
                try:
                    draft = self._draft_competitor_response(post["text"], post["author"])
                    drafts.append(self._package(post["id"], post["author"], "Competitor_Response", draft,
                        f"Response to @{post['author']}: {post['text'][:80]}..."))
                    print(f"[OK] Competitor response for @{post['author']}.")
                    time.sleep(2)
                except Exception as e:
                    print(f"[FAIL] Competitor response: {e}")

        # ── 5. IMAGE BRIEFS ───────────────────────────────
        # (requires Phase 2 report)
        if has_report and report_data.get("image_post_briefs"):
            for img_post in report_data["image_post_briefs"][:1]:
                try:
                    brief = self._draft_image_brief(img_post.get("text", ""), img_post.get("author", ""))
                    drafts.append(self._package(
                        img_post["id"], img_post["author"], "Image_Brief", brief,
                        f"Image post brief based on @{img_post['author']}'s visual post"))
                    print("[OK] Image post brief generated.")
                    time.sleep(2)
                except Exception as e:
                    print(f"[FAIL] Image brief: {e}")

        # ── 6. TREND-BASED CONTENT ────────────────────────
        # ✅ FIXED: Now always runs if trend data exists (Phase 4).
        # Previously only ran when intel data existed too — that was the bug.
        if has_trends:
            approved_trends = trend_data["approved"]
            print(f"[ARCHITECT] Drafting content from {len(approved_trends)} approved trends...")

            for trend in approved_trends[:4]:  # Top 4 trends max
                try:
                    # If trend already has a draft from Phase 4, upgrade it into a full thread
                    existing_hook = trend.get("hook", "")
                    existing_angle = trend.get("angle", "")
                    topic = trend.get("topic", "")

                    draft = self._draft_trend_thread(topic, existing_angle, existing_hook)
                    drafts.append(self._package(
                        f"trend_{topic[:20]}", "Trend_Engine", "Thread", draft,
                        f"Trend hijack: #{topic} (score {trend.get('score', '?')}/10)"))
                    print(f"[OK] Trend Thread: #{topic}")
                    time.sleep(2)
                except Exception as e:
                    print(f"[FAIL] Trend Thread #{trend.get('topic', '?')}: {e}")

        self._save_drafts(drafts)
        return drafts

    # ─────────────────────────────────────────────────────
    # DRAFT METHODS
    # ─────────────────────────────────────────────────────
    def _draft_gap_thread(self, gaps_context):
        system = f"{self.brand_prompt_block}\nWrite a Twitter thread filling a content gap competitors missed.\nFormat:\nHOOK: [First tweet — bold claim or myth-bust. Standalone.]\n---\nTWEET 2: [Technical breakdown with specs or numbers.]\n---\nTWEET 3: [Practical action for the reader.]\n---\nTWEET 4: [Strong opinion or prediction.]"
        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model, contents=f"Content gap:\n{gaps_context}",
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.7)
        ).text.strip())

    def _draft_audience_reply(self, question, post_context):
        system = f"{self.brand_prompt_block}\nWrite a reply under 280 chars that answers the question directly in the first sentence. Include a specific spec or product name. No 'Great question!' openers."
        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model, contents=f"Context: {post_context}\nQuestion: {question}",
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.4)
        ).text.strip())

    def _draft_opportunity_thread(self, opportunities_context):
        system = f"{self.brand_prompt_block}\nCreate a proactive Twitter thread positioning us as the leading voice in audio technology.\nFormat:\nHOOK: [Bold opening.]\n---\nTWEET 2: [Technical breakdown.]\n---\nTWEET 3: [Practical takeaway.]\n---\nTWEET 4: [Our strong opinion.]"
        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model, contents=f"Opportunities:\n{opportunities_context}",
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.7)
        ).text.strip())

    def _draft_competitor_response(self, competitor_tweet, competitor_account):
        system = f"{self.brand_prompt_block}\nWrite a reply under 280 chars that adds technical insight the competitor missed. Respectfully disagrees or expands. No emojis. No 'Great point!' openers."
        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model, contents=f"@{competitor_account} posted: {competitor_tweet}",
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.6)
        ).text.strip())

    def _draft_image_brief(self, competitor_post_text, competitor_account):
        system = f"{self.brand_prompt_block}\nCreate an IMAGE POST BRIEF for our design team.\nFormat:\nCONCEPT: [One sentence]\nHEADLINE TEXT: [Under 8 words, punchy]\nDATA POINTS: [3-5 bullets of specs/facts]\nVISUAL DIRECTION: [Colors, layout, style]\nCAPTION TWEET: [Under 200 chars, no hashtags]\nENGAGEMENT HOOK: [One question to drive replies]"
        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model, contents=f"@{competitor_account} posted: {competitor_post_text}",
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.6)
        ).text.strip())

    def _draft_trend_thread(self, topic, angle, hook):
        """Draft a full polished thread from an approved trend."""
        system = f"""
{self.brand_prompt_block}

A trending topic has been identified as highly relevant to our niche.
Write a complete Twitter thread that uses this trend to showcase our expertise.

Rules:
- First tweet MUST reference the trend directly in the first line
- Pivot naturally to audio/creator technical insight in tweet 2
- End with a strong opinion or surprising fact
- Format:
HOOK: [First tweet — references the trend + pivots to audio insight]
---
TWEET 2: [Technical breakdown with specs, numbers, or product names]
---
TWEET 3: [Practical takeaway for podcasters/creators]
"""
        content = f"Trending topic: {topic}\nCreative angle: {angle}\nSuggested hook: {hook}"
        return gemini_with_retry(self.client, lambda model: self.client.models.generate_content(
            model=model, contents=content,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.8)
        ).text.strip())

    # ─────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────
    def _package(self, source_id, author, intent, content, source_note=""):
        return {
            "generated_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source_id":     source_id,
            "source_author": author,
            "intent":        intent,
            "source_note":   source_note,
            "draft_content": content,
            "status":        "pending_review",
        }

    def _load_json(self, filepath):
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_drafts(self, drafts):
        os.makedirs("data", exist_ok=True)
        with open(self.drafts_file, "w", encoding="utf-8") as f:
            json.dump(drafts, f, indent=4, ensure_ascii=False)
        print(f"[SAVED] {len(drafts)} draft(s) → {self.drafts_file}")


if __name__ == "__main__":
    ArchitectAgent().run()