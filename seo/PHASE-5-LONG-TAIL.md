# Phase 5: Long-Tail & Question Keywords

**Goal:** Find low-competition, high-intent keywords that get 10-100 searches/month.

**Timeline:** Week 3, Days 1-2 | ~3-4 hours

**Dependencies:** PHASE-4-COMPETITIVE-LANDSCAPE.md ✅ Complete

---

## To-Do List

### Step 1: Mine Question Variations (1.5 hours)

- [ ] Create file: `seo/question-keywords.md`

**Use Answer The Public (from Phase 2) results**

- [ ] Extract all question keywords you found earlier:
  - "How do I install hermes agent?"
  - "Can I run hermes agent locally?"
  - "Is hermes agent free?"
  - "How does hermes agent compare to cursor?"
  - "What is hermes agent used for?"
  - "Do I need Docker for hermes?"
  - etc.

- [ ] Organize by category:
  ```markdown
  ## Installation & Setup
  - [ ] How do I install hermes agent?
  - [ ] Can I use hermes agent without Docker?
  - [ ] What are the system requirements?
  - [ ] How long does hermes setup take?
  
  ## Comparison & Alternatives
  - [ ] Hermes vs Cursor: What's the difference?
  - [ ] Is hermes agent better than Claude Code?
  - [ ] Can I use hermes with Ollama?
  
  ## Pricing & Licensing
  - [ ] Is hermes agent free?
  - [ ] Do I need a subscription for hermes?
  - [ ] What's the cost of running hermes locally?
  
  ## Troubleshooting & Support
  - [ ] Why won't hermes agent start?
  - [ ] How do I debug hermes errors?
  - [ ] What if hermes can't find my models?
  ```

- [ ] Estimate search volume for each:
  - Use Google search box autocomplete (type "how to use hermes agent" and see suggestions)
  - Check each in Ubersuggest free tier if possible

### Step 2: Google Autocomplete Mining (1 hour)

- [ ] For each of these seed keywords, Google them and document autocomplete suggestions:
  - "hermes agent"
  - "ollama"
  - "fox in the box"
  - "local llm"
  - "self hosted ai"
  - "docker container"

- [ ] Screenshot or note all autocomplete suggestions
  - These are real searches people are making

- [ ] Create file: `seo/google-autocomplete-findings.md`
  - Organize by keyword
  - Note: Which questions appear repeatedly?
  - Which are niche vs. popular?

### Step 3: Reddit Mining (30 min)

- [ ] Search Reddit for discussions about:
  - r/LocalLLaMA
  - r/selfhosted
  - r/docker
  - r/MachineLearning
  - r/programming

- [ ] Search queries:
  - "hermes agent"
  - "llm setup"
  - "ollama docker"
  - "self hosted ai"

- [ ] Document:
  - [ ] Common questions people ask
  - [ ] Pain points mentioned
  - [ ] Solutions discussed
  - [ ] These become blog post topics!

- [ ] Create file: `seo/reddit-mining-findings.md`

### Step 4: Build Question Keyword Master List (1 hour)

- [ ] Create file: `seo/long-tail-question-keywords.csv`

**Columns:**
```
Question_Keyword,
Estimated_Volume,
Intent_Type,
Related_Tier1_Keyword,
Blog_Series,
Content_Title,
Est_Length,
Status
```

**Example rows:**
```
How do I install hermes agent, 50, Transactional, hermes agent setup, Setup Guide, Installation: 5 Steps to Get Hermes Running, 1200, Backlog
Is hermes agent free, 35, Informational, hermes agent, Pricing & Cost, Is Hermes Agent Free? Complete Pricing Guide, 1000, Backlog
Can I run hermes without Docker, 25, Transactional, hermes agent docker, Setup Guide, Running Hermes Without Docker: Alternatives Explained, 1500, Backlog
Hermes vs Claude Code, 60, Commercial, hermes vs claude, Comparisons, Hermes Agent vs Claude Code: Side-by-Side Comparison, 1800, Backlog
```

- [ ] Target: 20-40 question keywords minimum
- [ ] Validate volume isn't too low (target >10 searches/month)

### Step 5: Group Into Blog Series (1 hour)

- [ ] Group related question keywords into blog series

**Example Series 1: "Getting Started with Hermes Agent"**
- How do I install hermes agent? (1200 words)
- Do I need Docker for hermes? (1000 words)
- What are the system requirements? (800 words)
- How do I troubleshoot errors? (1000 words)
- 4 blog posts, 3-4 weeks content, internal link to each other

**Example Series 2: "Hermes vs Other Tools"**
- Hermes vs Cursor: detailed comparison (1800 words)
- Hermes vs Claude Code: feature matrix (1500 words)
- Hermes vs ChatGPT: what's different? (1200 words)

