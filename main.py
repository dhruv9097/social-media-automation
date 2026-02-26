import os
import traceback

# ─────────────────────────────────────────────────────────────────────────────
# MOCK MODE SWITCH
# True  = no Apify credits used, uses built-in mock data (use while developing)
# False = live Apify scraping (flip when you have a paid Apify plan)
# ─────────────────────────────────────────────────────────────────────────────
USE_MOCK_DATA = True


def run_phase(name, fn):
    print(f"\n{'─'*50}")
    print(f"  {name}")
    print(f"{'─'*50}")
    try:
        result = fn()
        print(f"  [OK] {name} -- complete.")
        return result
    except Exception as e:
        print(f"  [FAIL] {name} -- FAILED: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


def run_growth_engine():
    print("MIC Growth Engine -- Starting...\n")
    print(f"  Mode: {'MOCK (no Apify credits)' if USE_MOCK_DATA else 'LIVE (Apify active)'}\n")

    # ── PHASE 1: Intelligence Gathering ──────────────────────────────────────
    from agents.spy_agent import SpyAgent
    run_phase(
        "PHASE 1 -- INTELLIGENCE GATHERING",
        lambda: SpyAgent().fetch_market_chatter(mock_mode=USE_MOCK_DATA)  # ← fix
    )

    # ── PHASE 2: Competitor Audit ─────────────────────────────────────────────
    from agents.auditor_agent import AuditorAgent
    run_phase(
        "PHASE 2 -- COMPETITOR AUDIT",
        lambda: AuditorAgent().run_full_audit(mock_mode=USE_MOCK_DATA)    # ← fix
    )

    # ── PHASE 3: Content Engineering ─────────────────────────────────────────
    from agents.architect_agent import ArchitectAgent
    architect_result = run_phase(
        "PHASE 3 -- CONTENT ENGINEERING",
        lambda: ArchitectAgent().run()
    )

    # ── PHASE 4: Community Management ────────────────────────────────────────
    from agents.engagement_agent import EngagementAgent
    engagement_result = run_phase(
        "PHASE 4 -- COMMUNITY MANAGEMENT (GOLDEN HOUR)",
        lambda: EngagementAgent().run_golden_hour_protocol(mock_mode=True)
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print("  ENGINE RUN COMPLETE")
    print(f"{'='*50}")

    drafts_count     = len(architect_result)  if architect_result  else 0
    engagement_count = len(engagement_result) if engagement_result else 0

    print(f"  Content drafts generated   : {drafts_count}")
    print(f"  Engagement drafts generated: {engagement_count}")
    print(f"\n  Open your Next.js Dashboard to review and approve.\n")


if __name__ == "__main__":
    run_growth_engine()