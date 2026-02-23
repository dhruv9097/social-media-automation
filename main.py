import os
from agents.spy_agent import SpyAgent
from agents.auditor_agent import AuditorAgent
from agents.architect_agent import ArchitectAgent
from agents.engagement_agent import EngagementAgent

def run_growth_engine():
    print(" Booting up the MIC Growth Engine...")

    try:
        # --- SAFELY MUTED ---
        # Step 1: Data Collection
        # print("\n--- PHASE 1: INTELLIGENCE GATHERING ---")
        # spy = SpyAgent()
        # spy.fetch_market_chatter()

        # Step 2: Gap Analysis & Strategy
        # print("\n--- PHASE 2: COMPETITOR AUDIT ---")
        # auditor = AuditorAgent()
        # auditor.run_full_audit()
        # -----
        
        
        # Step 3: Content Drafting
        print("\n--- PHASE 3: CONTENT ENGINEERING ---")
        architect = ArchitectAgent()
        architect.generate_content()

        # Step 4: Community Management (The Golden Hour)
        print("\n--- PHASE 4: COMMUNITY MANAGEMENT ---")
        engagement = EngagementAgent()
        engagement.run_golden_hour_protocol(mock_mode=True)

        print("\nAll systems nominal. Intelligence, Strategy, Execution, and Engagement completed.")
        print(" Open your Next.js Dashboard to review and approve.")

    except Exception as e:
        print(f"\n CRITICAL SYSTEM FAILURE: {e}")

if __name__ == "__main__":
    run_growth_engine()