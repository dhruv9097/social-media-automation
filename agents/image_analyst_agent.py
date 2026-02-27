"""
image_analyst_agent.py — Visual Content Intelligence Engine

Place this file at: mic-growth-engine/agents/image_analyst_agent.py

HOW IT WORKS:
  1. Reads flagged image posts from the auditor's competitor_report
  2. Downloads each image to a temp buffer
  3. Sends image + prompt to Gemini Vision (gemini-2.0-flash handles images natively)
  4. Extracts: text content, visual layout, core message, and emotional tone
  5. Generates a creative brief for our own similar post
  6. Saves to data/image_briefs_YYYY-MM-DD.json

NOTE: In mock mode, uses placeholder image analysis.
In live mode, requires real image URLs from the Apify scraper.
"""

import os
import json
import time
import base64
import requests
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv
from agents.gemini_utils import gemini_with_retry

load_dotenv()


class ImageAnalystAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("[FAIL] GEMINI_API_KEY missing from .env")
        self.client = genai.Client(api_key=api_key)

        self.today       = datetime.now().strftime("%Y-%m-%d")
        self.report_file = f"data/competitor_report_{self.today}.json"
        self.output_file = f"data/image_briefs_{self.today}.json"

        self.brand_voice = self._load_brand_voice()

    def _load_brand_voice(self):
        try:
            with open("config/brand_voice.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    # ─────────────────────────────────────────────
    # MAIN RUN
    # ─────────────────────────────────────────────

    def run(self, mock_mode=True):
        print("[IMAGES] Image Analyst Agent active.")

        if mock_mode:
            print("[IMAGES] Running in MOCK mode — generating synthetic image analysis.")
            briefs = self._mock_analysis()
            self._save(briefs)
            return briefs

        # Load image posts flagged by the Auditor
        image_posts = self._load_flagged_posts()
        if not image_posts:
            print("[IMAGES] No image posts to analyze. Run Spy + Auditor agents first.")
            self._save([])
            return []

        print(f"[IMAGES] Analyzing {len(image_posts)} competitor image posts...")
        briefs = []

        for post in image_posts:
            for url in post.get("media_urls", []):
                print(f"[IMAGES] Analyzing image from @{post['author']}: {url[:60]}...")
                try:
                    analysis = self._analyze_image(url, post)
                    if analysis:
                        brief = self._generate_our_brief(analysis, post)
                        briefs.append({
                            "source_post_id":    post.get("id"),
                            "source_author":     post.get("author"),
                            "source_post_text":  post.get("text", ""),
                            "image_url":         url,
                            "image_analysis":    analysis,
                            "our_brief":         brief,
                            "generated_at":      self.today,
                        })
                        print(f"[OK] Image brief generated for @{post['author']}")
                    time.sleep(3)  # Vision API can be slower
                except Exception as e:
                    print(f"[FAIL] Image analysis failed for {url[:50]}: {e}")

        self._save(briefs)
        return briefs

    # ─────────────────────────────────────────────
    # IMAGE ANALYSIS VIA GEMINI VISION
    # ─────────────────────────────────────────────

    def _analyze_image(self, image_url, post_context):
        """
        Download image and send to Gemini Vision for analysis.
        Gemini 2.0 Flash handles image input natively.
        """
        # Download image
        try:
            response = requests.get(image_url, timeout=15)
            response.raise_for_status()
            image_bytes = response.content
            content_type = response.headers.get("Content-Type", "image/jpeg")
        except Exception as e:
            print(f"[FAIL] Could not download image: {e}")
            return None

        # Encode to base64
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = """
Analyze this social media image post carefully. Extract and describe:

1. TEXT CONTENT: All text visible in the image, word for word
2. VISUAL LAYOUT: How is the image designed? (dark/light, sections, icons, charts, etc.)
3. CORE MESSAGE: What is the main point this image communicates in one sentence?
4. CALL TO ACTION: Is there a CTA or engagement hook? What is it?
5. EMOTIONAL TONE: What feeling does this image create? (authoritative, exciting, educational, etc.)
6. WHAT WORKS: What is most effective about this image design?
7. WHAT'S MISSING: What could make this image more impactful?

Be specific and factual. Do not invent content.
"""
        # Build multimodal content for Gemini
        try:
            result = gemini_with_retry(
                self.client,
                lambda model: self.client.models.generate_content(
                    model=model,
                    contents=[
                        types.Content(parts=[
                            types.Part(
                                inline_data=types.Blob(
                                    mime_type=content_type,
                                    data=image_b64
                                )
                            ),
                            types.Part(text=prompt)
                        ])
                    ],
                    config=types.GenerateContentConfig(temperature=0.3)
                ).text.strip()
            )
            return result
        except Exception as e:
            print(f"[FAIL] Gemini Vision analysis failed: {e}")
            return None

    def _generate_our_brief(self, image_analysis, source_post):
        """Generate a creative brief for our own version of this image post."""
        brand_name = self.brand_voice.get("brand_name", "MIC")
        niche      = self.brand_voice.get("niche", "audio technology")
        tone_adj   = ", ".join(self.brand_voice.get("tone", {}).get("adjectives", ["direct", "technical"]))
        img_style  = self.brand_voice.get("post_formats", {}).get("image_post", {}).get("preferred_style", "")
        never_do   = "\n- ".join(self.brand_voice.get("tone", {}).get("never_do", [])[:4])

        prompt = f"""
You are a content strategist for {brand_name} ({niche}).
Our image post style: {img_style}
Our voice: {tone_adj}
Never: {never_do}

A competitor posted this image post:
@{source_post.get('author', '')}: "{source_post.get('text', '')}"

The image contains: {image_analysis[:500]}...

Create a detailed IMAGE POST BRIEF for our design team to create a better version:

CONCEPT: [One sentence — what is our post about?]
HEADLINE TEXT: [The large text for the image — punchy, under 8 words, no emojis]
DATA POINTS: [3-5 specific facts/specs to display in the image body]
VISUAL DIRECTION: [Dark or light? Layout style? Key design notes.]
CAPTION TWEET: [The tweet text that accompanies the image — under 200 chars]
ENGAGEMENT HOOK: [One question or statement at the end to drive replies]
WHY THIS BEATS THE COMPETITOR: [One sentence on our competitive advantage]
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
    # MOCK DATA
    # ─────────────────────────────────────────────

    def _mock_analysis(self):
        """Mock image brief for development — realistic example output."""
        return [
            {
                "source_post_id":   "1002",
                "source_author":    "podcastage",
                "source_post_text": "USB vs XLR mics: stop framing this as a quality debate.",
                "image_url":        "mock://competitor_image.jpg",
                "image_analysis": """
1. TEXT CONTENT: "USB vs XLR — Which Should You Buy?" | Header bold white text
   Bullet points: "USB: Plug and play", "XLR: Full control", "Price: Similar at entry level"
   Footer: @podcastage logo
2. VISUAL LAYOUT: Dark grey background, two-column comparison layout, icons for each bullet
3. CORE MESSAGE: USB and XLR are workflow choices, not quality choices
4. CALL TO ACTION: None explicit — relies on caption
5. EMOTIONAL TONE: Educational, neutral, informative
6. WHAT WORKS: Clean layout, easy to scan at a glance, no clutter
7. WHAT'S MISSING: No specific product recommendations, no specs, no winner declared
""",
                "our_brief": """
CONCEPT: The real decision tree for choosing USB vs XLR — told with actual specs

HEADLINE TEXT: "USB or XLR? It depends on your gain."

DATA POINTS:
- USB: Fixed gain, 44.1kHz sample rate, direct to computer
- XLR: Variable gain, up to 192kHz with pro interface, requires phantom power
- SM7B needs 60dB gain — most USB mics have 30-40dB built in
- USB wins for: portability, speed, one-cable setup
- XLR wins for: recording quality, future upgrades, full signal chain control

VISUAL DIRECTION: Black background, white headline, two columns (USB left, XLR right),
green checkmarks for each category winner, MIC logo bottom right

CAPTION TWEET: USB isn't worse than XLR. It's optimized for a different workflow.
Here is how to actually decide.

ENGAGEMENT HOOK: What interface are you running with your XLR setup?

WHY THIS BEATS THE COMPETITOR: We include actual specs and dB numbers —
they only gave generic bullet points.
""",
                "generated_at": datetime.now().strftime("%Y-%m-%d"),
            }
        ]

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _load_flagged_posts(self):
        if not os.path.exists(self.report_file):
            return []
        with open(self.report_file, "r") as f:
            report = json.load(f)
        return report.get("image_post_briefs", [])

    def _save(self, briefs):
        os.makedirs("data", exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(briefs, f, indent=4, ensure_ascii=False)
        print(f"[SAVED] {len(briefs)} image brief(s) → {self.output_file}")


if __name__ == "__main__":
    agent = ImageAnalystAgent()
    agent.run(mock_mode=True)