# shorts-skill

Turns a folder of numbered clips + numbered voiceovers into a finished, synced YouTube Short.

## Make a new Short
1. Make a folder next to `shorts1` (for example `shorts2`) with:
   - `footages/1.mp4, 2.mp4, ...` (vertical 1080x1920)
   - `sound/1.mp3, 2.mp3, ...` (voiceover N plays over clip N)
   - `logo.png`, plus any real photos or map images
2. In Claude Code, say: **"Edit the short in shorts2. Title: <your title>"**
   Claude uses this skill: transcribes, plans the edit, previews, renders.
3. The video lands in `shorts2/final/<title>.mp4`.

## Run it yourself
```bash
cd "/Users/sayembillah/Desktop/Stick with sayem/shorts-skill"
./shorts analyze ../shorts2     # transcribe + draft edit.json
./shorts check ../shorts2       # show the timeline
./shorts preview ../shorts2     # still frames in shorts2/_work/preview
./shorts render ../shorts2      # final video
```
The first run installs its Python tools automatically (needs `ffmpeg`: `brew install ffmpeg`).

## What's inside
- `SKILL.md` instructions Claude follows (editing rules, workflow)
- `reference/edit-schema.md` every option in `edit.json`
- `examples/fossil-block.edit.json` the plan behind the fossil Short
- `scripts/` the pipeline
- Sound effects come from `../Sound Effects Collection`; music is generated (royalty-free).
