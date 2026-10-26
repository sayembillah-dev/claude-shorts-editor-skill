"""Shared plan + timeline logic for the Stick with Sayem Shorts pipeline.

A project folder looks like:
    footages/1.mp4 ... N.mp4     one clip per voiceover line
    sound/1.mp3 ... N.mp3        voiceover, numbered to match the clips
    logo.png                     channel logo (optional)
    *.png / *.jpg                real photos, maps, etc. referenced from edit.json
    edit.json                    the edit plan (drafted by `analyze`, refined by Claude)
    _work/                       generated: analysis, sheets, previews, intermediates
    final/                       generated: the finished Short
"""
import json, os, re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SFX_DIR = SKILL_DIR.parent / "Sound Effects Collection"
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/Library/Fonts/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
]


def font_path(cfg=None):
    if cfg and cfg.get("font"):
        return cfg["font"]
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    raise SystemExit("No bold font found; set \"font\" in edit.json to a .ttf path")


def norm(word):
    return re.sub(r"[^\w]", "", word.lower())


def scene_numbers(proj):
    return sorted(int(p.stem) for p in (proj / "sound").glob("*.mp3") if p.stem.isdigit())


REF_RE = re.compile(r"^(\d+)([:@])(.+?)([+-]\d+(?:\.\d+)?)?$")


def parse_ref(ref):
    """Time references used everywhere in edit.json.

    "2:start"      start of scene 2's voiceover          "2:end"   when scene 2's transition begins
    "2@3.1"        3.1 s into scene 2's voiceover        "2:5,000" when the word "5,000" starts
    "8:could#2"    2nd "could" in scene 8                "2:pounds>"  when "pounds" ends
    Any of them can take an offset: "3:start-0.25", "4:raleigh+0.04". Plain numbers are absolute seconds.
    """
    if isinstance(ref, (int, float)) or isinstance(ref, dict):
        return ref
    m = REF_RE.match(str(ref).strip())
    if not m:
        raise SystemExit(f"Bad time reference: {ref!r}")
    scene, sep, body, off = int(m[1]), m[2], m[3], float(m[4] or 0)
    if sep == "@":
        return dict(scene=scene, at=float(body), offset=off)
    if body in ("start", "end"):
        return dict(scene=scene, at=body, offset=off)
    edge = "end" if body.endswith(">") else "start"
    return dict(scene=scene, word=body.rstrip(">"), edge=edge, offset=off)


class Plan:
    def __init__(self, project, need_edit=True):
        self.proj = Path(project).expanduser().resolve()
        self.work = self.proj / "_work"
        self.work.mkdir(exist_ok=True)
        an_path = self.work / "analysis.json"
        if not an_path.exists():
            raise SystemExit("No _work/analysis.json yet: run `shorts analyze <project>` first")
        self.an = json.loads(an_path.read_text())
        self.cfg = json.loads((self.proj / "edit.json").read_text()) if need_edit else {}
        c = self.cfg
        self.W, self.H = c.get("size", [1080, 1920])
        self.fps = c.get("fps", 30)
        self.xf = c.get("transition_duration", 0.25)
        self.scenes = c.get("scenes") or [dict(n=n) for n in scene_numbers(self.proj)]
        self.idx = {s["n"]: i for i, s in enumerate(self.scenes)}
        self.D = []
        for i, s in enumerate(self.scenes):
            a = self.an["scenes"][str(s["n"])]
            gap = s.get("gap", 0.95 if i == len(self.scenes) - 1 else 0.2)
            self.D.append(round(a["speech_end"] + gap, 3))
        self.T = [round(sum(self.D[:i]), 3) for i in range(len(self.D))]
        self.total = round(sum(self.D), 3)
        self.words = []
        for s in self.scenes:
            i = self.idx[s["n"]]
            for k, (txt, a, b) in enumerate(self.an["scenes"][str(s["n"])]["words"]):
                self.words.append(dict(scene=s["n"], k=k, text=txt, start=self.T[i] + a, end=self.T[i] + b))

    # ---- timing helpers
    def lead(self, i):
        """Seconds of footage before scene i's voice starts (covers the incoming transition)."""
        return 0.0 if i == 0 else self.xf

    def scene_word(self, n, key):
        name, _, occ = str(key).partition("#")
        occ = int(occ or 1)
        hits = [w for w in self.words if w["scene"] == n and norm(w["text"]) == norm(name)]
        if len(hits) < occ:
            said = " ".join(w["text"] for w in self.words if w["scene"] == n)
            raise SystemExit(f"Word {key!r} not found in scene {n}. Scene {n} says: {said}")
        return hits[occ - 1]

    def t(self, ref, default=None):
        """Resolve a time reference (see parse_ref) to seconds on the output timeline."""
        if ref is None:
            ref = default
        ref = parse_ref(ref)
        if isinstance(ref, (int, float)):
            return float(ref)
        n = ref["scene"]
        if n not in self.idx:
            raise SystemExit(f"Scene {n} is not in the plan")
        i = self.idx[n]
        off = ref.get("offset", 0.0)
        if "word" in ref:
            w = self.scene_word(n, ref["word"])
            return (w["end"] if ref.get("edge") == "end" else w["start"]) + off
        at = ref.get("at", "start")
        if at == "start":
            return self.T[i] + off
        if at == "end":
            return (self.T[i + 1] - self.xf if i + 1 < len(self.T) else self.total) + off
        return self.T[i] + float(at) + off

    def local(self, n, v):
        """VO-relative seconds inside scene n for a number or a word."""
        if isinstance(v, (int, float)):
            return float(v)
        r = parse_ref(f"{n}:{v}")
        return self.t(r) - self.T[self.idx[n]]

    def scene_of(self, ref):
        r = parse_ref(ref)
        if isinstance(r, dict):
            return r["scene"]
        return self.scenes[max(i for i in range(len(self.T)) if self.T[i] <= r + 1e-6)]["n"]

    # ---- resolved graphics
    def events(self):
        c, out = self.cfg, []
        hook = c.get("hook")
        if hook and hook.get("lines"):
            until = self.t(hook.get("until"), self.T[1] - self.xf if len(self.T) > 1 else self.total)
            out.append(dict(hook, kind="hook", t_in=0.0, t_out=until))
        for e in c.get("events", []):
            t_in = self.t(e["from"])
            t_out = self.t(e["to"]) if "to" in e else self.t(f"{self.scene_of(e['from'])}:end")
            d = dict(e, t_in=t_in, t_out=t_out)
            for key in ("strike_at", "wobble_at"):
                if key in e:
                    d[key] = self.t(e[key])
            out.append(d)
        if c.get("end_logo", True) and (self.proj / c.get("logo", "logo.png")).exists():
            out.append(dict(kind="endlogo", t_in=self.T[-1], t_out=self.total))
        return out

    def punches(self):
        out = [(0.0, 0.14, 1.0)] if self.cfg.get("open_punch", True) else []
        for p in self.cfg.get("punches", []):
            out.append((self.t(p["at"]), p.get("strength", 0.06), p.get("shake", 0.0)))
        return sorted(out)

    def caption_colors(self):
        out = {}
        for c in self.cfg.get("captions", {}).get("colors", []):
            r = parse_ref(c["word"])
            w = self.scene_word(r["scene"], r["word"])
            out[(w["scene"], w["k"])] = c["color"]
        return out
