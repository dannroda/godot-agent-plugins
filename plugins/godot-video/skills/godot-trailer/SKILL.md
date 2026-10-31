---
name: "godot-trailer"
description: "Use when cutting a trailer or short promo for a Godot game from real gameplay: choosing the hook, writing a shot list, recording repeatable takes, editing to music, end card, and a test with someone who hasn't seen the game. Not for full feature tours; see godot-gamedev for development films."
---

# Godot trailer

A trailer gets one job: make the right player want this game. Leave out everything else, including features that took months. Use `godot-capture` for recording and ffmpeg steps.

## 1. Agree on the brief

Play the build and read its source, then fill this in. Ask the user for what you can't get from the project.

| Question | Example |
|---|---|
| Who is it for? | Fans of short tactical roguelikes |
| What's the one thing no other game gives them? | You rewind time, but your past self stays in the level |
| What must they do at the end? | Wishlist on Steam (a single action, with a real URL; if none exists yet, say so on the card or leave it out, never invent one) |
| How long? | 30 to 90 seconds; shorter if the idea is simple |
| What state is the build in? | Early access, so label footage if it will change |

If the second answer doesn't fit in one sentence, stop and settle it with the user. Everything else depends on it.

## 2. Shape it around the hook

A dependable default, to change whenever the game calls for it:

1. **First seconds:** the most striking real moment, with no logo before it.
2. **The rule:** one or two shots that make clear what the player does.
3. **Escalation:** the same idea, bigger each time. Variety only counts if it builds.
4. **Peak:** the biggest moment, then a sharp cut.
5. **End card:** title, platforms, one action.

Text on screen stays short and readable on a phone. Words explain only what the footage can't.

## 3. Write the shot list before recording

`shots.md`, one row per shot:

| # | Purpose | Footage | Seconds | Driver or manual | Take |
|---|---|---|---|---|---|

Check each shot against the running build. A shot of something not in the build gets cut, not faked. It's fine for a shot to fail at this stage and change the plan.

## 4. Record

Follow `godot-capture`. Hide debug text, and hide the HUD unless a shot needs it: at trailer size its text is too small to read, and it competes with the action. Record more than each shot needs, so cuts have room. Record text cards with the `title_card.gd` script in `godot-capture`, so they use the game's font, or as your own Godot scenes.

## 5. Edit to music

Prefer music from the user, with its license noted in `CREDITS.md`. If they have none, generate a simple track from the cut list with the `game-music` skill, and tell them it's a synthetic placeholder. With a known tempo, one beat lasts `60 / BPM` seconds, so a list of cut points can come from it. Cut on strong beats and save the biggest hit for the peak. Cut on the beat where it helps, and don't force a shot that needs longer to read. Make sure the ending lands on the music, not during a fade-out in silence.

Narration is optional, and most trailers don't need it. If the user wants it, use their voice or a tool they choose, and keep each line tied to what's on screen.

## 6. Test before calling it done

Run the checks in `godot-capture`. Then ask the user to show it to someone who hasn't seen the game, and to ask afterward:

- What is this game? What do you do in it?
- Would you try it? Why or why not?

You've watched every frame, so you can't answer those for a stranger. Report the trailer as unreviewed until this has happened, and don't invent the answers.

## Boundaries

- Footage comes from the game. No pre-rendered or generated shots presented as gameplay, unless clearly labelled.
- Don't change the game to make a shot work without telling the user. A bug found while recording goes in the report.
- Don't upload or publish unless the user asks.
