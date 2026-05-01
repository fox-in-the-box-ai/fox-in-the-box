# Phase 2: Volume & Difficulty Assessment

**Goal:** Filter for high-opportunity keywords (volume > difficulty).

**Timeline:** Week 1, Days 3-5 | ~6-8 hours

**Dependencies:** PHASE-1-SEED-LIST.md ✅ Complete

---

## To-Do List

### Step 1: Google Keyword Planner Setup (1 hour)

- [ ] Create/access Google Ads account (free tier)
  - [ ] Visit: https://ads.google.com
  - [ ] Set up account if needed (no ad spend required)
  - [ ] Verify access to Keyword Planner

- [ ] Access Keyword Planner
  - [ ] Navigate to: Tools & Settings → Keyword Planner
  - [ ] Select: "Discover new keywords"

- [ ] Upload seed keywords
  - [ ] Export `keyword-research-master.csv` 
  - [ ] Paste all keywords into Keyword Planner search box (or use CSV upload if available)
  - [ ] Filter by:
    - [ ] Location: Global (then later: Poland for local relevance context)
    - [ ] Language: English
    - [ ] Network: Google Search

- [ ] Export results
  - [ ] Download CSV: `google-keyword-planner-results.csv`
  - [ ] Columns needed: Keyword, Avg Monthly Searches, Competition Level
  - [ ] Paste into master spreadsheet under "Volume" and "Planner_Competition"

### Step 2: Ubersuggest Free Trial (2 hours)

- [ ] Create Ubersuggest account: https://ubersuggest.com
  - [ ] Free tier: 3 searches/day
  - [ ] Plan to do this over 10 days if full analysis needed

- [ ] Research top 15 Priority 1 keywords:
  - [ ] hermes agent docker
  - [ ] hermes agent setup
  - [ ] hermes agent install
  - [ ] hermes ai docker
  - [ ] fox in the box ai
  - [ ] hermes agent self-host
  - [ ] llm docker container
  - [ ] ollama docker
  - [ ] self hosted ai
  - [ ] hermes vs cursor
  - [ ] hermes vs claude
  - [ ] hermes agent tutorial
  - [ ] hermes ai setup
  - [ ] ollama setup
  - [ ] local llm desktop

- [ ] For each keyword, capture:
  - [ ] Search Volume (from Ubersuggest)
  - [ ] SEO Difficulty (0-100 score)
  - [ ] Paid Difficulty
  - [ ] SERP Overview (top 3 ranking domains)
  - [ ] Add to master spreadsheet under "Ubersuggest_Volume" and "Ubersuggest_Difficulty"

- [ ] Export SERP data:
  - [ ] For each top 15 keyword, screenshot or export the SERP overview
  - [ ] Create folder: `seo/serp-snapshots/` 
  - [ ] Save as: `SERP-[keyword].png` or `.txt`

### Step 3: Answer The Public Research (1 hour)

- [ ] Visit: https://answerthepublic.com (free tier)

- [ ] Search these core keywords:
  - [ ] "hermes agent"
  - [ ] "hermes ai"
  - [ ] "fox in the box"
  - [ ] "ollama"
  - [ ] "self hosted ai"

- [ ] For each, capture:
  - [ ] **Questions** people ask (e.g., "How to install hermes agent?")
  - [ ] **Prepositions** (Hermes agent + before, after, vs, with, near...)
  - [ ] **Comparisons** (Hermes vs X, X vs Hermes)

- [ ] Create file: `seo/answer-the-public-findings.md`
  - [ ] Group questions by semantic category
  - [ ] Example categories: Installation, Comparison, Tutorials, Troubleshooting
  - [ ] Note which questions are highest-intent (likely searchable)

### Step 4: Manual SERP Difficulty Analysis (2 hours)

**For each Tier 1 keyword (top 15), analyze:**

- [ ] Google the keyword directly
- [ ] Document top 3 ranking results:
  - [ ] Rank 1 URL, Title, Domain Authority (guess based on domain)
  - [ ] Rank 2 URL, Title, Domain Authority
  - [ ] Rank 3 URL, Title, Domain Authority

- [ ] For each result, note:
  - [ ] Is this an **official** source? (Nous Research, GitHub, etc.)
  - [ ] Is this a **medium-quality blog**? (potential to beat)
  - [ ] Is this a **high-authority general site**? (hard to beat)
  - [ ] How fresh is the content? (Last updated?)

- [ ] Create file: `seo/manual-serp-analysis.md`
  - [ ] Format: Table with Keyword | Rank1 | Rank2 | Rank3 | Difficulty_Assessment
  - [ ] Add column: "Opportunity?" (Yes/Maybe/No)

