"""
image_generator_agent.py v1.1 — AI Image Generator

Place at: mic-growth-engine/agents/image_generator_agent.py

FIX in v1.1:
  - Image generation no longer requires Gemini quota.
  - _build_image_prompt() tries Gemini first (better quality).
  - If Gemini is exhausted, falls back to _build_prompt_from_brief()
    which extracts key phrases from the brief text directly.
  - Phase 7 now works even when ALL Gemini keys are exhausted.
"""

import os
import re
import json
import time
import random
import urllib.parse
import requests
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

IMAGE_MODELS = ["flux", "turbo"]
DATA_DIR      = "data/generated_images"
DASHBOARD_DIR = "social-manager-ui/public/generated"
IMG_WIDTH     = 1080
IMG_HEIGHT    = 1080


class ImageGeneratorAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        # Client is optional — image generation works without Gemini
        self.client = genai.Client(api_key=api_key) if api_key else None

        self.today        = datetime.now().strftime("%Y-%m-%d")
        self.briefs_file  = f"data/image_briefs_{self.today}.json"
        self.drafts_file  = f"data/drafts_{self.today}.json"
        self.output_file  = f"data/generated_images_{self.today}.json"
        self.brand_voice  = self._load_brand_voice()

        os.makedirs(f"{DATA_DIR}/{self.today}", exist_ok=True)
        os.makedirs(DASHBOARD_DIR, exist_ok=True)

    def _load_brand_voice(self):
        try:
            with open("config/brand_voice.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    # ─────────────────────────────────────────────────────
    # MAIN RUN
    # ─────────────────────────────────────────────────────
    def run(self, mock_mode=True):
        print("[IMAGE GEN] Image Generator Agent active.")
        all_briefs = self._collect_briefs()

        if not all_briefs:
            print("[IMAGE GEN] No image briefs found. Run Architect + Image Analyst first.")
            self._save_manifest([])
            return []

        print(f"[IMAGE GEN] Found {len(all_briefs)} image brief(s) to generate.")
        generated = []

        for i, brief in enumerate(all_briefs):
            title = brief.get("title", f"Image {i+1}")
            print(f"\n[IMAGE GEN] Brief {i+1}/{len(all_briefs)}: {title}")

            try:
                prompt = self._build_image_prompt(brief)
                print(f"[IMAGE GEN] Prompt: {prompt[:90]}...")

                filename = f"mic_image_{self.today}_{i+1:03d}.jpg"
                if mock_mode:
                    result = self._mock_generate(brief, filename, prompt)
                else:
                    result = self._generate_image(prompt, filename)

                if result:
                    result["brief"]        = brief
                    result["prompt_used"]  = prompt
                    result["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    generated.append(result)
                    print(f"[OK] Generated: {result['filename']}")

                time.sleep(3)

            except Exception as e:
                print(f"[FAIL] Brief {i+1}: {e}")

        self._save_manifest(generated)
        print(f"\n[IMAGE GEN] Done — {len(generated)} image(s) generated.")
        return generated

    # ─────────────────────────────────────────────────────
    # BRIEF COLLECTION
    # ─────────────────────────────────────────────────────
    def _collect_briefs(self):
        briefs = []

        if os.path.exists(self.drafts_file):
            with open(self.drafts_file, "r") as f:
                drafts = json.load(f)
            for d in drafts:
                if d.get("intent") == "Image_Brief":
                    briefs.append({
                        "source":    "architect",
                        "title":     f"Image post (via @{d.get('source_author', 'competitor')})",
                        "raw_brief": d.get("draft_content", ""),
                    })

        if os.path.exists(self.briefs_file):
            with open(self.briefs_file, "r") as f:
                analyst_briefs = json.load(f)
            for b in analyst_briefs:
                briefs.append({
                    "source":    "image_analyst",
                    "title":     f"Competitor-inspired image (@{b.get('source_author', '?')})",
                    "raw_brief": b.get("our_brief", ""),
                })

        return briefs

    # ─────────────────────────────────────────────────────
    # PROMPT BUILDING — GEMINI OPTIONAL
    # ─────────────────────────────────────────────────────
    def _build_image_prompt(self, brief):
        """
        Try Gemini first for a polished prompt.
        If quota is exhausted or no client, fall back to rule-based extraction.
        Either way, image generation always proceeds.
        """
        # Try Gemini prompt optimisation
        if self.client:
            try:
                from agents.gemini_utils import gemini_with_retry
                brand_name = self.brand_voice.get("brand_name", "MIC")
                niche      = self.brand_voice.get("niche", "audio technology")
                img_style  = (self.brand_voice.get("post_formats", {})
                              .get("image_post", {})
                              .get("preferred_style", "dark background, white text, minimal"))

                system = f"""
Convert this social media image brief into a single image generation prompt.
Brand: {brand_name} ({niche})
Style: {img_style}

Rules:
1. Start with: "Dark background social media infographic,"
2. Describe headline text, data points, visual layout
3. Include: "1080x1080 square, professional design, clean typography"
4. Under 150 words. Output ONLY the prompt, nothing else.
"""
                raw_brief = brief.get("raw_brief", "")[:800]
                prompt = gemini_with_retry(
                    self.client,
                    lambda model: self.client.models.generate_content(
                        model=model,
                        contents=f"Convert to image prompt:\n\n{raw_brief}",
                        config=types.GenerateContentConfig(
                            system_instruction=system, temperature=0.6)
                    ).text.strip()
                )
                return prompt

            except RuntimeError as e:
                if "FATAL" in str(e) or "exhausted" in str(e).lower():
                    print("    [IMAGE GEN] Gemini quota exhausted — using rule-based prompt.")
                else:
                    raise

        # Fallback: build prompt directly from brief text
        return self._build_prompt_from_brief(brief)

    def _build_prompt_from_brief(self, brief):
        """
        Build an image prompt from brief text without any AI call.
        Extracts headline, data points, and visual direction from the brief.
        Works 100% offline, zero quota used.
        """
        raw = brief.get("raw_brief", "")
        brand_name = self.brand_voice.get("brand_name", "MIC")
        niche = self.brand_voice.get("niche", "audio technology")

        # Extract headline if present in brief
        headline = ""
        for pattern in [
            r"HEADLINE[^:]*:\s*[\"']?(.+?)[\"']?\n",
            r"Headline[^:]*:\s*[\"']?(.+?)[\"']?\n",
            r"CONCEPT[^:]*:\s*[\"']?(.+?)[\"']?\n",
        ]:
            m = re.search(pattern, raw, re.IGNORECASE)
            if m:
                headline = m.group(1).strip()[:60]
                break

        # Extract data points
        data_lines = []
        for pattern in [r"DATA POINTS?.*?:(.*?)(?:\n[A-Z]|\Z)", r"bullet[^:]*:(.*?)(?:\n[A-Z]|\Z)"]:
            m = re.search(pattern, raw, re.IGNORECASE | re.DOTALL)
            if m:
                lines = [l.strip().lstrip("-•*").strip() for l in m.group(1).strip().split("\n") if l.strip()]
                data_lines = [l for l in lines if len(l) > 5][:3]
                break

        # Build prompt components
        headline_part = f'bold white headline "{headline}",' if headline else "bold white headline text,"
        data_part     = f"data points: {', '.join(data_lines[:2])}," if data_lines else "technical specifications and bullet points,"

        prompt = (
            f"Dark background social media infographic, {brand_name} brand, "
            f"{niche} topic, "
            f"{headline_part} "
            f"{data_part} "
            f"professional minimal design, white typography on dark background, "
            f"subtle blue accent lines, clean layout, "
            f"1080x1080 square format, social media post, "
            f"high contrast, no clutter, studio aesthetic"
        )

        return prompt

    # ─────────────────────────────────────────────────────
    # IMAGE GENERATION — POLLINATIONS.AI (FREE, NO KEY)
    # ─────────────────────────────────────────────────────
    def _generate_image(self, prompt, filename):
        for model in IMAGE_MODELS:
            try:
                print(f"[IMAGE GEN] Calling Pollinations ({model})...")
                seed = random.randint(1, 999999999)
                url = (
                    f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
                    f"?width={IMG_WIDTH}&height={IMG_HEIGHT}"
                    f"&model={model}&seed={seed}&nologo=true&enhance=true&private=true"
                )

                response = requests.get(url, timeout=120)

                if response.status_code == 200 and len(response.content) > 1000:
                    data_path      = f"{DATA_DIR}/{self.today}/{filename}"
                    dashboard_path = f"{DASHBOARD_DIR}/{filename}"

                    with open(data_path, "wb") as f:
                        f.write(response.content)
                    with open(dashboard_path, "wb") as f:
                        f.write(response.content)

                    return {
                        "filename":   filename,
                        "data_path":  data_path,
                        "public_url": f"/generated/{filename}",
                        "model_used": model,
                        "seed":       seed,
                        "size_kb":    len(response.content) // 1024,
                        "width":      IMG_WIDTH,
                        "height":     IMG_HEIGHT,
                        "status":     "generated",
                    }
                else:
                    print(f"[WARN] Pollinations {model}: status {response.status_code}. Trying next...")

            except requests.Timeout:
                print(f"[WARN] Pollinations {model} timed out. Trying next...")
            except Exception as e:
                print(f"[WARN] Pollinations {model}: {e}. Trying next...")
            time.sleep(5)

        print("[FAIL] All Pollinations models failed.")
        return None

    def _mock_generate(self, brief, filename, prompt):
        return {
            "filename":   filename,
            "data_path":  f"{DATA_DIR}/{self.today}/{filename}",
            "public_url": f"/generated/{filename}",
            "model_used": "mock",
            "seed":       12345,
            "size_kb":    0,
            "width":      IMG_WIDTH,
            "height":     IMG_HEIGHT,
            "status":     "mock — run with --live for real images",
        }

    def _save_manifest(self, generated):
        os.makedirs("data", exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(generated, f, indent=4, ensure_ascii=False)
        print(f"[SAVED] Image manifest → {self.output_file}")


if __name__ == "__main__":
    import sys
    ImageGeneratorAgent().run(mock_mode="--live" not in sys.argv)