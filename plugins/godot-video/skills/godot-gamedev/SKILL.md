---
name: "godot-gamedev"
description: "Use when making a development film, devlog or code walkthrough video of a Godot game: choosing the systems to teach, pairing each short code excerpt with the visible behavior it causes, recording evidence shots, and scripting narration. For a promo, use godot-trailer; for comparing a design document with the game, use godot-gdd."
---

# Godot development film

Viewers learn code when they can see what it does. So the unit of this film is a **pair**: a short excerpt, then that excerpt's visible effect in the running game. Use `godot-capture` for recording and ffmpeg steps.

## 1. Choose what to teach

Read the project and run it. Pick the few systems that explain why the game feels the way it does, or the decisions someone could reuse. A tour of every file teaches nothing. Agree on the audience with the user: what a beginner needs on screen differs from what a Godot veteran needs.

## 2. Write `pairs.md`

| # | Point to teach | Code (file:lines, commit) | Visible result | Footage | Honest label |
|---|---|---|---|---|---|
| 1 | Coyote time forgives late jumps | `player.gd:88-94`, abc123 | Jump that succeeds just past the ledge | take03, 0:04 to 0:07 | Real play, slowed to 50% |

Rules for a pair:

- **Short enough to read aloud.** Around 3 to 12 lines. Remove unrelated lines and mark the cut with `# ...`, never change what's left.
- **The result must be visible.** A file name, another code panel or a statement isn't a result. For code with no visual effect, show its effect some other way: test output, a debug overlay, a printed value, with the limits explained.
- **The result comes straight after the code.** Don't stack several excerpts and promise the payoff later.
- **Name the link.** Narration points from a specific line or value to a specific thing on screen.

Changing a value and showing both versions is often the clearest proof. Do it in the capture copy, and label it as a modified build.

## 3. Show the code

Render excerpts from the actual file at the recorded commit, so they can't drift. Use large type: if it can't be read on a laptop at normal size, cut lines. Build the code panel as a Godot scene, or take a real editor screenshot. If you build something that looks like the editor, label it as a reconstruction.

## 4. Record the evidence

Follow `godot-capture`. Use real motion for movement, collision, cameras and state changes. Label anything staged: posed shots, slow motion, visible colliders, teleports for a setup. Say what a test does and doesn't prove.

## 5. Script and assemble

Write `script.md` from the pairs, opening with the game itself, and ending on what the viewer can try. Say what didn't work too, since that's often the most useful part. Narration comes from the user's voice or a tool they choose; without either, deliver on-screen text plus the script. Then assemble and check using `godot-capture`.

Before finishing, re-check every excerpt against its file and commit, and every statement about the code against the code. List anything you couldn't verify.

## Boundaries

Don't change the original game, push commits or publish unless the user asks. A bug found while filming goes in the report, and the film doesn't hide it.
