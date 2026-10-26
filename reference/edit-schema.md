# edit.json reference

## Time references
Used by `from`, `to`, `at`, `strike_at`, `wobble_at`, music `modes[].from`, and `pieces[].until` (inside a scene, just the number or word).

| Form | Meaning |
|---|---|
| `"2:start"` | scene 2's voice starts |
| `"2:end"` | scene 2's outgoing transition starts (default `to` for events) |
| `"2@3.1"` | 3.1 s into scene 2's voice |
| `"2:5,000"` | the word "5,000" starts (case/punctuation ignored) |
| `"8:could#2"` | the 2nd "could" in scene 8 |
| `"2:pounds>"` | the word "pounds" ends |
| `"…+0.04"` / `"…-0.25"` | offset in seconds, on any of the above |
| `12.5` | absolute seconds on the output timeline |

Scene numbers are the file numbers (`sound/2.mp3` is scene 2).

## Top level
| Key | Default | Notes |
|---|---|---|
| `title` | | Output file name `final/<title>.mp4` |
| `hook` | | `{"lines": [small, BIG, payoff?], "highlight": 1, "until": ref}`; shown from frame one until scene 2's transition |
| `scenes` | all numbered files | ordered list, see below |
| `events` | `[]` | on-screen graphics, see below |
| `punches` | `[]` | `{"at": ref, "strength": 0.06, "shake": 0}`; strength 0.05 subtle … 0.16 dramatic, shake 0–1 |
| `open_punch` | `true` | zoom + shake on frame one |
| `sfx` | `[]` | extra sound effects, see below |
| `auto_sfx` | `true` | boom/whoosh/shutter/chime/pop/bell placed automatically |
| `sfx_library` | | `{"dir": "../Sound Effects Collection", "whoosh": [..files..], "boom": file, "shutter": file, "riser": file, "thud": file}` (paths relative to `dir`; a list rotates). Pops, chimes and scrapes are always synthesized. |
| `music` | | see below |
| `captions` | | `{"enabled": true, "max_words": 3, "max_chars": 15, "size": 84, "colors": [{"word": "8:could#2", "color": "red"}]}` |
| `watermark` | `true` | small logo top-left until the end card |
| `end_logo` | `true` | big logo on the last scene |
| `logo` | `"logo.png"` | |
| `layout` | | `stamp_y [375,515]`, `card_y 800`, `caption_y 1290`, `hook_y 330`, `end_logo_y 255` |
| `mix` | | `vo_lufs -16`, `music_db -9`, `sfx_db -5`, `final_lufs -14` |
| `transition_duration` | `0.25` | |
| `fps`, `size`, `font` | `30`, `[1080,1920]`, Arial Black | |

## scenes[]
```json
{"n": 2, "gap": 0.2, "push": 0.035, "transition": "zoomin",
 "pieces": [{"src": [0.00, 1.94], "until": 1.40}, {"src": [1.95, 3.98], "until": "5,000"}, {"src": [3.99, 6.00]}]}
```
- `pieces`: footage ranges in source seconds, played in order. Each non-last piece ends at `until` (VO seconds or a word in this scene); the last fills to the scene end. Speed is fitted automatically.
- `gap`: silence after the last word before the next scene (default 0.2; last scene 0.95).
- `push`: slow zoom across the scene (0.035 default; 0.10 for a "going inside" feel).
- `transition`: ffmpeg xfade into the next scene. Good ones: `smoothleft`, `smoothright`, `zoomin`, `fadewhite`, `fadeblack`, `circleopen`, `circleclose`, `slideup`, `slidedown`, `wipeleft`, `radial`, `hblur`, `dissolve`.

## events[]
| kind | Fields | Look |
|---|---|---|
| `stamp` | `text`, `from`, `to`, `color` (yellow\|green\|red\|white\|blue\|orange), `row` (1\|2), `wobble_at` | tilted pill, pops in |
| `warn` | same as stamp; defaults red, row 2 | smaller caution pill under a stamp |
| `strike` | `text`, `from`, `to`, `strike_at`, `color` (white) | pill that gets a red line through it |
| `card` | `image`, `from`, `to`, `tilt` (±3), `label` ("REAL PHOTO", `null` to hide), `y` | polaroid-style photo, flash + shutter |
| `map` | `image`, `from`, `to`, `pin` [fx, fy] (fraction of the art), `chime` ("low"), `y` | cream card with a pulsing pin |

Keep at most one card/map and two stamps on screen at once.

## sfx[]
| type | Fields |
|---|---|
| `boom`, `thud`, `pop`, `shutter`, `ding`, `whoosh` | `at`, `gain`, optional `file`, `align` (onset\|peak\|end), `length` |
| `riser` | `from`, `to`, `gain` (library risers are aligned so their peak hits `to`) |
| `scrape` | `from`, `to`, `style` (brush\|pencil) |
| `file` | `file` (relative to the library dir or absolute), `at`, `align`, `gain`, `length` |

Typical gains: boom 0.55–1.0, thud 0.7–0.9, riser 0.4–0.45, whoosh 0.55.

## music
```json
{"root": "D", "scale": "minor", "bpm": 100, "file": null,
 "modes": [{"from": "1:start", "mode": "intro"}, {"from": "2:start-0.25", "mode": "groove"}]}
```
| mode | Sound |
|---|---|
| `intro` | drone + ticking, under the hook |
| `groove` | kick, pumping bass, marimba arp, pad |
| `drive` | groove + 16th hats (later, more energy) |
| `mystery` | drone, heartbeat, pad ("inside", "buried", "but…") |
| `suspense` | mystery + ticking |
| `lift` | full groove + bright high arp (payoff) |
| `outro` | pad + bright arp, fades out |
| `stop` | tape-stop into silence ending at `from`; put it ~0.04 s before the dramatic word |

Put mode changes 0.2–0.25 s before a scene starts so they land with the transition. `file` replaces the synth with your own track (modes then only change its volume; `stop` still tape-stops).
