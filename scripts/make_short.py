"""Stick with Sayem Shorts pipeline.

    shorts analyze  <project> [--model small.en] [--force-draft]
    shorts check    <project>                    resolve every reference in edit.json, print the timeline
    shorts preview  <project> [--at 1.5,6.4,...] render still frames + contact sheet (no audio)
    shorts render   <project> [--out file.mp4]   full render into <project>/final/
    shorts sfx-list [filter]                     list files in the sound-effects library
"""
import argparse, json, math, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Plan, DEFAULT_SFX_DIR


def stale(target, *sources):
    return not target.exists() or any(s.exists() and s.stat().st_mtime > target.stat().st_mtime for s in sources)


def ensure_base(p):
    import build_base
    base = p.work / "base.mp4"
    if stale(base, p.proj / "edit.json", p.work / "analysis.json"):
        t = time.time()
        build_base.run(p)
        print(f"base video built ({time.time() - t:.0f}s)")


def cmd_check(p):
    print(f"{len(p.scenes)} scenes, total {p.total:.2f}s at {p.W}x{p.H}")
    for i, s in enumerate(p.scenes):
        a = p.an["scenes"][str(s["n"])]
        speed = a["video_duration"] / (p.D[i] + p.lead(i))
        print(f"  scene {s['n']:>2}: {p.T[i]:6.2f} -> {p.T[i] + p.D[i]:6.2f}  ({p.D[i]:.2f}s, clip {a['video_duration']:.1f}s,"
              f" avg speed {speed:.2f}x)  -> {s.get('transition', '-')}")
        t_prev = 0.0
        for k, pc in enumerate(s.get("pieces", [])):
            end = p.D[i] if k == len(s["pieces"]) - 1 else p.local(s["n"], pc["until"])
            a0, b0 = pc["src"]
            sp = (b0 - a0) / max(0.01, end - t_prev + (p.lead(i) if k == 0 else 0))
            flag = "  <- fast" if sp > 1.6 else "  <- slow" if sp < 0.75 else ""
            print(f"        shot {k + 1}: src {a0:.2f}-{b0:.2f} until VO {end:.2f}s  speed {sp:.2f}x{flag}")
            t_prev = end
    print("events:")
    for e in p.events():
        label = e.get("text") or e.get("image") or " / ".join(e.get("lines", [])) or ""
        print(f"  {e['t_in']:6.2f} -> {e['t_out']:6.2f}  {e['kind']:8} {label}")
        if e["t_out"] <= e["t_in"]:
            print("         ! ends before it starts")
    print("punches:", ", ".join(f"{t:.2f}" for t, *_ in p.punches()))
    import audio
    modes = audio.mode_points(p, int(p.total * audio.SR))
    print("music:", ", ".join(f"{t:.2f} {m}" for t, m in modes))
    p.caption_colors()


def cmd_preview(p, at):
    import overlay
    from PIL import Image
    ensure_base(p)
    if at:
        times = [float(x) for x in at.split(",")]
    else:  # a frame inside every graphic + the middle of every scene
        times = sorted({round(e["t_in"] + min(0.45, (e["t_out"] - e["t_in"]) / 2), 2) for e in p.events()}
                       | {round(p.T[i] + p.D[i] / 2, 2) for i in range(len(p.T))})
    times = [t for t in times if t < p.total]
    out = p.work / "preview"
    out.mkdir(exist_ok=True)
    for f in out.glob("*.jpg"):
        f.unlink()
    frames = overlay.run(p, times=times, outdir=out)
    sheets = []
    for s in range(0, len(frames), 15):
        ims = [Image.open(f).resize((360, 640)) for f in frames[s:s + 15]]
        cols, rows = 5, math.ceil(len(ims) / 5)
        sheet = Image.new("RGB", (360 * cols, 640 * rows))
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % cols) * 360, (i // cols) * 640))
        path = out / f"sheet_{s // 15 + 1}.jpg"
        sheet.save(path, quality=80)
        sheets.append(path)
    print("frames at:", ", ".join(f"{t:.2f}" for t in times))
    print("sheets:", *map(str, sheets), sep="\n  ")


def cmd_render(p, out):
    import audio, overlay
    t0 = time.time()
    ensure_base(p)
    audio.run(p)
    print(f"audio mixed ({time.time() - t0:.0f}s)")
    if not out:
        title = p.cfg.get("title", "short")
        safe = re.sub(r'[\\/:*?"<>|]', "", title).strip() or "short"
        (p.proj / "final").mkdir(exist_ok=True)
        out = p.proj / "final" / f"{safe}.mp4"
    overlay.run(p, out=Path(out))
    import subprocess
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", subprocess.run(
        ["ffmpeg", "-i", str(out), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr)
    print(f"done in {time.time() - t0:.0f}s -> {out}  ({p.total:.1f}s, {lufs[-1] if lufs else '?'} LUFS)")


def cmd_sfx_list(flt):
    if not DEFAULT_SFX_DIR.exists():
        print(f"No library at {DEFAULT_SFX_DIR}")
        return
    for f in sorted(DEFAULT_SFX_DIR.rglob("*")):
        if f.suffix.lower() in (".mp3", ".wav", ".flac", ".m4a", ".aiff") and (not flt or flt.lower() in str(f).lower()):
            print(f.relative_to(DEFAULT_SFX_DIR))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["analyze", "check", "preview", "render", "sfx-list"])
    ap.add_argument("project", nargs="?")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--force-draft", action="store_true")
    ap.add_argument("--at")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "sfx-list":
        return cmd_sfx_list(a.project)
    if not a.project:
        ap.error("project folder required")
    if a.cmd == "analyze":
        import analyze
        return analyze.run(a.project, a.model, a.force_draft)
    p = Plan(a.project)
    {"check": lambda: cmd_check(p), "preview": lambda: cmd_preview(p, a.at),
     "render": lambda: cmd_render(p, a.out)}[a.cmd]()


if __name__ == "__main__":
    main()
