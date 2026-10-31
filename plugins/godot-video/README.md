# godot-video

- `godot-capture`: repeatable footage with Movie Maker and an input driver, and the ffmpeg recipes to assemble it. The other three skills use it, so install it with them.
- `godot-trailer`: a short trailer built around one hook.
- `game-music`: simple synthesized instrumental music, with beats at exact times to cut on. Needs Python 3, with no model or network.
- `trailer-music`: write requests for external music generators, such as the Gemini app or Suno, then build a beat grid from the track and check it by ear. Needs Python and ffmpeg.
- `godot-gdd`: compare a design document with the game, and explain both on video.
- `godot-gamedev`: a development film that pairs each code excerpt with what it does in the game.

Needs Godot and ffmpeg. There is no required voice, brand or render service; narration comes from you, and music too unless you use `game-music`. The idea of agent skills for game films came from [brutalist.art](https://github.com/nikbearbrown/brutalist.art), which has no license: nothing here is copied from it, and its skills depend on its own video pipeline.
