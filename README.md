<div align="center">

# 🤖 Social Media Automation Engine

**A 7-phase multi-agent system that does a social media manager's job.**

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_Vision-8E75B2?style=flat-square&logo=googlegemini&logoColor=white)
![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup-43B02A?style=flat-square&logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=flat-square&logo=pandas&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js_UI-000000?style=flat-square&logo=nextdotjs&logoColor=white)

</div>

---

## What it does

Most "AI social media tools" are a single prompt behind a text box. This is a **pipeline**:
seven specialised agents, each with one job, running in sequence and passing structured
state forward — from competitor intelligence all the way to a generated image, ready to post.

```
python main.py            # mock mode — safe, no real API calls, free to iterate
python main.py --live     # live mode — real scraping, real AI, real image generation
python main.py --reset    # wipe quota state, then run live
```

## The seven phases

| # | Agent | Job |
|---|---|---|
| 1 | **Spy** | 7-day competitor scrape — posts *and* comment threads |
| 2 | **Auditor** | Deep competitive analysis, content-gap detection, flags image posts |
| 3 | **Image Analyst** | Reads competitor image posts through the **Gemini Vision API** |
| 4 | **Trend Hijack** | Scores world trends; drafts posts only for trends scoring ≥ 7 |
| 5 | **Architect** | Drafts threads, replies, competitor responses and image briefs |
| 6 | **Engagement** | Community reply drafts, on the *Golden Hour* protocol |
| 7 | **Image Generator** | Renders the briefs via **Pollinations.ai** — free, no API key |

Every phase is fault-isolated: one agent failing degrades the run, it doesn't kill it. The
orchestrator reports per-phase results and a final structured summary.

## Design decisions worth noting

**Dual-mode by default.** Mock mode is the *default*, not an afterthought. Developing against
live APIs burns quota and money on every iteration, so the whole pipeline runs end-to-end on
fixtures until you explicitly pass `--live`.

**Quota is state, not hope.** LLM call budgets are persisted to a quota state file and printed
before every live run. `--reset` is the deliberate escape hatch.

**Brand voice is config, not prompt soup.** `config/brand_voice.json` holds the voice
definition once; every drafting agent reads from it, so tone stays consistent across threads,
replies and image briefs.

**Scoring before generating.** The Trend Hijack agent scores trends and only drafts for the
ones clearing the threshold — the expensive step never runs on noise.

## Layout

```
main.py                            # orchestrator — phase sequencing, fault isolation, summary
agents/
  spy_agent.py                     # 1 · competitor scraping
  auditor_agent.py                 # 2 · gap analysis
  image_analyst_agent.py           # 3 · Gemini Vision
  trend_hijack_agent.py            # 4 · trend scoring
  architect_agent.py               # 5 · content drafting
  engagement_agent.py              # 6 · reply drafting
  image_generator_agent.py         # 7 · image generation
  gemini_utils.py                  # shared client + quota accounting
config/
  brand_voice.json                 # single source of tone
  settings.py                      # runtime configuration
social-manager-ui/                 # Next.js dashboard for reviewing drafts
```

## Getting started

```bash
pip install -r requirements.txt

cp .env.example .env               # add GEMINI_API_KEY for live mode
python main.py                     # mock run — no keys needed

cd social-manager-ui && npm install && npm run dev   # review dashboard
```

Mock mode needs no credentials at all, so you can see the full pipeline before deciding
whether to wire up keys.

## Stack

`Python` · `Gemini Vision API` · `Pollinations.ai` · `BeautifulSoup` · `Pandas` · `Tweepy`
· `python-dotenv` · `schedule` · `Next.js` (review UI)

---

<div align="center">
Built by <a href="https://github.com/dhruv9097">Dhruv Singh</a>
</div>
