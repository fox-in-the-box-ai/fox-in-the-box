# Phase 7: Tools & Automation

**Goal:** Set up and optimize the SEO tech stack for ongoing management.

**Timeline:** Week 4, Days 1-3 | ~4-5 hours

**Dependencies:** PHASE-6-ORGANIZATION-TRACKING.md ✅ Complete

---

## To-Do List

### Step 1: Free Tools Setup (1.5 hours)

- [ ] **Google Search Console (GSC)**
  - [ ] Site added and verified
  - [ ] Property settings reviewed
  - [ ] Sitemap submitted (if site ready)
  - [ ] URL inspection tested
  - [ ] Performance report bookmarked

- [ ] **Google Analytics 4 (GA4)**
  - [ ] GA4 property created
  - [ ] Tracking code installed on site
  - [ ] Goals configured (5+ conversion points)
  - [ ] Custom events set up (scroll depth, video play, etc.)
  - [ ] Segments created (organic traffic, hermes keywords)
  - [ ] Dashboard built for monthly review

- [ ] **Google Keyword Planner**
  - [ ] Account set up (from Phase 2)
  - [ ] Saved keyword lists created:
    - [ ] "Tier 1 Keywords"
    - [ ] "Tier 2 Keywords"
    - [ ] "Question Keywords"
  - [ ] Planner bookmarked for regular checks

- [ ] **Answer The Public**
  - [ ] Account created
  - [ ] Core keywords saved
  - [ ] Monthly check scheduled (reminder)

- [ ] **Ubersuggest**
  - [ ] Free trial activated
  - [ ] Top 15 Tier 1 keywords researched
  - [ ] Data exported to tracker

### Step 2: Browser Extensions Setup (30 min)

- [ ] Install **Ahrefs SEO Toolbar** (free Chrome extension)
  - [ ] https://chrome.google.com/webstore
  - [ ] Check DA/PA on any page instantly
  - [ ] Useful for backlink research

- [ ] Install **Ubersuggest Extension** (free)
  - [ ] Quick keyword difficulty on search results
  - [ ] Volume estimates inline

- [ ] Install **SERPstat** or similar (optional, free tier)
  - [ ] Free SERP tracking for 5 keywords
  - [ ] Set up tracking for top 5 Tier 1 keywords

- [ ] Create bookmark folder: `SEO Tools` in browser
  - [ ] GSC, GA4, Ubersuggest, Answer The Public, Planner links

### Step 3: Rank Tracking Setup (1.5 hours)

- [ ] **Option 1: Free Manual Tracking**
  - [ ] Create sheet: `seo/rank-tracking-manual.csv`
  - [ ] Columns: Keyword, Date, Google Position, Bing Position, Notes
  - [ ] Monthly check: Search each Tier 1 keyword, record position
  - [ ] Effort: 30 min/month, accurate for top 10 positions

- [ ] **Option 2: Free SERPstat (limited)**
  - [ ] Sign up: https://serpstat.com
  - [ ] Free tier: 5 keywords tracked daily
  - [ ] Set to track: Top 5 Tier 1 keywords
  - [ ] Export data monthly to your tracker
  - [ ] Effort: 5 min/month, automatic daily checks

- [ ] **Option 3: Paid (if budget allows)**
  - [ ] SEMrush: $99+/month (full suite)
  - [ ] Ahrefs: $99+/month (full suite)
  - [ ] Moz: $99+/month (full suite)
  - [ ] Serptech: $29+/month (rank tracking only)
  - For now: **Start with free manual tracking**, upgrade if needed

- [ ] Create file: `seo/RANK-TRACKING-SETUP.md`
  - Document your chosen method
  - Create schedule: Which day of week to check?

### Step 4: Content Workflow Tools (1 hour)

- [ ] **Set up writing workflow:**
  - [ ] GitHub/GitLab repo for blog content? (optional)
    - Allows version control, review, collaboration
  - [ ] OR: Google Docs folder for drafts
    - Easier for non-technical writers

- [ ] **Create content management:**
  - [ ] If using CMS (WordPress, Webflow, etc.):
    - [ ] SEO plugin installed (Yoast, RankMath, etc.)
    - [ ] SEO checklist created before publishing
  - [ ] Create file: `seo/PRE-PUBLISH-CHECKLIST.md` (from Phase 6)

