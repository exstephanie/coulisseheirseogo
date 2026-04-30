# Coulisse Heir SEO Agent v3 — Setup Guide

## Setup Status (as of 2026-04-30)

| Secret / Config | Status | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Set | Direct Anthropic key |
| `WP_URL` | ✅ Set | https://coulisseheir.com |
| `WP_USERNAME` | ✅ Set | ad_chadmin |
| `WP_APP_PASSWORD` | ✅ Set | Generated via WP Profile → Application Passwords |
| `BRAND` | ✅ Set | coulissehair |
| `SITE_URL` | ✅ Set | https://coulisseheir.com/ |
| `NOTIFICATION_EMAIL` | ✅ Set | stephanie.au@exgroup.com.sg |
| `GMAIL_USER` | ✅ Set | coulisseheir.seo@gmail.com |
| `GMAIL_APP_PASSWORD` | ✅ Set | Gmail App Password |
| `GSC_CREDENTIALS_JSON` | ⏳ Pending | Need to identify GSC account owner for coulisseheir.com |
| `PEXELS_API_KEY` | ⏳ Optional | For featured images — get free key at pexels.com/api |
| Vault: brand_voice.md | ✅ Done | Populated from coulisseheir.com |
| Vault: locations.json | ✅ Done | ION Orchard #04-02 |
| Vault: services.json | ✅ Done | 8 services with real pricing |
| Vault: faqs.json | ✅ Done | 6 FAQs |
| Vault: stylists.json | ✅ Done | Nico Tan, Gina, KG |

**Agent is ready to run.** GSC data is optional — the agent will generate content from vault data without it.

To trigger a manual run: **GitHub → Actions → Coulisse Heir SEO Agent v3 → Run workflow → weekly**

---

---

## What This Agent Does

**Every Monday (Weekly Council Session):**
1. Pulls real keyword data from Google Search Console
2. Crawls and audits coulisseheir.com for technical issues
3. Convenes the Expert Council (5 SEO personas debate your data)
4. Produces a PDCA weekly plan with specific tasks, targets, and contingencies
5. Writes and publishes a keyword-targeted blog post to WordPress
6. Saves a full Markdown report to `reports/weekly/`

**Tuesday–Sunday (Daily Lightweight Run):**
1. Quick site audit (catches regressions fast)
2. Publishes the next scheduled blog post if it's a posting day

**Expert Council Members:**
- 📈 Neil Patel — growth, content volume, conversion
- 🎯 Rand Fishkin — brand signals, audience, 10x content  
- 📍 Joy Hawkins — Google Business Profile, local pack
- 🔗 Brian Dean — backlinks, topical authority
- 💰 Wil Reynolds — revenue attribution, real business outcomes

---

## Step 1: Prerequisites

- Python 3.11+
- A GitHub account (free)
- coulisseheir.com WordPress admin access
- Google Search Console access for coulisseheir.com
- Anthropic API key

---

## Step 2: Clone and Configure

```bash
git clone https://github.com/YOUR_USERNAME/coulissehair-seo-v2.git
cd coulissehair-seo-v2
cp .env.example .env
pip install -r requirements.txt
```

Edit `.env` — you need all 3 sections filled.

---

## Step 3: Google Search Console API

### 3a. Create Google Cloud Project
1. Go to https://console.cloud.google.com/
2. New project → name it "Coulisse Heir SEO Agent"
3. APIs & Services → Library → Search "Search Console API" → Enable

### 3b. Create Service Account
1. APIs & Services → Credentials → Create Credentials → Service Account
2. Name: `coulissehair-seo-agent` → Create → Done
3. Click the service account → Keys → Add Key → JSON → Download
4. Save as `config/gsc_credentials.json`

### 3c. Grant Access in Search Console
1. Copy service account email (e.g. `coulissehair-seo-agent@project.iam.gserviceaccount.com`)
2. Go to https://search.google.com/search-console/
3. Select coulisseheir.com property
4. Settings → Users and permissions → Add user
5. Paste email → Restricted → Add

---

## Step 4: WordPress Application Password

