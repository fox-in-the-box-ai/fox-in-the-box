# Phase 3: Search Intent Mapping

**Goal:** Understand *why* people search, what content satisfies them, and map to content types.

**Timeline:** Week 2, Days 1-2 | ~4-5 hours

**Dependencies:** PHASE-2-VOLUME-DIFFICULTY.md ✅ Complete (keyword-targets-final.csv)

---

## To-Do List

### Step 1: Intent Classification (1.5 hours)

- [ ] Create intent classification file: `seo/keyword-intent-mapping.md`

**For each of your TIER 1 + TIER 2 keywords (top 30), classify as:**

- [ ] **Navigational** — Person wants a specific resource/website
  - Examples: "hermes agent github", "fox in the box official", "hermes docker hub"
  - Action: Link directly to resource + brief context

- [ ] **Informational** — Person wants to learn about a topic
  - Examples: "what is hermes agent", "hermes agent tutorial", "how hermes ai works"
  - Action: Long-form blog/guide explaining the concept

- [ ] **Transactional** — Person wants to DO something (install, set up, use)
  - Examples: "install hermes agent", "hermes docker setup", "run ollama locally"
  - Action: Step-by-step guide with code/commands

- [ ] **Commercial Intent** — Person researching options, comparing solutions
  - Examples: "hermes vs cursor", "hermes agent vs claude code", "best local ai tools"
  - Action: Comparison table + positioning toward Fox in the Box

- [ ] Create master table: `keyword-intent-mapping.csv`
  ```
  Keyword, Intent_Type, Primary_Audience, User_Stage, Confidence
  hermes agent docker, Transactional, Developer, Problem_Solving, High
  what is hermes agent, Informational, Non-Dev, Awareness, Medium
  hermes vs cursor, Commercial, Developer, Consideration, High
  ```

### Step 2: Content Type Mapping (1.5 hours)

- [ ] For each keyword, assign **content type**:

| Intent | Best Content Type | Est. Length | CTA | Example |
|--------|-------------------|-------------|-----|---------|
| Navigational | Resource Page / Link Hub | 500-800 | Link to GitHub | "Get Hermes Agent" |
| Informational | Blog / Tutorial | 1500-2500 | Free resource | "Learn More" or "Try Free" |
| Transactional | Step-by-Step Guide | 1200-2000 | Call-to-action (Fox in the Box) | "Download Now" |
| Commercial | Comparison / Versus | 1500-2500 | Product comparison + CTA | "Choose Your Tool" |

- [ ] Populate table: `content-type-mapping.csv`
  ```
  Keyword, Intent, Content_Type, Length_Target, Primary_CTA, Secondary_CTA
  hermes agent docker, Transactional, Step-by-Step Guide, 1500, Download Fox in the Box, GitHub setup
  what is hermes agent, Informational, Blog Post, 2000, Try Free, Subscribe to updates
  hermes vs cursor, Commercial, Comparison, 2000, Choose Fox in the Box, See feature matrix
  ```

### Step 3: Content Gap Analysis (1.5 hours)

**For your top 15 keywords, perform gap analysis:**

- [ ] For EACH keyword:
  - [ ] Google it
  - [ ] Read top 3 results fully (not skim)
  - [ ] Document:
    - [ ] What does it cover?
    - [ ] What's missing?
    - [ ] What angle could YOU own?
    - [ ] Is the content dated or evergreen?

- [ ] Create file: `seo/content-gap-analysis.md`
  
**Format:**
```
## Keyword: "hermes agent docker"

**Top 3 Results:**
1. Nous Research official docs
   - Covers: Advanced config, multiple deployment options
   - Missing: One-click setup, non-technical audience
   - Angle opportunity: "Hermes Agent Docker Without the Headache"

2. Medium article (2024)
   - Covers: Manual Docker setup with docker-compose
   - Missing: Pre-built image, GUI, troubleshooting
   - Angle opportunity: "Pre-built Docker Image (No Compose Needed)"

3. GitHub gist
   - Covers: Docker commands only
   - Missing: Why you'd want Docker, prerequisites, validation
   - Angle opportunity: "Complete Docker Setup Guide (Beginner-Friendly)"

**Our Opportunity:** 
- All competitors assume technical Docker knowledge
- No one targets the "non-dev who wants AI locally" audience
- Our angle: "Install in 2 minutes with Fox in the Box"
- Content gap: "One-click, visual setup with Docker behind the scenes"
```

