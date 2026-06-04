# Step 7: Output — Narrative Guidelines

## Overview

The narrative is the qualitative synthesis of the output. It's not a summary of the numbers — the numbers are already in the output. The narrative is the INTERPRETATION: what do the numbers mean together, why does the current state matter, what is the most important thing happening right now, and what could change the picture.

A good narrative takes 30 seconds to read and leaves the trader with a clear mental model of the market. A bad narrative restates the numbers without adding meaning, hedges every statement, or buries the key insight in qualifications.

The narrative is 3-5 sentences. Every sentence carries information. No filler.

---

## The Five-Sentence Structure

Each narrative follows this structure. Not every sentence needs to be exactly one of these types, but the narrative should cover all five elements.

### Sentence 1: Regime context

State the current regime and its key structural fact. One sentence. Be specific about prices.

**Good:** "Positive gamma established, spot at 20,847 sitting 7 points above the gamma flip (20,840), with the put wall (20,850) acting as the immediate floor."

**Bad:** "The market is in a positive gamma environment with support below."

The bad version tells you nothing you couldn't infer from the regime letter. The good version gives you the specific prices that matter.

### Sentence 2: Flow state

Describe what the options flow is doing. Be specific about direction, magnitude, and recency.

**Good:** "Call-heavy flow with two sweeps in the last 15 minutes totaling $4.2M net call premium — buyers are paying up for upside exposure."

**Bad:** "Options flow is bullish."

The bad version is a label. The good version tells you the magnitude ($4.2M), the recency (last 15 minutes), the mechanism (sweeps), and the interpretation (buyers paying up).

### Sentence 3: Key observation

This is the most important sentence. Identify the SINGLE most important thing happening right now. Not the most important thing in general — the most important thing at this specific moment.

The key observation is often:
- A change since the last update (wall lifted, iceberg appeared, dark pool flipped)
- A confirmation of the setup (defense score upgraded, aggression imbalance spiked)
- A warning (VIX reversing, dark pool opposing flow, spoof detected)
- A structural development (gamma flip being tested, wall break imminent)

**Good:** "The put wall defense score upgraded from 71 to 87 since the last cycle — reload rate increased, iceberg bids have been active for 4 minutes, and buyer aggression at the wall is +52. The wall is being tested and held."

**Bad:** "The put wall is showing strong defense."

The good version tells you WHY the defense is strong (reload rate, iceberg, aggression), HOW LONG it's been happening (4 minutes), and the CONCLUSION (being tested and held). The bad version is a label.

### Sentence 4: Bias conclusion

State the directional bias and the path of least resistance. Be specific about targets.

**Good:** "Bullish bias at +68, path of least resistance toward HVL at 21,020 (+173 pts) and potentially the expected move high at 21,150 if the move extends."

**Bad:** "The bias is bullish and price could go higher."

The good version gives you the score (+68), the specific targets (21,020 and 21,150), and the distances (+173 pts). The bad version is useless.

### Sentence 5: Risk callout

Identify the ONE thing that could change the picture. Not a list of risks — the single most important risk to the current thesis.

**Good:** "Key risk: if spot closes below 20,840 for 2+ minutes, the gamma flip is breached and Regime E cascade begins — the put wall becomes a ceiling, not a floor."

**Bad:** "There are risks to the downside if the market reverses."

The good version tells you the specific trigger (20,840 for 2+ minutes), the mechanism (gamma flip breach), and the consequence (Regime E cascade, wall becomes ceiling). The bad version is noise.

---

## Narrative DO's

### Be specific with prices

Every level mentioned in the narrative should have a specific NQ price. "The call wall" is not specific. "The call wall at 21,200" is specific. The trader should be able to look at the level map and find every price mentioned in the narrative.

### Be causal

Explain WHY the bias is what it is. "Bullish BECAUSE flow is call-heavy AND dark pool is buying AND DOM is bid-heavy" is causal. "Bullish" is a label. The narrative should make the reasoning transparent.

### Be honest about uncertainty

If dark pool is neutral, say so. If conviction is 3/5 instead of 5/5, say why. If two dimensions are contradicting each other, acknowledge it and explain how you resolved it.

**Good:** "Dark pool is neutral — no clear directional signal from UW in the last 2 hours — reducing conviction from 4/5 to 3/5 and position size accordingly."

**Bad:** (ignoring the neutral dark pool and claiming 4/5 conviction)

### Identify the one thing that could change the picture

Every narrative should end with the single most important risk or catalyst. This forces clarity about what the thesis depends on. If you can't identify what would invalidate the thesis, the thesis isn't clear enough.

### Track changes from the last update

The narrative is cumulative. Reference what changed since the last output. This is especially important for event-triggered outputs.

**Good:** "Previously bearish bias at -42 due to put sweeps. Now shifting to neutral -12 as dark pool buying appears and put flow exhausts — the bearish thesis is weakening."