1. Log in to WordPress Admin → `https://coulisseheir.com/wp-admin/`
2. Users → Your Profile → scroll to **Application Passwords**
3. Name: `SEO Agent` → Add New Application Password
4. Copy the generated password (format: `AbCd EfGh IjKl MnOp QrSt UvWx`)
5. Add to `.env`:
   ```
   WP_USERNAME=your_admin_username
   WP_APP_PASSWORD=AbCd EfGh IjKl MnOp QrSt UvWx
   ```

**Requires:** WordPress 5.6+ with HTTPS enabled

---

## Step 5: Test Locally

```bash
# Test weekly council session
python seo_agent.py --weekly

# Test daily run
python seo_agent.py --daily
```

First run uses demo data if GSC not connected. Check `reports/weekly/` for output.

---

## Step 6: Deploy to GitHub Actions

### 6a. Push to GitHub
```bash
git init
git add .
git commit -m "Coulisse Heir SEO Agent v2.0"
git remote add origin https://github.com/YOUR_USERNAME/coulissehair-seo-v2.git
git push -u origin main
```

### 6b. Add GitHub Secrets
Repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `GSC_CREDENTIALS_JSON` | Full contents of `config/gsc_credentials.json` |
| `WP_URL` | `https://coulisseheir.com` |
| `WP_USERNAME` | WordPress admin username |
| `WP_APP_PASSWORD` | Application Password from Step 4 |
| `WP_POST_STATUS` | `draft` (recommended to start) |
| `WP_POST_DAYS` | `mon,wed,fri` |

### 6c. Enable Actions
GitHub repo → Actions → Enable workflows

---

## Understanding the Weekly PDCA Report

Reports saved to `reports/weekly/week_XX_YYYY-MM-DD.md`

| Section | What It Contains |
|---------|-----------------|
| 🧠 Council Verdict | The expert panel's single most important priority this week |
| 📊 Scorecard | Clicks, impressions, position, audit score vs last week's targets |
| 💡 Expert Insights | Each of 5 personas' key observation and recommendation |
| 📋 PLAN | This week's theme, focus area, and measurable targets |
| ✅ DO | Prioritised action list with owner (Agent vs You vs Team) |
| ✍️ Content Plan | Blog posts to write with keyword, intent, urgency |
| 📍 GBP Posts | Ready-to-post Google Business Profile ideas |
| ⚠️ Technical Issues | SEO audit findings prioritised by severity |
| 🎯 Quick-Wins | Keywords in positions 11-30 sorted by opportunity |
| 🔍 CHECK | How to know if this week worked; success definition |
| 🔄 ACT | Next week contingency: if on track / behind / ahead |
| 📬 Message to Daniel | Direct advice for what YOU should personally do |

---

## PDCA Memory System

The agent remembers every week in `memory/pdca_state.json`:
- What was planned
- What was executed
- Whether targets were met
- Trend data across all weeks

This means every week's plan is informed by all previous weeks.
The council's recommendations evolve as the data does.

---

## File Structure

```
coulissehair-seo-v2/
├── seo_agent.py                    # Main orchestrator
├── agents/
│   ├── personas.py                 # 5 expert personas + council prompt
│   ├── memory.py                   # PDCA state persistence
│   ├── council_agent.py            # Multi-persona debate engine
│   ├── content_agent.py            # Council-directed content writer
│   ├── weekly_reporter.py          # PDCA report generator
│   ├── gsc_agent.py                # Google Search Console
│   ├── crawler_agent.py            # Site crawler + audit
│   └── wordpress_agent.py          # WordPress REST API publisher
├── config/
│   └── gsc_credentials.json        # GSC service account (gitignored)
├── memory/
│   └── pdca_state.json             # Persistent PDCA state
├── reports/
│   ├── weekly/                     # Weekly PDCA reports
│   └── daily/                      # Daily audit logs
├── .github/workflows/seo_pdca.yml  # GitHub Actions schedule
├── requirements.txt
├── .env.example
└── SETUP.md
```

---

## Monthly Cost Estimate

| Item | Cost |
|------|------|
| Anthropic API (council + content) | ~$8–15 SGD/month |
| GitHub Actions | Free |
| Google Search Console API | Free |
| **Total** | **~$8–15 SGD/month** |
