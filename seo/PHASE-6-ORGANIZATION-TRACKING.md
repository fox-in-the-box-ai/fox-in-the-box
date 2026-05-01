# Phase 6: Organization & Tracking Setup

**Goal:** Create master tracking system and set up ongoing measurement infrastructure.

**Timeline:** Week 3, Days 3-5 | ~4-5 hours

**Dependencies:** All previous phases ✅ Complete

---

## To-Do List

### Step 1: Build Master Keyword Spreadsheet (1 hour)

- [ ] Create comprehensive tracking sheet: `seo/SEO-MASTER-TRACKER.csv`

**This is your single source of truth for all keywords.**

**Columns to include:**
```
Rank,
Keyword,
Search_Volume,
Keyword_Difficulty,
Intent_Type,
Tier,
Content_Type,
Target_URL,
Blog_Series,
Blog_Post_Title,
Publishing_Month,
Current_Status,
Draft_Link,
Published_Date,
Current_SERP_Position,
Current_Traffic_Month,
Current_Backlinks,
Last_Updated,
Notes
```

- [ ] Populate with:
  - All Tier 1 keywords (40)
  - All Tier 2 keywords (30)
  - All Tier 3 / long-tail keywords (50+)
  - Total: 120+ keywords minimum

- [ ] Import data from:
  - `keyword-targets-final.csv` (from Phase 2)
  - `keyword-to-content-mapping.csv` (from Phase 3)
  - `long-tail-question-keywords.csv` (from Phase 5)

- [ ] Format as Google Sheet OR Excel for easy collaboration/updates

- [ ] Create multiple view tabs:
  - [ ] **Master** — all keywords, all data
  - [ ] **By Month** — filtered to Month 1, 2, 3 content plan
  - [ ] **By Status** — Backlog, In Progress, Published, Ranking
  - [ ] **By Tier** — Tier 1, 2, 3
  - [ ] **Dashboard** — summary stats

### Step 2: Set Up Search Console Tracking (1.5 hours)

- [ ] **Create/verify Google Search Console account**
  - [ ] Go to: https://search.google.com/search-console
  - [ ] Verify/add your site (foxinthebox.io)
  - [ ] Add property for your blog subdomain if separate

- [ ] **Create custom keyword tracking in GSC**
  - [ ] Note: GSC shows impressions + CTR automatically, but we'll build custom filters

- [ ] Create Google Sheet connected to GSC data: `seo/GSC-DASHBOARD.csv`

**Daily/Weekly tracking (set a recurring task to update):**
```
Date,
Keyword,
Impressions,
Clicks,
Avg_Position,
CTR_%,
Trend_vs_Week_Ago
```

- [ ] Set up automated Google Sheets function (if possible):
  - Use Google Data Studio to pull GSC data into Sheets
  - Or: Manual weekly export from GSC → paste into tracker

- [ ] Create filters:
  - [ ] "Hermes" keywords only
  - [ ] "Fox in the box" keywords
  - [ ] Keywords with 0 impressions (not yet ranking)
  - [ ] Keywords in top 10 (winning keywords)

### Step 3: Set Up Google Analytics 4 Goals (1 hour)

- [ ] **Set up conversion tracking in GA4**
  - [ ] If not already configured: https://analytics.google.com

- [ ] **Create Goals for:**
  - [ ] CTA Clicks: "Download Fox in the Box"
  - [ ] CTA Clicks: "Visit GitHub" (for Hermes info)
  - [ ] Email signup (if applicable)
  - [ ] Time on page > 2 minutes (engagement)
  - [ ] Scroll depth > 50% (engagement)

- [ ] **Create segments:**
  - [ ] "Organic Search" traffic
  - [ ] "Hermes Keywords" traffic
  - [ ] "Direct from SERP" (high intent)

- [ ] Create GA4 dashboard: `seo/GA4-DASHBOARD-SETUP.md`
  - Document which events to track
  - Document which custom events to implement on site

### Step 4: Backlink Tracking Setup (1 hour)

- [ ] Create file: `seo/backlink-tracking.csv`