**Example Series 3: "Cost & Value"**
- Is hermes free? (1000 words)
- Cost of running local AI (1200 words)
- When to choose Hermes vs cloud AI (1000 words)

- [ ] Create file: `seo/blog-series-structure.md`

**Format:**
```markdown
## Series: "Getting Started with Hermes Agent"
**Target Audience:** Non-technical founders, DevOps engineers
**Series Goals:** Establish as authority for hermes setup, build topic cluster for SEO
**Internal Linking:** Every post links to the others

### Post 1: "How to Install Hermes Agent" (1200 words)
- Question keyword: "How do I install hermes agent?"
- Content outline: Prerequisites → Step-by-step → Validation → Next steps
- CTA: "Try Fox in the Box for one-click setup"
- Links to: Post 2, Post 4

### Post 2: "Do You Need Docker?" (1000 words)
- Question keyword: "Can I run hermes without Docker?"
- Content outline: What is Docker? → Why Docker? → Alternatives → Docker vs. native
- CTA: "Learn about Docker with our setup guide"
- Links to: Post 1, Post 3

...etc
```

### Step 6: Content Calendar Integration (1 hour)

- [ ] Update master content calendar: `seo/content-calendar-final.md`

**Integrate long-tail blog series:**

```markdown
## Month 1: Foundation (Tier 1 Priority)
- Landing page: "/hermes-agent" (What is Hermes)
- Guide: "/setup-hermes-docker" (Installation)
- 2 blog posts: Quick wins from Phase 4

## Month 2: Build Depth (Tier 1 + 2)
- Comparison pages: "/hermes-vs-cursor", "/hermes-vs-claude"
- Blog series: "Getting Started with Hermes" (4 posts)

## Month 3: Long-Tail Dominance (Tier 2 + 3)
- Blog series: "Hermes Cost & Value" (3 posts)
- Individual long-tail posts: FAQ answers (10 posts)
- Update & relink Month 1 content

**Total Content:** 
- Month 1: 3 pieces
- Month 2: 6 pieces
- Month 3: 15 pieces
- Total: 24 pieces in 3 months
```

### Step 7: Validate & Prioritize (30 min)

- [ ] Create file: `seo/long-tail-prioritization.csv`

**Score each question keyword for priority:**

```
Question_Keyword,
Volume,
Difficulty_Est,
Effort_Hours,
Priority_Score,
Series,
Month
```

**Scoring logic:**
- Effort-to-volume ratio (high volume, low effort = high priority)
- Series cohesion (groups of 4-5 related questions > individual posts)
- Link-building potential (can you build a strong internal link structure?)

- [ ] Mark top 30 as **"Ready to Write"**

---

## Deliverables

✅ **Output files:**
- `question-keywords.md` — organized by category
- `google-autocomplete-findings.md` — autocomplete suggestions + patterns
- `reddit-mining-findings.md` — Reddit pain points + discussions
- `long-tail-question-keywords.csv` — all question keywords with scoring
- `blog-series-structure.md` — grouped blog series with outline + CTA
- `content-calendar-final.md` — complete 3-month + year-1 plan
- `long-tail-prioritization.csv` — top 30 sorted by priority

✅ **Key metrics to record in PHASE-5-SUMMARY.md:**
- Question keywords identified: ___
- Blog series created: ___ (count)
- Total blog posts planned: ___
- Estimated total word count: ___ (24 posts × avg length)
- Priority 1 posts (ready to write): ___ (count)
- Estimated coverage of Tier 3 keywords: ___%

---

## Content Calendar Summary

| Phase | Pieces | Type | Focus |
|-------|--------|------|-------|
| Month 1 | 3 | Landing pages + guides | Tier 1 transactional |
| Month 2 | 6 | Blog series + comparisons | Tier 1 + 2 |
| Month 3 | 15 | Long-tail blog series | Tier 2 + 3 |
| **Total** | **24** | Mixed | **All tiers** |

---

## Common Pitfalls

⚠️ **Don't:**
- Ignore question keywords because volume is "low" (10-50 searches/month is GOLDEN for SEO)
- Write blog posts without grouping into series (waste of effort, poor internal linking)
- Forget that question keywords have high INTENT (low volume ≠ low quality)
- Assume every question needs a full 2000-word post (many questions = 800-1200 words max)

✅ **Do:**
- Mine REAL questions from Answer The Public, Google autocomplete, Reddit
- Group questions into 3-5 post series (internal linking multiplier)
- Write one series fully (Month 2) before moving to next
- Use question keywords in your post titles and headers (natural keyword usage)

---

## Next Steps → Phase 6

Once complete, move to **PHASE-6-ORGANIZATION-TRACKING.md**
