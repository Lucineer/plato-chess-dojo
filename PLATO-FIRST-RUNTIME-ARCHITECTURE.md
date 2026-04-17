# The Plato-First Runtime: Unified Architecture

*A synthesis of 10 creative model discussions across 3 idea batches*

---

## The Convergence

Three batches of ideas from Casey, discussed across 10 model sessions (DeepSeek-Reasoner x2, DeepSeek-chat x5, Hermes-3-405B x2, Seed-OSS-36B), all converge on one thesis:

**The document is the program. The words are the logic. The reading is the execution.**

PLATO — both the 1960s system and our modern one — was always about this. The original PLATO had TUTOR language, plasma tiles, episode recorders, teaching loops. Our PLATO has question-answer tiles, two-gear NPCs, room navigation, audit trails. The Plato-First Runtime unifies both.

## The Five Pillars

### Pillar 1: Tiling Knowledge Substrate

**From:** Monolithic context dumping
**To:** Overlapping semantic chunks injected on demand

The runtime breaks every Markdown document into tiles by `##` headers. Tiles have overlap (last 2 lines of tile N = first 2 lines of tile N+1) to prevent boundary context loss. The runtime tracks the user's "position" in the document and only injects the relevant tile + neighbors.

**Key insight from research:** Optimal tile size is task-dependent. Diagnostics need 200-300 word tiles (focused problem-solving). Creative tasks need 500-800 word tiles (broader context). The runtime adapts tile size based on room type.

**Compression ratio:** A 10,000-word document tiled at 300 words with 50-word overlap = ~36 tiles. Average query loads 3 tiles (current + 1 neighbor each direction) = 900 words. That's a **91% compression** from full context dump.

### Pillar 2: Assertive Markdown (The Cave of Evals)

**From:** Instructional documentation (passive)
**To:** Assertion-based guardrails (active)

Bullet points become executable constraints:

```markdown
## Room: medical
### Assertions
- [ ] Patient age must be confirmed before diagnosis
- [ ] Never recommend medication without dosage
- [ ] If confidence < 0.6, offer "consult a specialist" option
- [ ] Tile score < 0.5 triggers fallback to LLM synthesis
- [ ] Maximum 3 iterations before human escalation
```

A secondary auditor agent checks every response against assertions. Violations trigger a retry loop (max 3 retries, then escalate). The audit trail records every violation and correction.

**Key insight:** Assertions compose hierarchically. Global assertions (safety) → room assertions (domain) → tile assertions (specific). An assertion at any level can veto a response.

### Pillar 3: Semantic Muscle Memory (Episode Recorder)

**From:** Every query is independent
**To:** Past experience shapes future responses

As the agent acts, the runtime records successes and failures as "episodes" — compact knowledge tiles that capture what worked. When a similar query arrives, the runtime preloads the most relevant episode into context.

**Key insight from cognitive science:** Human expertise is chunked pattern recognition. The agent equivalent is compiled experience tiles — not raw logs, but compressed "lessons learned" that capture the pattern, not the details.

**Decay mechanism:** Episodes have a half-life. Unused episodes decay (score decreases by 10%/week). High-use episodes strengthen. This prevents stale knowledge from calcifying while preserving actively-used wisdom.

### Pillar 4: Word Anchors + Homoiconic Markdown

**From:** Static documents
**To:** Self-referencing, self-modifying knowledge graphs

`[PaymentFlow]` in any tile creates a hyperlink to the PaymentFlow tile. The agent can jump its entire context there. Anchors are bidirectional — the PaymentFlow tile knows every tile that references it.

**Homoiconic:** The agent can rewrite its own tiles. After 10 successful resolutions of "python memory leak," the agent compresses 10 verbose episode tiles into 1 concise pattern tile. The knowledge graph literally restructures itself.

**Cycle detection:** Anchor resolution has a max depth of 5. Cycles are detected and broken with a "circular reference" warning. Cross-room anchors create emergent navigation pathways.

### Pillar 5: The Plato-First Runtime (Unified)

All five pillars run in a single runtime:

```
User Query
    │
    ▼
┌─────────────────┐
│  Tiling Engine   │ ← Load relevant tiles (Pillar 1)
│  (position track)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Muscle Memory   │ ← Preload relevant episodes (Pillar 3)
│  (episode match) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Gear 1: Tiles   │ ← Pattern match against loaded tiles
│  Gear 2: LLM     │ ← Synthesize if no match
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Assertion Check │ ← Validate against room assertions (Pillar 2)
│  (auditor agent) │
└────────┬────────┘
         │
    Pass │ Fail
         │    │
         │    ▼
         │  ┌──────────┐
         │  │ Retry    │ ← Max 3, then escalate
         │  │ Loop     │
         │  └──────────┘
         ▼
┌─────────────────┐
│  Anchor Resolve  │ ← Expand [WordAnchors] (Pillar 4)
│  (graph walk)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Response       │
│  + Audit Trail  │ ← Log everything (Markdown)
│  + Episode Save │ ← Record for future muscle memory
└─────────────────┘
```

## Original PLATO → Modern PLATO Mapping

| Original PLATO (1960s) | Modern PLATO (2026) | Plato-First Runtime |
|---|---|---|
| TUTOR `jump` command | Room navigation | Word Anchors `[Target]` |
| Plasma screen tiles | Question-answer tiles | Tiling Knowledge Substrate |
| Teaching loops | Clunk detection | Assertive Markdown assertions |
| Dialogue Episode Recorder | Audit trail | Semantic Muscle Memory |
| Notes file | MEMORY.md | Homoiconic Markdown |
| Conditional branching | Gear 1/2 NPC | Mermaid state machines |

## What This Enables

1. **A doctor's room** where assertions prevent dangerous advice, muscle memory recalls similar cases, and word anchors connect to drug interaction databases
2. **A teacher's room** where teaching loops ensure students pass checkpoints, tiles adapt to learning speed, and episode recordings identify common misconceptions
3. **An engineer's room** where assertions enforce coding standards, muscle memory recalls similar bugs, and homoiconic markdown lets the room optimize its own troubleshooting guides

## Implementation Priority

**Phase 1 (this week):** Tiling substrate + assertions
**Phase 2 (next week):** Muscle memory (episode recorder)
**Phase 3 (next month):** Word anchors + homoiconic markdown
**Phase 4:** Full Plato-First Runtime unification

---

*53K chars of research. 5 models. 3 idea batches. 1 unified architecture.*
*The document is the program. The words are the logic. The reading is the execution.*