**Columns:**
```
Date_Acquired,
URL_Receiving_Link,
Referring_Domain,
Referring_URL,
Anchor_Text,
Link_Type (NoFollow/DoFollow),
Link_Value_Est (Low/Medium/High),
Associated_Keyword,
Source (Organic/Outreach/Mention),
Status
```

- [ ] Initial seeding:
  - [ ] Do a backlink audit now (before you have links)
  - [ ] Use Ahrefs free extension to check what exists

- [ ] Ongoing tracking:
  - [ ] Monthly: Export from Ahrefs/SEMrush if using paid
  - [ ] Or: Manual tracking of outreach results

### Step 5: Monthly Reporting Template (1 hour)

- [ ] Create file: `seo/MONTHLY-REPORT-TEMPLATE.md`

**This becomes your recurring review document.**

```markdown
# SEO Report — [MONTH/YEAR]

## Executive Summary
- Total organic impressions: ___
- Total clicks from organic: ___
- Avg position: ___
- New keywords ranking: ___
- Keywords in top 10: ___

## Traffic
- New users from organic: ___
- Total sessions: ___
- Conversion rate (Fox in the Box CTA): ___%
- Revenue attributed (if applicable): $___

## Content Published This Month
- [ ] Blog posts published: ___ (titles)
- [ ] Landing pages updated: ___ (URLs)
- [ ] Total word count: ___ words
- [ ] Total traffic to new content: ___ visits

## Ranking Changes
- Keywords improved (moved up): ___ keywords
  - Best performer: "[keyword]" (now rank __)
- Keywords declined (moved down): ___ keywords
  - Watch list: "[keyword]" (now rank __)
- New keywords ranking: ___ keywords (top 100)

## Backlinks
- Total new backlinks: ___
- High-quality backlinks: ___
- Referring domains: ___
- Outreach successes: ___ (count)

## Opportunities & Next Month
- [ ] Biggest wins this month: ___
- [ ] Biggest challenges: ___
- [ ] Keywords to prioritize next month: ___
- [ ] Content to refresh/update: ___
- [ ] Outreach targets: ___ (count)

## Month-over-Month Comparison
| Metric | Last Month | This Month | Change |
|--------|-----------|-----------|--------|
| Impressions | ___ | ___ | ___ |
| Clicks | ___ | ___ | ___ |
| Keywords ranking | ___ | ___ | ___ |
| Traffic | ___ | ___ | ___ |

## Appendix: Raw Data
- [GSC export link]
- [GA4 report link]
- [Backlink audit export]
```

- [ ] Set calendar reminder: Last Friday of every month (report review)

### Step 6: Establish Baseline Metrics (30 min)

- [ ] Capture starting point metrics (Month 0):

- [ ] Create file: `seo/BASELINE-METRICS.md`

```markdown
# SEO Baseline — [Date]

## Pre-Launch Status
- **Domain age:** ___ years
- **Current organic traffic:** ___ visits/month (if any)
- **Indexed pages:** ___ (check Google Search Console)
- **Backlinks to site:** ___ (check Ahrefs)
- **DA/PA estimate:** ___ / ___ (Ahrefs)
- **Current ranking keywords:** ___ (all keywords, any position)
- **Keywords in top 50:** ___
- **Keywords in top 10:** ___

## Tier 1 Keyword Status (Initial)
| Keyword | Current Position | Difficulty | Volume |
|---------|------------------|-----------|--------|
| hermes agent docker | Not ranking (>50) | 45 | 1200 |
| what is hermes agent | Not ranking | 38 | 850 |
| ... | ... | ... | ... |

## Target Projections
**Within 6 months:**
- Tier 1 keywords ranking in top 20: 10+ keywords
- Tier 1 keywords ranking in top 10: 3-5 keywords
- Estimated organic traffic: 1,000-2,000 visits/month

**Within 12 months:**
- Tier 1 + 2 keywords ranking: 50+ keywords in top 20
- 10+ keywords in top 10
- Estimated organic traffic: 5,000-10,000 visits/month

## Monthly Review Dates
- Month 1 review: [Date]
- Month 2 review: [Date]
- Month 3 review: [Date]
- Monthly ongoing: Last Friday of each month
```