- [ ] **Set up internal linking tool (optional):**
  - [ ] Use: Manual spreadsheet tracking related links
  - [ ] Or: Plugin like Link Whisper (paid, ~$77)
  - [ ] Goal: Build topic clusters, 3-5 internal links per post

### Step 5: Backlink Monitoring Tools (1 hour)

- [ ] **Option 1: Manual Tracking**
  - [ ] Use: `seo/backlink-tracking.csv` (from Phase 6)
  - [ ] When you get a backlink: Add to spreadsheet
  - [ ] Tools: Ahrefs extension to verify (free)

- [ ] **Option 2: Automated Monitoring (Paid)**
  - [ ] Set up: Google Alerts for brand mentions
    - [ ] Create alerts: "fox in the box", "foxinthebox.io", "hermes agent docker"
    - [ ] Receive email notifications when mentioned
  - [ ] Or: Mention monitoring tool (free tier often available)
    - Mention.com, Notificare, or similar

- [ ] **Option 3: Ahrefs/SEMrush (if budget allows)**
  - [ ] Monthly backlink reports (automated)
  - [ ] Competitor backlink tracking
  - [ ] New backlink notifications

- [ ] Create file: `seo/BACKLINK-MONITORING-SETUP.md`

### Step 6: Google Sheets Automation (1 hour)

- [ ] **Create automated monthly report:**

- [ ] Using Google Sheets + Google Forms (free):
  - [ ] Create form: `seo/monthly-data-collection-form.md`
  - [ ] Form fields:
    - Date
    - GSC impressions (copy from GSC)
    - GSC clicks (copy from GSC)
    - GA4 organic traffic
    - New keywords ranking
    - Keywords in top 10
    - Backlinks acquired
    - Content published (count)
    - Notes/opportunities
  
  - [ ] Form responses auto-populate Google Sheet
  - [ ] Sheet calculates month-over-month % change
  - [ ] Dashboard chart auto-updates

- [ ] **Example Sheet structure:**
  ```
  Tab 1: Data Entry (Form responses)
  Tab 2: Trends (Charts + analysis)
  Tab 3: Dashboard (KPIs at a glance)
  Tab 4: Backlinks (Tracking)
  Tab 5: Rank Tracking (Manual or imported)
  ```

- [ ] Create file: `seo/GOOGLE-SHEETS-SETUP.md`
  - Document formulas used
  - Share permissions (read-only for stakeholders)

### Step 7: Automation Workflow Tools (1.5 hours)

- [ ] **Set up content calendar + workflow:**
  - [ ] Option A: Trello (free)
    - Create board: SEO Content Calendar
    - Columns: Backlog, Writing, Review, Published, Ranking
    - Cards: Blog post = card, move through columns
  
  - [ ] Option B: Airtable (free + paid tiers)
    - Create base: SEO Management
    - Tables: Keywords, Content, Backlinks, Rankings
    - Views: By month, by status, by keyword
  
  - [ ] Option C: GitHub Projects (free if using GitHub)
    - Create project: SEO Content
    - Issues = blog posts
    - Automate: Move to "Published" when merged

- [ ] **Set up recurring tasks/reminders:**
  - [ ] Google Calendar: Monthly review (last Friday)
  - [ ] Google Calendar: Weekly check (Monday morning)
  - [ ] Google Calendar: Content publish day (set day, e.g., Tuesday)

- [ ] Create file: `seo/WORKFLOW-TOOLS-SETUP.md`

### Step 8: Email Automation & Alerts (30 min)

- [ ] **Set up GSC email alerts:**
  - [ ] In GSC settings: Email alerts for critical issues
  - [ ] Alerts: Mobile usability, security issues, AMP errors

- [ ] **Create automated weekly digest:**
  - [ ] Option: Use Google Sheets + Google Script (free)
  - [ ] Weekly email: Current top keywords, new rankings, traffic
  - [ ] OR: Use Zapier free tier (5 tasks/month)
    - Trigger: Weekly
    - Action: Send email with GSC summary

- [ ] **News alerts for competitors:**
  - [ ] Google Alerts: "Nous Research hermes agent"
  - [ ] Google Alerts: "Claude Code alternatives"
  - [ ] Receive: Weekly digest of competitor news

### Step 9: Documentation & Process (30 min)

