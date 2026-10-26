"""Step 1: transcribe every voiceover with word timings, measure speech bounds and shot cuts,
make contact sheets for Claude to look at, and draft edit.json."""
import json, math, re, subprocess
from io import BytesIO
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from common import scene_numbers, font_path, DEFAULT_SFX_DIR

TRANSITIONS = ["smoothleft", "zoomin", "fadewhite", "circleopen", "slideup",
               "smoothright", "zoomin", "wipeleft", "circleclose", "slidedown"]


def duration(f):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                         capture_output=True, text=True).stdout
    return float(out.strip())


def speech_bounds(mp3):
    dur = duration(mp3)
    log = subprocess.run(["ffmpeg", "-i", str(mp3), "-af", "silencedetect=n=-40dB:d=0.12", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    lead = ends[0] if starts and starts[0] < 0.02 and ends else 0.0
    end = dur
    if starts and (len(ends) < len(starts) or ends[-1] >= dur - 0.03):
        end = starts[-1]
    lead = lead if lead > 0.08 else 0.0
    return dur, round(lead, 3), round(end, 3)


def shot_cuts(mp4):
    log = subprocess.run(["ffmpeg", "-i", str(mp4), "-vf", "select='gt(scene,0.3)',showinfo", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return [round(float(x), 4) for x in re.findall(r"pts_time:([\d.]+)", log)]


def load_audio(f):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def merge_tokens(ws):
    out = []
    for txt, s, e in ws:
        txt = txt.strip()
        if out and re.match(r"^([,.]\d|%)", txt):  # whisper splits "5,000" into "5" + ",000"
            out[-1] = [out[-1][0] + txt, out[-1][1], e]
        else:
            out.append([txt, s, e])
    return out


def contact_sheets(proj, nums, work):
    sheets = []
    f = ImageFont.truetype(font_path(), 34)
    rows = []
    for n in nums:
        clip = proj / "footages" / f"{n}.mp4"
        dur = duration(clip)
        k = max(1, min(12, math.ceil(dur)))
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip), "-vf",
                              f"fps={k / dur:.5f},scale=150:-2,tile={k}x1", "-frames:v", "1", "-f", "image2pipe",
                              "-vcodec", "png", "-"], capture_output=True).stdout
        strip = Image.open(BytesIO(raw)).convert("RGB")
        row = Image.new("RGB", (110 + 150 * 12, strip.height), (20, 20, 20))
        row.paste(strip, (110, 0))
        ImageDraw.Draw(row).text((10, 10), str(n), font=f, fill=(255, 214, 10))
        ImageDraw.Draw(row).text((10, 60), f"{dur:.0f}s", font=ImageFont.truetype(font_path(), 22), fill="white")
        rows.append(row)
    for p in range(0, len(rows), 8):
        part = rows[p:p + 8]
        sheet = Image.new("RGB", (part[0].width, sum(r.height for r in part)))
        y = 0
        for r in part:
            sheet.paste(r, (0, y)); y += r.height
        path = work / f"sheet_footage_{p // 8 + 1}.jpg"
        sheet.save(path, quality=80)
        sheets.append(path)
    imgs = [p for p in sorted(proj.iterdir()) if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    if imgs:
        tile = 300
        sheet = Image.new("RGB", (tile * min(5, len(imgs)), (tile + 40) * math.ceil(len(imgs) / 5)), (128, 128, 128))
        small = ImageFont.truetype(font_path(), 16)
        for i, p in enumerate(imgs):
            im = Image.open(p).convert("RGBA")
            im.thumbnail((tile, tile))
            x, y = (i % 5) * tile, (i // 5) * (tile + 40)
            sheet.paste(im, (x + (tile - im.width) // 2, y + (tile - im.height) // 2), im)
            ImageDraw.Draw(sheet).text((x + 6, y + tile + 8), p.name[:32], font=small, fill="black")
        path = work / "sheet_images.jpg"
        sheet.save(path, quality=80)
        sheets.append(path)
    return sheets


def draft_plan(proj, nums, scenes):
    sfx_dir = DEFAULT_SFX_DIR if DEFAULT_SFX_DIR.exists() else None
    plan_scenes = []
    for i, n in enumerate(nums):
        a = scenes[str(n)]
        gap = 0.95 if i == len(nums) - 1 else 0.2
        lead = 0.0 if i == 0 else 0.25
        L = a["speech_end"] + gap + lead
        bounds = [0.0] + a["cuts"] + [a["video_duration"]]
        pieces = []
        for k in range(len(bounds) - 1):
            src0 = bounds[k] - 0.01 if k else 0.0
            src1 = bounds[k + 1] - 0.02 if k + 1 < len(bounds) - 1 else bounds[k + 1]
            p = {"src": [round(max(0, src0), 2), round(src1, 2)]}
            if k + 1 < len(bounds) - 1:  # shot length kept proportional; Claude re-times these to words
                p["until"] = round(bounds[k + 1] / a["video_duration"] * L - lead, 2)
            pieces.append(p)
        s = {"n": n, "pieces": pieces}
        if i < len(nums) - 1:
            s["transition"] = TRANSITIONS[i % len(TRANSITIONS)]
        if gap != 0.2:
            s["gap"] = gap
        plan_scenes.append(s)
    last = nums[-1]
    plan = {
        "title": "TODO: YouTube title",
        "hook": {"lines": ["TODO SMALL LINE", "TODO BIG LINE", "TODO LINE?"], "highlight": 1},
        "scenes": plan_scenes,
        "events": [],
        "punches": [],
        "sfx": [],
        "music": {"root": "D", "scale": "minor", "bpm": 100,
                  "modes": [{"from": f"{nums[0]}:start", "mode": "intro"},
                            {"from": f"{nums[1]}:start-0.25", "mode": "groove"} if len(nums) > 1 else None,
                            {"from": f"{last}:start", "mode": "outro"}]},
        "captions": {"colors": []},
        "watermark": True,
        "end_logo": True,
    }
    plan["music"]["modes"] = [m for m in plan["music"]["modes"] if m]
    if sfx_dir:
        plan["sfx_library"] = {
            "dir": str(sfx_dir),
            "whoosh": ["Whooshs/Whoosh 1.mp3", "Whooshs/Whoosh 2.mp3", "Whooshs/Whoosh 3.mp3"],
            "boom": "Impacts/Cinematic Impact.mp3",
            "shutter": "Camera Sounds/CAMERA-35MM-SLR-SHUTTER.wav",
            "riser": "Risers/Cinematic Riser 9.mp3",
        }
    return plan


def run(project, model="small.en", force_draft=False):
    from faster_whisper import WhisperModel
    proj = Path(project).expanduser().resolve()
    work = proj / "_work"
    work.mkdir(exist_ok=True)
    nums = scene_numbers(proj)
    if not nums:
        raise SystemExit(f"No numbered mp3s in {proj}/sound")
    missing = [n for n in nums if not (proj / "footages" / f"{n}.mp4").exists()]
    if missing:
        raise SystemExit(f"Missing footages for: {missing}")
    print(f"Transcribing {len(nums)} voiceovers with whisper {model} ...")
    m = WhisperModel(model, device="cpu", compute_type="int8")
    scenes, lines = {}, []
    for n in nums:
        mp3, mp4 = proj / "sound" / f"{n}.mp3", proj / "footages" / f"{n}.mp4"
        adur, lead, end = speech_bounds(mp3)
        segs, _ = m.transcribe(load_audio(mp3), word_timestamps=True)
        words = merge_tokens([(w.word, w.start, w.end) for s in segs for w in s.words])
        words = [[t, round(max(0, s - lead), 2), round(max(0, e - lead), 2)] for t, s, e in words]
        vdur, cuts = duration(mp4), shot_cuts(mp4)
        scenes[str(n)] = dict(audio_duration=adur, trim_start=lead, speech_end=round(end - lead, 3),
                              video_duration=vdur, cuts=cuts, words=words)
        speed = vdur / (end - lead + 0.45)
        lines.append(f"Scene {n}: speech {end - lead:.2f}s | clip {vdur:.1f}s, shot cuts at {cuts} | "
                     f"fit speed ~{speed:.2f}x{'  <- consider trimming' if speed > 1.5 else ''}")
        lines.append("   " + "  ".join(f"{t}@{s:.2f}" for t, s, e in words))
    (work / "analysis.json").write_text(json.dumps(dict(scenes=scenes), indent=1))
    (work / "transcript.txt").write_text("\n".join(lines) + "\n")
    sheets = contact_sheets(proj, nums, work)
    edit = proj / "edit.json"
    if force_draft or not edit.exists():
        edit.write_text(json.dumps(draft_plan(proj, nums, scenes), indent=2, ensure_ascii=False))
        print(f"Drafted {edit}")
    else:
        print(f"Kept existing {edit} (use --force-draft to overwrite)")
    print("\n".join(lines))
    print("Contact sheets:", *map(str, sheets), sep="\n  ")