### Step 7: Content Publishing Workflow (1 hour)

- [ ] Create file: `seo/CONTENT-PUBLISHING-WORKFLOW.md`

**Document the process for publishing optimized content:**

```markdown
## Content Publishing Checklist

### Pre-Writing (Planning)
- [ ] Keyword assigned from master tracker
- [ ] Target URL decided (URL slug = keyword-aligned)
- [ ] Content brief prepared (outline + CTA)
- [ ] Related keywords identified for natural mention
- [ ] Internal links planned (to which pages?)

### Writing
- [ ] First draft completed
- [ ] Word count: [target based on content type]
- [ ] H1 tag = main keyword (only one H1)
- [ ] H2/H3 = related keywords, naturally
- [ ] Images added (alt text includes keyword)
- [ ] Links added (internal: 3-5, external: 2-3)

### Optimization
- [ ] Meta title (60 char max, keyword-first)
- [ ] Meta description (160 char max, CTA included)
- [ ] URL slug: lowercase, hyphens, keyword-aligned
- [ ] Headers structure: H1 → H2 → H3 (logical flow)
- [ ] Images: Compressed, alt text, descriptive filenames
- [ ] Internal links: Anchor text = target keyword
- [ ] External links: High-authority, relevant sources

### Publishing
- [ ] Content uploaded to CMS
- [ ] Preview checked on desktop + mobile
- [ ] Links tested (all working?)
- [ ] Images loaded properly?
- [ ] Page speed checked (target: <3 sec)

### Post-Publishing
- [ ] Update master tracker: Published_Date + URL
- [ ] Add to GSC search console (if new URL)
- [ ] Share on social (Twitter, LinkedIn, etc.)
- [ ] Alert relevant communities (Reddit, Dev.to, etc.)
- [ ] Plan outreach for backlinks
- [ ] Set 30-day review reminder

### 30-Day Review
- [ ] Check GSC: Any impressions yet? Ranking position?
- [ ] Check Google Analytics: Traffic?
- [ ] Check engagement: Time on page, scroll depth?
- [ ] If not ranking: Identify why, plan refresh content
- [ ] If ranking but low CTR: Improve meta description
- [ ] If ranking top 10: Start backlink outreach
```

### Step 8: Quarterly Review Process (30 min)

- [ ] Create file: `seo/QUARTERLY-REVIEW-PROCESS.md`

```markdown
## Quarterly SEO Review

**Timing:** Every 3 months (March 31, June 30, Sept 30, Dec 31)

### Review Meeting Agenda (2-3 hours)

**Part 1: Wins & Learnings (30 min)**
- Which keywords exceeded expectations?
- Which blog posts had highest conversion?
- What content format worked best?
- What was most surprising?

**Part 2: Data Analysis (60 min)**
- Traffic growth: Month 1 vs Month 3?
- Ranking progress: How many Tier 1 in top 20?
- Backlink growth: Quality vs quantity?
- Conversion data: CTA performance?
- Compare to projections: On track?

**Part 3: Gap Analysis (30 min)**
- Which Tier 1 keywords are NOT ranking? Why?
- Which content underperformed? Why?
- Missed opportunities?
- Competitive changes (did competitors improve)?

**Part 4: Action Planning (30 min)**
- Refresh content: Which pieces need updates?
- New outreach: New backlink opportunities?
- Pivots: Should we shift keyword focus?
- Next quarter priorities: Which keywords matter most?

### Deliverable: Quarterly Summary
- Create `seo/QUARTERLY-REVIEW-Q[N].md`
- Document findings, wins, failures, plan
```

### Step 9: Create Master Tracker Navigation (30 min)

- [ ] Create file: `seo/TRACKER-GUIDE.md`

**This helps anyone on the team use the system:**