- [ ] Document findings for all 15 TIER 1 keywords
- [ ] Look for patterns: What's consistently missing?
  - [ ] Beginner-friendly explanations?
  - [ ] Comparison to alternatives?
  - [ ] Visual guides / screenshots?
  - [ ] Local/offline-first angle?
  - [ ] Non-technical audience angle?

### Step 4: Audience Persona Mapping (1 hour)

- [ ] Define audience personas for each keyword:

**Create file: `seo/audience-personas.md`**

- [ ] **Persona 1: The Non-Technical Founder**
  - Keywords: "fox in the box ai", "hermes ai simple", "one-click ai setup"
  - Pain: "I want AI locally but I don't know Docker"
  - Content angle: Visual, no jargon, emphasize "it just works"
  - CTA: "Get started free"

- [ ] **Persona 2: The DevOps Engineer**
  - Keywords: "hermes agent docker", "self-hosted ai architecture", "containerized llm"
  - Pain: "I need to deploy this in production safely"
  - Content angle: Advanced config, orchestration, scaling
  - CTA: "See deployment guide"

- [ ] **Persona 3: The AI Researcher**
  - Keywords: "hermes agent", "hermes ai vs claude", "local llm benchmarks"
  - Pain: "Which AI tool is best for my use case?"
  - Content angle: Technical comparison, benchmarks, feature matrix
  - CTA: "Compare tools"

- [ ] **Persona 4: The Cursor/Claude Code User**
  - Keywords: "hermes vs cursor", "hermes vs claude code", "hermes agent supervision"
  - Pain: "Should I switch tools? What's different?"
  - Content angle: Head-to-head comparison, why you'd choose Fox in the Box
  - CTA: "Try Fox in the Box free"

- [ ] For each persona, list:
  - [ ] 3-5 keywords they'd search
  - [ ] What they care about (speed? cost? features? UX?)
  - [ ] Content format preference (guides? comparisons? videos?)
  - [ ] Objection: What would convince them?

### Step 5: Content Calendar Draft (1 hour)

- [ ] Create file: `seo/content-calendar-draft.md`

- [ ] Map keywords to **3-month content plan**:

**Month 1: Foundation & Transactional** (Landing pages + core guides)
- [ ] `/hermes-agent` landing page ("What is Hermes Agent?") — Tier 1 keywords
- [ ] `/setup-hermes-docker` guide ("Install Hermes in Docker") — Tier 1 keywords
- [ ] `/fox-in-the-box-hermes` positioning page — Brand keywords
- [ ] 3-4 blog posts: Transactional keywords from Tier 1

**Month 2: Comparisons & Depth** (Competitive positioning)
- [ ] `/hermes-vs-cursor` comparison page
- [ ] `/hermes-vs-claude-code` comparison page
- [ ] 5 blog posts: Informational + long-tail keywords

**Month 3: Long-tail & SEO Flywheel** (Question keywords + evergreen)
- [ ] Blog series: Answer The Public questions ("How do I...?" keywords)
- [ ] 8-10 short guides (800-1200 words each)
- [ ] Refresh old content with internal links

### Step 6: Validation & Final Mapping Table (30 min)

- [ ] Create comprehensive master table: `seo/keyword-to-content-mapping.csv`

**Columns:**
```
Rank,
Keyword,
Volume,
Difficulty,
Intent_Type,
Content_Type,
Target_URL,
Est_Length,
Primary_CTA,
Blog_Post_Title,
Month_1_2_or_3,
Persona,
Content_Status,
Blog_Post_Draft_Link
```

