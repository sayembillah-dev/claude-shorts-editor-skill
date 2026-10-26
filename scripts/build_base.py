"""Step 2: cut + speed-fit each clip so its shots land on the right words, then chain xfade transitions."""
import subprocess


def run(p):
    inputs, chains = [], []
    for i, s in enumerate(p.scenes):
        n = s["n"]
        inputs += ["-i", str(p.proj / "footages" / f"{n}.mp4")]
        L = p.D[i] + p.lead(i)  # segment length on the output timeline
        vdur = p.an["scenes"][str(n)]["video_duration"]
        pieces = s.get("pieces") or [{"src": [0, vdur]}]
        labels, t_prev = [], 0.0
        for k, pc in enumerate(pieces):
            a, b = pc["src"]
            b = min(b, vdur)
            t_end = L if k == len(pieces) - 1 else p.local(n, pc["until"]) + p.lead(i)
            out_dur = t_end - t_prev
            if out_dur <= 0.02:
                raise SystemExit(f"Scene {n} piece {k + 1} ends before it starts (until={pc.get('until')})")
            chains.append(
                f"[{i}:v]trim=start={a}:end={b},setpts=(PTS-STARTPTS)*{out_dur / (b - a):.5f},"
                f"fps={p.fps},tpad=stop_mode=clone:stop_duration=0.5,trim=duration={out_dur:.4f},"
                f"setpts=PTS-STARTPTS[s{i}p{k}]")
            labels.append(f"[s{i}p{k}]")
            t_prev = t_end
        chains.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0,"
                      f"scale={p.W}:{p.H}:force_original_aspect_ratio=increase,crop={p.W}:{p.H},setsar=1,"
                      f"format=yuv420p,settb=AVTB,trim=duration={L:.4f}[seg{i}]")
    prev = "[seg0]"
    if len(p.scenes) == 1:
        chains[-1] = chains[-1].replace("[seg0]", "[vout]")
    for k in range(1, len(p.scenes)):
        out = f"[x{k}]" if k < len(p.scenes) - 1 else "[vout]"
        tr = p.scenes[k - 1].get("transition", "fade")
        chains.append(f"{prev}[seg{k}]xfade=transition={tr}:duration={p.xf}:offset={p.T[k] - p.xf:.4f}{out}")
        prev = out
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chains),
                    "-map", "[vout]", "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-an",
                    str(p.work / "base.mp4")], check=True)
