"""
main.py v2.3 — MIC Growth Engine Orchestrator

Run modes:
  python main.py           → mock mode (safe, no real API calls)
  python main.py --live    → live mode (real scraping + AI + image generation)
  python main.py --reset   → wipe quota state then run live

PHASES:
  1  Spy Agent           — 7-day competitor scraping + comments
  2  Auditor Agent       — deep analysis, gap detection, image flagging
  3  Image Analyst       — read competitor image posts via Gemini Vision
  4  Trend Hijack        — score world trends, draft posts for score >= 7
  5  Architect           — draft threads, replies, competitor responses, image briefs
  6  Engagement          — community reply drafts (Golden Hour)
  7  Image Generator     — generate actual images via Pollinations.ai (FREE, no key)
"""

import sys
import time
import os
from datetime import datetime

from agents.spy_agent             import SpyAgent
from agents.auditor_agent         import AuditorAgent
from agents.image_analyst_agent   import ImageAnalystAgent
from agents.trend_hijack_agent    import TrendHijackAgent
from agents.architect_agent       import ArchitectAgent
from agents.engagement_agent      import EngagementAgent
from agents.image_generator_agent import ImageGeneratorAgent
from agents.gemini_utils          import print_quota_status, QUOTA_STATE_FILE


def print_phase(number, name):
    print(f"\n{'='*58}")
    print(f"  PHASE {number} — {name.upper()}")
    print(f"{'='*58}")


def print_summary(results):
    print(f"\n{'='*58}")
    print("  ENGINE RUN COMPLETE — MIC Growth Engine v2.3")
    print(f"{'='*58}")
    for key, val in results.items():
        print(f"  {key:<40} {val}")
    print(f"{'='*58}")
    print("\n[ENGINE] Done. Open your Dashboard to review content.\n")


def run_engine(mock_mode=True):
    start = datetime.now()
    print(f"\n[ENGINE] MIC Growth Engine v2.3 starting...")
    print(f"[ENGINE] Mode: {'MOCK (safe)' if mock_mode else 'LIVE'}")
    print(f"[ENGINE] Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")

    if not mock_mode:
        print_quota_status()

    results = {
        "Tweets scraped":    0,
        "Analysis report":   "not generated",
        "Trends approved":   0,
        "Content drafts":    0,
        "Engagement drafts": 0,
        "Images generated":  0,
    }

    # ── PHASE 1: SPY ──────────────────────────────────
    print_phase(1, "COMPETITOR INTELLIGENCE (7-DAY SCRAPE)")
    try:
        tweets = SpyAgent().run(mock_mode=mock_mode)
        results["Tweets scraped"] = len(tweets)
        print(f"[OK] Phase 1 complete — {len(tweets)} posts collected.")
    except Exception as e:
        print(f"[FAIL] Phase 1: {e}")
    time.sleep(1)

    # ── PHASE 2: AUDITOR ──────────────────────────────
    print_phase(2, "DEEP COMPETITIVE ANALYSIS")
    try:
        report = AuditorAgent().run()
        if report:
            results["Analysis report"] = "generated ✓"
        print(f"[OK] Phase 2 complete.")
    except Exception as e:
        print(f"[FAIL] Phase 2: {e}")
    time.sleep(1)

    # ── PHASE 3: IMAGE ANALYST ────────────────────────
    print_phase(3, "COMPETITOR IMAGE READING")
    try:
        briefs = ImageAnalystAgent().run(mock_mode=mock_mode)
        print(f"[OK] Phase 3 complete — {len(briefs)} competitor image(s) analysed.")
    except Exception as e:
        print(f"[FAIL] Phase 3: {e}")
    time.sleep(1)

    # ── PHASE 4: TREND HIJACK ─────────────────────────
    print_phase(4, "TREND INTELLIGENCE")
    try:
        trend_result = TrendHijackAgent().run(mock_mode=mock_mode)
        results["Trends approved"] = trend_result.get("approved_count", 0)
        print(f"[OK] Phase 4 complete — {results['Trends approved']} trends approved.")
    except Exception as e:
        print(f"[FAIL] Phase 4: {e}")
    time.sleep(1)

    # ── PHASE 5: ARCHITECT ────────────────────────────
    print_phase(5, "CONTENT CREATION")
    try:
        drafts = ArchitectAgent().run()
        results["Content drafts"] = len(drafts)
        img_briefs = sum(1 for d in drafts if d.get("intent") == "Image_Brief")
        print(f"[OK] Phase 5 complete — {len(drafts)} drafts ({img_briefs} image briefs).")
    except Exception as e:
        print(f"[FAIL] Phase 5: {e}")
    time.sleep(1)

    # ── PHASE 6: ENGAGEMENT ───────────────────────────
    print_phase(6, "COMMUNITY ENGAGEMENT (GOLDEN HOUR)")
    try:
        eng = EngagementAgent().run_golden_hour_protocol(mock_mode=mock_mode)
        results["Engagement drafts"] = len(eng)
        print(f"[OK] Phase 6 complete — {len(eng)} engagement draft(s).")
    except Exception as e:
        print(f"[FAIL] Phase 6: {e}")
    time.sleep(1)

    # ── PHASE 7: IMAGE GENERATOR ──────────────────────
    print_phase(7, "IMAGE GENERATION (POLLINATIONS.AI — FREE, NO KEY NEEDED)")
    try:
        images = ImageGeneratorAgent().run(mock_mode=mock_mode)
        results["Images generated"] = len(images)
        if mock_mode:
            print(f"[OK] Phase 7 complete — {len(images)} brief(s) queued.")
            print("     Run with --live to generate real images.")
        else:
            print(f"[OK] Phase 7 complete — {len(images)} image(s) generated.")
            print("     Saved to: data/generated_images/ + social-manager-ui/public/generated/")
    except Exception as e:
        print(f"[FAIL] Phase 7: {e}")

    if not mock_mode:
        print_quota_status()

    elapsed = (datetime.now() - start).seconds
    results["Total runtime"] = f"{elapsed}s"
    print_summary(results)


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--reset" in args:
        if os.path.exists(QUOTA_STATE_FILE):
            os.remove(QUOTA_STATE_FILE)
            print(f"[RESET] Quota state cleared.")
        args = [a for a in args if a != "--reset"]

    live_mode = "--live" in args
    if live_mode:
        print("\n  LIVE MODE — Real API calls + image generation will run.")
        print("   Phase 7 calls Pollinations.ai (100% free, no API key needed).")
        print("   Press Ctrl+C within 3 seconds to cancel.\n")
        time.sleep(3)

    run_engine(mock_mode=not live_mode)