**Example rows:**
```
1, hermes agent docker, 1200, 45, Transactional, Step-by-Step, /setup-hermes-docker, 1500, Download Fox in the Box, How to Install Hermes Agent in Docker, Month 1, DevOps, Backlog,
2, what is hermes agent, 850, 38, Informational, Blog, /hermes-agent, 2000, Try Free, What is Hermes Agent? A Beginner's Guide, Month 1, Non-Tech Founder, Backlog,
3, hermes vs cursor, 650, 52, Commercial, Comparison, /hermes-vs-cursor, 2000, Choose Fox in the Box, Hermes Agent vs Cursor: Feature Comparison, Month 2, DevOps, Backlog,
```

- [ ] Sort by Month (1, 2, 3) then by Content_Status
- [ ] Verify:
  - [ ] No duplicate URLs
  - [ ] Each Tier 1 keyword has a content assignment
  - [ ] CTA aligns with intent (Transactional = Fox in the Box download, not general "learn more")
  - [ ] Each persona appears in 3-5 keywords at minimum

### Step 7: Summarize Intent Distribution (30 min)

- [ ] Create file: `seo/PHASE-3-SUMMARY.md`

- [ ] Document:
  ```
  ## Phase 3 Summary: Search Intent Mapping
  
  **Keywords Analyzed:** 40 (TIER 1 + 2)
  
  **Intent Distribution:**
  - Navigational: 3 (7%)
  - Informational: 12 (30%)
  - Transactional: 15 (38%)
  - Commercial: 10 (25%)
  
  **Content Type Breakdown:**
  - Landing Pages: 3
  - Step-by-Step Guides: 8
  - Blog Posts (Long): 15
  - Comparison Pages: 2
  - Resource Hub: 1
  
  **Content Calendar:**
  - Month 1 (Foundation): 7 pieces
  - Month 2 (Comparison): 10 pieces
  - Month 3 (Long-tail): 15 pieces
  
  **Primary Audience:**
  - DevOps Engineers: 45% of keywords
  - Non-Technical Founders: 25% of keywords
  - AI Researchers: 20% of keywords
  - Tool Switchers: 10% of keywords
  
  **Key Insights:**
  - Most search volume is Transactional (people want to SET IT UP)
  - Gap opportunity: All competitors skip the non-technical audience
  - Comparison pages could capture 25% of keywords with minimal effort
  - Answer The Public showed 50+ "how to..." questions — blog series goldmine
  ```

---

## Deliverables

✅ **Output files:**
- `keyword-intent-mapping.csv` — all keywords with intent classification
- `content-type-mapping.csv` — keywords mapped to content types + length targets
- `content-gap-analysis.md` — detailed gap analysis for top 15 keywords
- `audience-personas.md` — 4 personas with keywords + pain points
- `content-calendar-draft.md` — 3-month editorial calendar
- `keyword-to-content-mapping.csv` — master table (keyword → content URL → CTA)
- `PHASE-3-SUMMARY.md` — metrics + key insights

✅ **Key metrics to record:**
- Total keywords mapped: ___
- Transactional keywords (highest intent): ___
- Primary audience: ___ (most common persona)
- Content pieces needed (3 months): ___ (total)
- Blog vs. Landing pages ratio: ___
- Content gaps identified: ___

---

## Common Pitfalls

⚠️ **Don't:**
- Assume "highest volume" = best content target (transactional is better)
- Create the same content for all keywords (match content type to intent)
- Forget the gap analysis (this is your competitive advantage!)
- Write content for Personas you don't understand (talk to customers first!)

✅ **Do:**
- Match intent to content type rigorously (Transactional → Guides, not blogs)
- Look for "quick-win" gaps (weak competitors + high volume + clear angle)
- Use personas to write copy (not generic content)
- Build a content calendar BEFORE you start writing (focus, not chaos)

---

## Next Steps → Phase 4

Once complete, move to **PHASE-4-COMPETITIVE-LANDSCAPE.md**