**Bad:** (treating every output as if it's the first one, ignoring the session history)

### Use the session history

The narrative should reference the session arc. "This is the third test of the put wall today — the first two held, and the defense score is higher now than on either previous test" is more informative than treating the current test in isolation.

---

## Narrative DON'Ts

### Don't be wishy-washy

"Market could go up or down depending on how things develop" is not a narrative. It's a refusal to take a position. The system has a bias score. The narrative should reflect that score with conviction.

If the bias score is +68, the narrative should be bullish. If the bias score is +12, the narrative should acknowledge the weak bullish lean and explain why it's weak. But it should not hedge to the point of saying nothing.

### Don't ignore contradictions

If flow says bullish but dark pool says bearish, the narrative must address this. Ignoring contradictions produces false confidence. Acknowledging them produces honest uncertainty.

**Good:** "Flow is bullish (call sweeps, net call premium) but dark pool is showing net selling ($8M in the last hour) — the contradiction reduces conviction to 3/5. The flow signal is more recent and more time-sensitive; the dark pool signal may reflect hedging rather than directional positioning."

**Bad:** (mentioning only the bullish flow and ignoring the bearish dark pool)

### Don't repeat numbers without interpretation

"GEX is +$3.2B" means nothing without "which means positive gamma — dealers are long gamma and will buy dips, dampening downside moves." The number is in the output. The narrative adds the meaning.

### Don't use filler

Every word in the narrative should carry information. Cut:
- "It's worth noting that..."
- "As we can see from the data..."
- "The market is currently..."
- "At this point in time..."
- "Given the above analysis..."

These phrases add length without adding meaning.

### Don't list everything

The narrative is not a summary of every field in the output. It's a synthesis of the most important elements. If you're mentioning all five component scores, you're summarizing, not synthesizing. Pick the two or three most important elements and explain their interaction.

---

## Session-Specific Narratives

### The morning setup narrative (9:40-9:45 AM ET)

The first narrative of the session is the most important. It sets the framework for the day. It should be slightly longer than subsequent narratives (5-7 sentences) and cover:

1. **Overnight positioning:** What happened overnight? Did NQ gap? What was the overnight range? What does the gap direction tell us?

2. **GEX regime for the day:** What regime are we starting in? Where is the gamma flip? Where are the walls? What's the expected move for the day?

3. **Key levels to watch:** The 2-3 most important levels for the session. Not a list of every level — the 2-3 that will determine the day's character.

4. **Expected scenarios:** What are the 2-3 most likely scenarios for the day? "If price holds above 20,840 (gamma flip), expect a grind toward HVL at 21,020. If price breaks below 20,840, expect Regime E cascade toward 20,720 (expected move low)."

5. **What to watch for:** The specific signals that would confirm or invalidate each scenario. "Watch for iceberg bids at the put wall (20,850) to confirm the floor. Watch for VIX reversal above 18 as the primary risk to the bullish scenario."

**Example morning setup narrative:**

"NQ opened flat (+12 pts from yesterday's close) with no significant gap, suggesting overnight positioning was balanced. Positive gamma regime established with spot at 20,847, gamma flip at 20,840, call wall at 21,200, and put wall at 20,850 — the day's range is likely to be contained between these walls unless a catalyst forces a break. The primary scenario is a grind toward HVL at 21,020 (the gravitational center) with the put wall providing a defended floor. The secondary scenario is a put wall break if selling pressure overwhelms the defense — watch for defense score dropping below 40 and depletion rate accelerating without reload. VIX opened at 16.8, providing a mild vanna tailwind for the bullish scenario. The key level to watch is 20,840 (gamma flip) — a sustained break below this level changes the entire day's character from dampened to amplified."

### The midday review narrative (12:00-12:30 PM ET)

The midday review reassesses the morning setup. It should answer three questions:

1. **What played out?** Did the morning scenario materialize? Did price reach the expected targets?

2. **What changed?** Did the regime shift? Did walls move? Did flow change character?

3. **What's the plan for the afternoon?** Given the current state, what are the afternoon scenarios?

**Example midday review narrative:**

"Morning scenario played out partially — price reached HVL at 21,020 (+173 pts from the put wall) but stalled there rather than extending to the expected move high. The put wall held on two tests (9:52 AM and 10:31 AM), confirming the Regime C floor. Flow has gone quiet since 11:15 AM — net premium dropped to $1.2M in the last 15 minutes, approaching the dead market threshold. The afternoon plan: if flow revives after 1:30 PM with call-heavy character, the path to 21,150 (expected move high) remains open. If flow stays dead, expect a pin near HVL (21,020) into the close. Watch for charm flows after 2:30 PM — with 0DTE calls at 21,000, charm will push price toward that strike in the final hour."

### The afternoon close narrative (2:30 PM ET)

The afternoon close narrative focuses on the final 90 minutes of the session. It should cover:

1. **Charm flow direction:** Which way are charm flows pushing price? (See step3-derived/vanna-charm.md)

2. **0DTE pin risk:** Is there a dominant 0DTE strike that price is being pulled toward?

3. **Session P&L context:** How has the session gone? Are we protecting profits or trying to recover?

4. **Close plan:** What's the plan for the final 90 minutes? Any positions to close before 3:45 PM?

**Example afternoon close narrative:**

"Charm flows are pushing price toward the 21,000 0DTE call strike — with 14,200 contracts of 0DTE call OI at 21,000, the pin force is significant. Current spot at 21,018 is 18 points above the pin target, and charm will continue pulling it lower into the close. Session P&L is +22 pts — in profit protection mode. No new positions after 3:30 PM. Existing long position (entered at 20,855) has stop at breakeven (20,855) and target at 21,020 — if charm pulls price to 21,000, the position will be stopped out at breakeven. The better play is to close the long at current price (21,018) and take the +163 pt gain rather than risk giving it back to charm."

---

## Narrative Evolution Through the Session

The narrative is not written in isolation. Each narrative builds on the previous ones. The session has a story arc, and the narrative should reflect that arc.

### Tracking the arc

Maintain a session summary that tracks:
- Opening regime and key levels
- Major events (regime changes, wall breaks, iceberg appearances)
- Trades taken and their outcomes
- How the bias score has evolved through the session

Each narrative should reference this arc. "This is the third test of the put wall today" is more informative than treating each test as if it's the first.

### Narrative consistency

If the bias was +68 in the last output and is now +45, the narrative should explain the change. "Bias declined from +68 to +45 as the call sweep flow exhausted — the two sweeps from 10:30 AM are now 30 minutes old and their signal weight has decayed. The structural and DOM signals remain bullish, but the flow component dropped from +61 to +28."

If the bias was +68 and is now +72, the narrative should note the improvement and why. "Bias strengthened from +68 to +72 as the dark pool signal shifted from neutral to bullish — a $15M dark pool buy print appeared at 10:52 AM, upgrading the dark component from +45 to +68."

### The "nothing changed" narrative

Sometimes the state is stable and nothing significant has changed since the last output. This is fine. The compact output format handles this case. But if a full output is produced, the narrative should still be informative:

"State unchanged from last cycle — Regime C stable, put wall defense score holding at 87, flow quiet but not dead ($2.1M net premium last 15 min), bias at +68. The setup remains valid. Waiting for either a new sweep to confirm the bullish thesis or a defense score drop below 60 to signal the wall is weakening."

This narrative tells the trader: nothing changed, the setup is still valid, here's what to watch for. It's short but informative.

---

## Contradiction Resolution

When two or more dimensions contradict each other, the narrative must resolve the contradiction explicitly. The resolution follows a priority hierarchy:

### Priority hierarchy for contradictions

1. **DOM (order book) > Flow (options):** The order book is real-time. Options flow has inherent lag (sweeps are reported with some delay). If the book says one thing and flow says another, the book is more current.

2. **Flow (options) > Dark pool:** Options flow is more time-sensitive than dark pool prints. Dark pool data from Unusual Whales has 15-30 minute inherent lag. A dark pool print from 20 minutes ago may already be fully priced in.

3. **Structural (GEX) > Derived (vanna/charm):** The GEX structure is the foundation. Derived signals (vanna, charm) are secondary effects. If they conflict, the structural signal wins.

4. **Recent > Old:** A signal from 5 minutes ago outweighs a signal from 45 minutes ago, all else equal.

### Contradiction narrative examples

**Flow bullish, dark pool bearish:**
"Options flow is bullish (two call sweeps, $4.2M net call premium) but dark pool is showing net selling ($8M in the last hour via Unusual Whales). The contradiction reduces conviction from 4/5 to 3/5. Resolving in favor of flow: the sweeps are from the last 15 minutes, while the dark pool prints are from 45-60 minutes ago and may reflect hedging of existing long positions rather than new directional selling. Monitoring for new dark pool prints — if selling continues, the bullish thesis weakens."

**DOM bearish, structural bullish:**
"The order book is showing ask-heavy depth (depth asymmetry 0.38, bearish lean) despite the positive gamma structural setup. This is a warning: the book is not confirming the GEX structure. Possible explanations: (1) the put wall defense is being tested and the book is reflecting the attack, not the defense; (2) the GEX data is slightly stale (last poll 2 min 40 sec ago) and the wall may have shifted. Reducing conviction from 4/5 to 3/5 until the book confirms the structural support."

**VIX rising, flow bullish:**
"VIX is rising (+0.6 pts in the last 20 minutes) while options flow remains call-heavy. This is a contradiction: rising VIX typically triggers vanna unwind (bearish for NQ) but the flow is still buying calls. Possible explanation: the call buying is hedging (buying calls as protection against a rally they're short) rather than directional. Treating the flow signal with lower weight until VIX stabilizes. Derived component downgraded from +58 to +15 (vanna tailwind becoming headwind)."

---

## Quality Checklist

Before finalizing any narrative, verify:

- [ ] Every level mentioned has a specific NQ price
- [ ] The bias conclusion matches the directional score (don't say "bullish" if the score is +12)
- [ ] Contradictions between dimensions are acknowledged and resolved
- [ ] The key observation is the MOST important thing, not just any observation
- [ ] The risk callout identifies a specific trigger, not a vague risk
- [ ] Changes since the last output are referenced
- [ ] No filler phrases
- [ ] No hedging that renders the narrative useless
- [ ] 3-5 sentences (morning setup: 5-7 sentences)
- [ ] Every sentence adds information not already in the structured output fields
