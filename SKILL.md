---
name: shorts-skill
description: Edit a finished, synced, hook-first YouTube Short for the Stick with Sayem channel from a folder of numbered footage clips (footages/1.mp4…) and matching numbered voiceovers (sound/1.mp3…), plus a logo and optional real photos / map graphics. Use when the user says "edit my short", "make a short from these clips", "new short in <folder>", or drops a project folder with footages/ and sound/. Transcribes the voiceover with word timings, cuts and speed-fits every shot to the words, adds burned-in karaoke captions, a frame-one hook title, stat stamps, real-photo and map cards, camera punch-ins, transitions, sound effects from the user's library, and a music bed with drops, then renders a 1080x1920 MP4 at -14 LUFS.
---

# Stick with Sayem — Shorts editor

The heavy lifting is done by scripts. **Your job is the creative plan in `edit.json`**: which shot sits under which words, what pops on screen when, where the music drops. Do not rewrite the scripts for a normal edit; change `edit.json` and re-render.

```
SKILL = "/Users/sayembillah/Desktop/Stick with sayem/shorts-skill"
"$SKILL/shorts" analyze  "<project>"        # transcribe + measure + contact sheets + draft edit.json
"$SKILL/shorts" check    "<project>"        # resolve every reference, print timeline (cheap, no render)
"$SKILL/shorts" preview  "<project>" [--at 1.5,6.4]   # still frames + contact sheet (~1 min)
"$SKILL/shorts" render   "<project>"        # final MP4 -> <project>/final/<title>.mp4 (~2 min / 50 s)
"$SKILL/shorts" sfx-list [filter]           # browse "Sound Effects Collection"
```
First run builds a venv automatically (`setup.sh`; needs `ffmpeg` from Homebrew).

## Project folder convention
```
<project>/footages/1.mp4 … N.mp4   one animated clip per voiceover line (1080x1920)
<project>/sound/1.mp3 … N.mp3      voiceover line N plays over clip N
<project>/logo.png                 channel logo (watermark + end card)
<project>/*.png|jpg                real photos, map graphics … (referenced by file name)
```
If a file is missing or numbering does not match, stop and tell the user before editing.

## Workflow (keep the task list to these steps)
1. **Analyze.** Run `shorts analyze "<project>"`. Read `_work/transcript.txt` (words with timings, shot cuts, fit speed) and look at `_work/sheet_footage_*.jpg` and `_work/sheet_images.jpg`. Look at each sheet once; do not open individual frames.
2. **Get the title.** Use the user's title if given (it becomes the hook and the file name). If none, load the `youtube-shorts` skill and propose a keyword-rich question/number title.
3. **Write `edit.json`.** Start from the draft analyze wrote; use `examples/fossil-block.edit.json` as the model of a finished plan and `reference/edit-schema.md` for every field. Apply the editing rules below.
4. **Check.** `shorts check` and fix anything flagged (word not found, `<- fast` shots, events that end before they start).
5. **Preview.** `shorts preview` with no `--at` (one frame inside every graphic + every scene middle). Look at the sheet(s); fix overlaps, covered faces, wrong timings. One or two rounds is normal.
6. **Render.** `shorts render`. Confirm the printed duration and ~-14 LUFS, grab frame 0 (`ffmpeg -ss 0 -i out.mp4 -frames:v 1 f0.jpg`) and verify the hook is on it.
7. **Deliver.** Send the MP4, list what is on screen and in the audio, and remind the user to tick YouTube's "Altered or synthetic content" box for AI footage. Say plainly that nobody has listened to it yet if that is true.

## Editing rules (what made the fossil Short work)
**Sync**
- Every scene lasts its speech + `gap` (0.2 s default, 0.25 before a reveal, ~0.95 on the last/subscribe scene). The transition finishes exactly as the next line starts; this is automatic.
- Re-time `pieces` so each shot change lands on the word it illustrates (e.g. the block on the cart appears on "5,000"). `until` takes a VO time or a word: `"until": "5,000"`.
- Keep shot speeds roughly 0.85x–1.45x. If `check` says `<- fast`, trim the boring start/end of that shot's `src` instead of speeding up.
- Never let a trimmed `src` cross a detected cut: end pieces at `cut-0.02`, start the next at `cut-0.01` (the draft already does this).

**Retention (youtube-shorts Retention Ladder)**
- Frame one must carry the hook text (handled: the hook is fully on screen at t=0, with a boom and a zoom punch). The hook is 3 lines: small lead-in, BIG yellow key phrase (`highlight`), payoff line ending in `?`.
- Something new on screen every 2–4 s: a stamp, a card, a map, a punch-in or a shot change. Do not leave a 5 s stretch with nothing new.
- Stamps restate the number or key idea in 1–4 words (`~5,000 LBS`, `75 MILLION YEARS`, `8–10 FT LONG`). They never add a claim the voiceover does not make; use `warn` ("NOT CONFIRMED YET") when the script hedges.
- Real photos go in as `card`s at the moment the VO talks about that real thing; they are proof the story is real and are the strongest beats. Maps go in when a place is named, with `pin` on the spot.
- Punch-ins on the biggest number, the twist word, and the reveal; strong shake only on 1–2 moments.
- Music arc: `intro` under the hook, `groove` for facts, `mystery` for "inside / buried / but…", a `stop` (tape-stop to silence) right before the single most dramatic word, `suspense` after it, `lift` for the payoff, `outro` on subscribe.
- End on the subscribe clip with the logo card; keep it short so the Short loops back into the opening line.

**Layout (1080x1920, YouTube UI safe)**
- Stamps y≈375 (row 1) / 515 (row 2); cards and maps centred y≈800; captions y≈1290 (above the title/channel UI); watermark top-left; end-card logo y≈255. Change `layout` only if a face or key action is covered in preview.
- Captions are automatic (≤3 words, active word yellow). Colour one dramatic word red via `captions.colors`.

**Sound**
- Auto: boom on frame one, whoosh on every transition, shutter on each card, chime on each map, pop on each stamp, bell + click on the end logo.
- Add by hand: `thud` on heavy numbers, `riser` into the big reveals, `boom` on scene-level turns ("But…"), `scrape` (brush/pencil) when hands work on screen.
- `sfx_library` maps kinds to files in "Sound Effects Collection" (whoosh, boom, shutter, riser by default). Use `shorts sfx-list impact` etc. to pick others; any kind without a file falls back to a synthesized sound.
- Music is synthesized (royalty-free, no Content ID risk). Use `music.file` only for a track the user owns or licensed.

## Cost discipline
- Do not re-read the scripts unless something breaks; everything creative lives in `edit.json`.
- Prefer `check` (text) over `preview` (images); preview only with targeted `--at` times after the first full preview.
- If whisper mis-hears a word, fix the text in `_work/analysis.json` instead of re-running analyze.

## Files
- `scripts/` pipeline (`make_short.py` entry, `analyze.py`, `build_base.py`, `audio.py`, `overlay.py`, `common.py`).
- `reference/edit-schema.md` every `edit.json` field, time-reference syntax, transitions, music modes.
- `examples/fossil-block.edit.json` the complete plan behind "What's Inside This 5,000-Pound Fossil Block?" (`../shorts1`).