- [ ] Identify **weak competitors**: Articles ranking that are only tangentially related
  - [ ] These are your quick-win targets

### Step 5: Create Opportunity Scoring Matrix (1 hour)

- [ ] Build comprehensive scoring file: `seo/keyword-opportunity-matrix.csv`

**Columns:**
```
Keyword,
Volume,
Ubersuggest_Difficulty,
CPC_Est,
Opportunity_Score,
Tier,
Recommendation,
Content_Type,
SERP_Difficulty_Assessment,
Quick_Win_Target
```

- [ ] **Scoring formula:**
  ```
  Opportunity Score = (Volume / 100) + (100 - Difficulty) - (Difficulty * 0.2)
  ```
  
- [ ] Example scoring:
  - hermes agent docker: Volume=1200, Diff=45 → Score = 12 + 55 - 9 = **58**
  - hermes ai setup: Volume=850, Diff=38 → Score = 8.5 + 62 - 7.6 = **62.9**
  - fox in the box ai: Volume=120, Diff=15 → Score = 1.2 + 85 - 3 = **83.2** (small volume but EASY)

- [ ] Sort by Opportunity_Score DESC

- [ ] Mark "Quick_Win_Target" = True for:
  - Difficulty < 30 AND Volume > 100
  - OR Difficulty < 50 AND Volume > 500

### Step 6: Create Tier Assignments (30 min)

- [ ] Top 10 keywords by Opportunity_Score → **TIER 1** (launch priority)
  - These are your first 3 months of content
  - Example: "hermes agent docker", "hermes agent setup", "fox in the box ai"

- [ ] Next 20 keywords → **TIER 2** (supporting content)
  - Blog posts, tutorials, follow-ups
  
- [ ] Remaining → **TIER 3** (long-tail, evergreen blog series)

- [ ] Update master spreadsheet with Tier assignments

### Step 7: Validation & Quality Check (1 hour)

- [ ] Sanity check on scoring:
  - [ ] Does the ranking make intuitive sense?
  - [ ] Are "hermes agent docker" type keywords scoring higher than generic "docker"? (Should be)
  - [ ] Are low-volume keywords with low difficulty scoring high? (They should — quick wins)

- [ ] Cross-check volumes:
  - [ ] If Ubersuggest and Planner differ by 3x, note it (data variance is normal)
  - [ ] If either shows 0 volume for a keyword, you might have misspelled it

- [ ] Verify no duplicates in final list

- [ ] Export clean CSV: `seo/keyword-targets-final.csv` (top 40 keywords only)

---

## Deliverables

✅ **Output files:**
- `google-keyword-planner-results.csv` — raw export from Planner
- `answer-the-public-findings.md` — organized question keywords by category
- `manual-serp-analysis.md` — your hand-written SERP analysis for top 15 keywords
- `keyword-opportunity-matrix.csv` — full scoring + Tier assignments
- `keyword-targets-final.csv` — top 40 keywords sorted by opportunity score
- `seo/serp-snapshots/` folder — visual reference of top SERPs

✅ **Key metrics to record in PHASE-2-SUMMARY.md:**
- Total keywords analyzed: ___
- TIER 1 count: ___
- TIER 2 count: ___
- TIER 3 count: ___
- Average difficulty of TIER 1: ___
- Average volume of TIER 1: ___
- Highest opportunity score: ___
- Lowest difficulty score: ___
- Quick-win targets identified: ___ (count)

---

## Tools Reference

| Tool | Free Tier | Limitation | Use For |
|------|-----------|-----------|---------|
| Google Keyword Planner | ✅ Yes | None for research | Volume baseline |
| Ubersuggest | ✅ 3 searches/day | Rate-limited | Difficulty + SERP overview |
| Answer The Public | ✅ Yes | Limited exports | Question mining |
| Ahrefs free extension | ✅ Chrome extension | Domain Authority only | Competitive backlinks (Phase 4) |
| SEMrush | ❌ Paid | $99+/month | Optional: full suite |

---

## Common Pitfalls

⚠️ **Don't:**
- Assume Ubersuggest difficulty = final ranking difficulty (it's correlated, not causal)
- Trust volume if it shows 0 — doesn't mean no searches, might mean niche keyword
- Score keywords without SERP analysis — a 30-difficulty keyword might be easy if competitors are weak
- Skip manual SERP review — this is where you find quick wins

✅ **Do:**
- Validate volumes across multiple tools (Planner + Ubersuggest should roughly align)
- Look at actual SERPs — see WHO ranks, not just difficulty scores
- Identify "weak competitors" — they're your initial targets
- Note fresh vs. stale content in top results (stale = opportunity to update/beat)

---

## Next Steps → Phase 3

Once complete, move to **PHASE-3-SEARCH-INTENT.md**