- [ ] Create file: `seo/TOOLS-STACK-SUMMARY.md`

```markdown
# SEO Tools Stack

## Free Tools (Tier 1 — must-have)
| Tool | Purpose | Setup Time | Monthly Cost |
|------|---------|-----------|--------------|
| Google Search Console | Position tracking, indexing | 15 min | Free |
| Google Analytics 4 | Traffic & conversions | 30 min | Free |
| Google Keyword Planner | Volume & CPC | 15 min | Free |
| Ahrefs Extension | DA/PA lookup | 5 min | Free |

## Free Tools (Tier 2 — optional)
| Tool | Purpose | Setup Time | Monthly Cost |
|------|---------|-----------|--------------|
| Answer The Public | Question keywords | 5 min | Free (limited) |
| Ubersuggest | Difficulty scores | 15 min | Free (3/day) |
| Google Alerts | News monitoring | 10 min | Free |

## Paid Tools (Consider if budget available)
| Tool | Purpose | Setup Time | Monthly Cost | Priority |
|------|---------|-----------|--------------|----------|
| Ahrefs / SEMrush | Full keyword suite | 30 min | $99+ | Medium |
| Rank tracking tool | Automated position tracking | 20 min | $29+ | Low |
| Mention.com | Brand mention monitoring | 15 min | $49+ | Low |

## Spreadsheet Automation (Free)
| System | Purpose | Setup Time | Cost |
|--------|---------|-----------|------|
| Google Sheets + Forms | Monthly reporting | 1 hour | Free |
| Google Calendar + Email | Reminders & alerts | 30 min | Free |
| GitHub Projects | Content workflow | 30 min | Free (if using GitHub) |

## Recommended Starting Stack
- GSC (required)
- GA4 (required)
- Keyword Planner (required)
- Ahrefs Extension (required)
- Google Sheets (required)
- Google Calendar (required)
- Answer The Public (optional)

**Total setup time:** ~2 hours
**Monthly cost:** $0
**Team accessibility:** High (all Google/free tools)
```

---

## Deliverables

✅ **Output files:**
- `RANK-TRACKING-SETUP.md` — your chosen tracking method + schedule
- `PRE-PUBLISH-CHECKLIST.md` — content quality gates before publishing
- `BACKLINK-MONITORING-SETUP.md` — how you'll track new links
- `GOOGLE-SHEETS-SETUP.md` — automation formulas + structure
- `WORKFLOW-TOOLS-SETUP.md` — content calendar tool (Trello/Airtable/GitHub)
- `TOOLS-STACK-SUMMARY.md` — overview of all tools in use
- `seo/rank-tracking-manual.csv` — empty template (if manual tracking)
- `seo/backlink-tracking.csv` — empty template for backlinks

✅ **Systems configured:**
- GSC position tracking: Daily
- GA4 conversion tracking: Real-time
- Monthly reporting: Automated via Google Forms + Sheets
- Rank checks: Weekly or monthly (depending on tool)
- Email alerts: Weekly digest setup
- Content workflow: Tool selected (Trello/Airtable/GitHub)

---

## Quick Reference: Monthly Maintenance

| Task | Frequency | Time | Tool |
|------|-----------|------|------|
| Check top keyword rankings | Weekly | 15 min | GSC or manual |
| Export GSC data | Monthly | 10 min | GSC → Sheets |
| Export GA4 data | Monthly | 10 min | GA4 → Sheets |
| Monthly report | Monthly | 60 min | Google Sheets |
| Update content calendar | Ongoing | 10 min/post | Trello/Airtable |
| Quarterly deep-dive | Quarterly | 2-3 hours | All tools |

---

## Common Pitfalls

⚠️ **Don't:**
- Rely on manual tracking for 100+ keywords (too time-consuming)
- Skip Google Analytics setup (you need conversion tracking!)
- Forget to set up email alerts (you'll miss opportunities)
- Use too many tools (complexity kills consistency)

✅ **Do:**
- Start simple (GSC + GA4 + manual sheet)
- Upgrade tools only when you need them
- Automate what you can (Google Sheets, email alerts)
- Review data consistently (weekly checks, monthly reports)

---

## Next Steps → Implementation Phase

Once complete, all research is done. Move to **START-WRITING-CONTENT.md**
