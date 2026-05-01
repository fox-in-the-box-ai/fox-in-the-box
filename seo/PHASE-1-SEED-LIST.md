# Phase 1: Seed List & Scope Definition

**Goal:** Build a comprehensive seed of search terms to research.

**Timeline:** Week 1, Days 1-2 | ~4-6 hours

---

## To-Do List

### Step 1: Build Intent Clusters (2 hours)
- [ ] Create base spreadsheet: `keyword-research-master.csv` with columns:
  - Keyword
  - Search Intent (Navigational/Informational/Transactional/Commercial)
  - Volume Estimate
  - Source
  - Notes
  
- [ ] Generate first cluster: `hermes agent` variations
  - [ ] hermes agent install
  - [ ] hermes agent docker
  - [ ] hermes agent setup
  - [ ] hermes agent tutorial
  - [ ] hermes agent self-host

- [ ] Generate second cluster: `hermes ai` variations
  - [ ] hermes ai docker
  - [ ] hermes ai local
  - [ ] hermes ai self hosted
  - [ ] what is hermes ai
  - [ ] hermes ai tutorial

- [ ] Generate third cluster: `fox in the box` variations
  - [ ] fox in the box ai
  - [ ] fox in the box hermes
  - [ ] fox in the box docker
  - [ ] fox in the box app
  - [ ] fox in the box install

### Step 2: Reverse-Engineer Competitor Seeds (2 hours)

- [ ] Google search: "hermes agent"
  - [ ] Analyze SERP titles & descriptions for top 10 results
  - [ ] Extract implied keywords
  - [ ] Note: Who ranks? (Nous Research, GitHub, blog posts?)
  - [ ] Add to seed list with source: "SERP-hermes-agent"

- [ ] Google search: "claude code"
  - [ ] Capture competitive keywords
  - [ ] Look for: setup, docker, tutorial, comparison
  - [ ] Add with source: "SERP-claude-code"

- [ ] Google search: "cursor ai"
  - [ ] Same analysis as above
  - [ ] Add with source: "SERP-cursor-ai"

- [ ] Google search: "llm docker container"
  - [ ] Extract local AI + docker angle
  - [ ] Add with source: "SERP-llm-docker"

- [ ] Google search: "self hosted ai"
  - [ ] Your positioning keywords
  - [ ] Add with source: "SERP-self-hosted-ai"

### Step 3: Trend-Chase Related Keywords (1 hour)

- [ ] Search trending local AI keywords:
  - [ ] ollama docker
  - [ ] ollama setup
  - [ ] self hosted ai tools
  - [ ] local ai desktop
  - [ ] electron app docker
  - [ ] hermes vs claude code
  - [ ] hermes vs cursor
  - [ ] ai agent framework
  - [ ] local llm desktop

- [ ] Check GitHub trending for related keywords:
  - [ ] Search: "hermes agent"
  - [ ] Search: "local llm docker"
  - [ ] Note: high-volume repos in these spaces

- [ ] Add all to master spreadsheet

### Step 4: Document & Validate (1 hour)

- [ ] Count total keywords: Should have 80-120
- [ ] Validate no duplicates
- [ ] Sort by rough intent categories
- [ ] Create summary:
  - Total keywords: ___
  - Navigational: ___ 
  - Informational: ___
  - Transactional: ___
  - Commercial: ___

- [ ] Create backup: `keyword-research-master.csv.backup`

---

## Deliverables

✅ **Output files:**
- `keyword-research-master.csv` — all 80-120 seed keywords with intent + source
- `PHASE-1-SUMMARY.md` — summary stats, what we learned about competitors
- `PHASE-1-NOTES.md` — manual observations from SERP analysis (not ranking for what? Who's ranking? Why?)

✅ **Metrics to track:**
- Total seed keywords
- Distribution by intent type
- Top 10 competitor domains that appear in SERPs

---

## Notes & Assumptions

- "Search Volume Estimate" can be left blank for Phase 1 — we'll populate in Phase 2
- Focus on precision here: these are seeds for deeper research, not final target list
- If you find 150+ keywords, that's fine — we'll filter ruthlessly in Phase 2
- Manual SERP analysis is time-consuming but invaluable: you learn WHO your competitors are and WHY they rank

---

## Next Steps → Phase 2

Once complete, move to **PHASE-2-VOLUME-DIFFICULTY.md**