```markdown
# SEO Tracking System Guide

## File Structure

```
seo/
├── SEO-MASTER-TRACKER.csv          ← Main keyword database
├── GSC-DASHBOARD.csv               ← Search Console data
├── GA4-DASHBOARD-SETUP.md          ← Analytics events
├── backlink-tracking.csv           ← Link tracking
├── MONTHLY-REPORT-TEMPLATE.md      ← Monthly reviews
├── BASELINE-METRICS.md             ← Starting point
├── CONTENT-PUBLISHING-WORKFLOW.md  ← How to publish
├── QUARTERLY-REVIEW-PROCESS.md     ← Quarterly reviews
├── TRACKER-GUIDE.md                ← This file
│
├── phases/                         ← Research phases
│   ├── PHASE-1-SEED-LIST.md
│   ├── PHASE-2-VOLUME-DIFFICULTY.md
│   ├── PHASE-3-SEARCH-INTENT.md
│   ├── PHASE-4-COMPETITIVE-LANDSCAPE.md
│   ├── PHASE-5-LONG-TAIL.md
│   └── PHASE-6-ORGANIZATION-TRACKING.md (this file)
│
├── research/                       ← Supporting documents
│   ├── keyword-research-master.csv
│   ├── keyword-targets-final.csv
│   ├── keyword-to-content-mapping.csv
│   ├── content-calendar-final.md
│   ├── competitor-*.md
│   ├── backlink-opportunities.md
│   └── ...
│
└── reports/                        ← Monthly/quarterly reports
    ├── MONTHLY-REPORT-2025-01.md
    ├── QUARTERLY-REVIEW-Q1.md
    └── ...
```

## How to Use the System

**Starting a new month:**
1. Open SEO-MASTER-TRACKER.csv
2. Filter by "Publishing_Month = [Current Month]"
3. Use CONTENT-PUBLISHING-WORKFLOW.md to guide writing
4. Update tracker as content publishes

**Monthly review:**
1. Export GSC data → update GSC-DASHBOARD.csv
2. Export GA4 data → add to MONTHLY-REPORT
3. Follow MONTHLY-REPORT-TEMPLATE.md
4. Archive report in `reports/`

**Quarterly deep-dive:**
1. Gather all monthly reports
2. Follow QUARTERLY-REVIEW-PROCESS.md
3. Create QUARTERLY-REVIEW-Q[N].md
4. Plan next quarter priorities

**Tracking a specific keyword:**
1. Search SEO-MASTER-TRACKER.csv for keyword
2. Check: Current_SERP_Position, Current_Traffic_Month
3. Look at MONTHLY reports to see history
4. Analyze in GSC if ranking, GA4 if driving traffic
```

---

## Deliverables

✅ **Output files:**
- `SEO-MASTER-TRACKER.csv` — 120+ keywords, all data, sortable views
- `GSC-DASHBOARD.csv` — weekly/monthly tracking from Search Console
- `GA4-DASHBOARD-SETUP.md` — goals, events, segments configured
- `backlink-tracking.csv` — backlink sources + dates
- `MONTHLY-REPORT-TEMPLATE.md` — recurring report format
- `BASELINE-METRICS.md` — starting point metrics
- `CONTENT-PUBLISHING-WORKFLOW.md` — step-by-step publishing checklist
- `QUARTERLY-REVIEW-PROCESS.md` — quarterly deep-dive process
- `TRACKER-GUIDE.md` — navigation + how to use system

✅ **Systems configured:**
- Google Search Console: Keywords + position tracking
- Google Analytics 4: Conversion goals + segments
- Monthly reporting: Last Friday of each month
- Quarterly review: Every 3 months (Q1, Q2, Q3, Q4)

---

## Calendar Setup

- [ ] Set recurring calendar reminders:
  - **Weekly:** Monday @ 9am — Check GSC for any new rankings
  - **Monthly:** Last Friday @ 2pm — Monthly review + report
  - **Quarterly:** End of Q1/Q2/Q3/Q4 — Quarterly deep-dive

---

## Next Steps → Implementation

Once complete, you're ready to move to **PHASE-7-TOOLS-AND-AUTOMATION.md**
