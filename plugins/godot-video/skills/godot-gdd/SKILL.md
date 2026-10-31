---
name: "godot-gdd"
description: "Use when checking a game design document (GDD) against a Godot project, finding what's built, partial, missing or undecided, or making an explainer video that walks through the design using real game footage. Reports evidence for each claim and doesn't change the game or the design."
---

# Godot GDD

The most useful thing about a design document is knowing how far to trust it. This skill compares the document with the game, then optionally explains both on video.

If there are several design documents and none is clearly current, ask which one counts.

## 1. Read everything

Read the whole document, including open questions and revision notes, then the relevant scripts, scenes and tests. A README that states the rules counts as a design document. Run the game and the tests where possible. Reading code shows that a feature exists, not that it works.

Many rules can be checked without a window. In a copy of the project, a `SceneTree` script can load the main scene, read values and call the game's own functions, then run through play at high speed:

```bash
godot --headless --path copy --fixed-fps 60 --script res://gdd_check.gd -- 1
```

Take the seed from the arguments and repeat with several seeds, since one run proves little about balance or randomness: on the test game, six seeded runs in seconds confirmed a claim about when an idle player loses. Headless runs can't confirm visuals, so a claim about something on screen stays **Built** until it's been seen.

## 2. Write the status ledger

`gdd-status.md`, one row per claim the document makes:

| Claim (section) | Status | Evidence | Notes |
|---|---|---|---|
| Dash has 0.5 s cooldown (§3.2) | Differs | `player.gd:42` uses 0.8 | Which one is right? |
| Save on checkpoint (§4.1) | Verified | `test_save.gd` passes; seen in a run | |
| Boss phase 2 (§5.3) | Missing | No code or scene | |

Use one status per row:

- **Verified:** seen running, a test passes that really covers it, or a script ran the real game code. Note how many runs.
- **Built:** the code exists, but nothing has run it yet.
- **Partial:** part of the claim holds; say which part.
- **Differs:** the game does something else. Don't decide which is right.
- **Missing:** no sign of it in the project.
- **Open:** the document itself leaves this undecided.

Evidence is a file and line, a test name, or a run you did. Without evidence, the status can't be Built or Verified. Cover every section; if you skip one, say so and why. Also list what the game does that the document never mentions.

Stop here if the user only wanted the comparison. Report the rows that need a human decision first.

## 3. Explainer video (optional)

The video teaches someone how the design works and how much of it exists. Don't read the document aloud in order. For each main mechanic, explain the chain:

> What the player should feel → the rule that causes it → the system that owns it → what the player sees → how we know it works.

Then:

1. Write `script.md` with one section per beat: the narration, the footage, and the status from the ledger.
2. Record footage with `godot-capture`. Each shot shows the claim it's used for.
3. Show the status on screen whenever it isn't Verified. Something Missing gets a text or diagram card, never staged footage that passes as the game.
4. Close with the open decisions, since that's what the team needs to act on.
5. Assemble and check using `godot-capture`.

Narration comes from the user's voice or a tool they choose. Without either, deliver the video with on-screen text, and hand over the script.

## Boundaries

Don't edit the document or the game. Differences and gaps go in the report for the user to resolve. A quote from the document never counts as evidence that the game does it.
