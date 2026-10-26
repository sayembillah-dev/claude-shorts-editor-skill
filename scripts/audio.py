"""Step 3: music bed + sound effects + voiceover on the shared timeline, then the ducked loudness-normalised mix."""
import subprocess
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve
from scipy.io import wavfile

SR = 48000
rng = np.random.default_rng(7)

# per-mode layer levels for the synthesized bed
LEVELS = {
    "intro":    dict(pad=.5, groove=0, hat16=0, tick=1, mystery=.6, bright=0),
    "groove":   dict(pad=.5, groove=1, hat16=.5, tick=0, mystery=0, bright=0),
    "drive":    dict(pad=.6, groove=1, hat16=1, tick=0, mystery=0, bright=0),
    "mystery":  dict(pad=.5, groove=0, hat16=0, tick=0, mystery=1, bright=0),
    "suspense": dict(pad=.3, groove=0, hat16=0, tick=1, mystery=1, bright=0),
    "lift":     dict(pad=1, groove=1, hat16=1, tick=0, mystery=0, bright=1),
    "outro":    dict(pad=1, groove=0, hat16=0, tick=0, mystery=0, bright=.6),
    "stop":     dict(pad=0, groove=0, hat16=0, tick=0, mystery=0, bright=0),
}
# when edit.json supplies a music file instead, modes only scale its volume
FILE_LEVEL = dict(intro=.7, groove=1, drive=1, mystery=.55, suspense=.4, lift=1, outro=.8, stop=0)
NOTES = "C C# D D# E F F# G G# A A# B".split()
FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def tt(n):
    return np.arange(n) / SR


def filt(x, kind, f):
    return sosfilt(butter(4, f, btype=kind, fs=SR, output="sos"), x)


def reverb(x, secs=1.2, mix=0.25):
    n = int(secs * SR)
    ir = filt(rng.standard_normal(n) * np.exp(-tt(n) / (secs / 5)), "lowpass", 5000)
    wet = fftconvolve(x, ir)[: len(x)]
    wet *= np.abs(x).max() / (np.abs(wet).max() + 1e-9)
    return x * (1 - mix) + wet * mix


def load(path, mono=False):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1" if mono else "2",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).copy()
    return x if mono else x.reshape(-1, 2)


class Bus:
    def __init__(self, n):
        self.n = n
        self.buf = np.zeros((n, 2))

    def add(self, sig, t0, gain=1.0, pan=0.0):
        """Mix mono/stereo sig at t0 seconds with constant-power pan (-1..1)."""
        if sig.ndim == 1:
            a = (pan + 1) * np.pi / 4
            sig = np.stack([sig * np.cos(a), sig * np.sin(a)], 1)
        i = int(round(t0 * SR))
        if i < 0:
            sig, i = sig[-i:], 0
        m = min(len(sig), self.n - i)
        if m > 0:
            self.buf[i:i + m] += sig[:m] * gain


def env(points, n):
    ts, gs = zip(*points)
    return np.interp(tt(n), ts, gs)


def mode_points(p, n_total):
    """[(time, mode)] from edit.json music.modes, first entry forced to t=0."""
    modes = [(p.t(m["from"]), m["mode"]) for m in p.cfg.get("music", {}).get("modes", [])] or [(0, "groove")]
    modes.sort()
    modes[0] = (0.0, modes[0][1])
    for _, m in modes:
        if m not in LEVELS:
            raise SystemExit(f"Unknown music mode {m!r}; use one of {list(LEVELS)}")
    return modes


def automation(modes, key, table, n):
    pts = [(0.0, table[modes[0][1]][key] if isinstance(table[modes[0][1]], dict) else table[modes[0][1]])]
    for tc, m in modes[1:]:
        v = table[m][key] if isinstance(table[m], dict) else table[m]
        pts += [(tc - 0.05, pts[-1][1]), (tc, v)]
    pts.append((n / SR + 1, pts[-1][1]))
    return env(pts, n)


def tape_stops(music, modes):
    for tc, m in modes:
        if m != "stop":
            continue
        i0, i1 = int((tc - 0.45) * SR), int(tc * SR)
        rate = np.linspace(1, 0, i1 - i0) ** 1.3
        pos = i0 + np.cumsum(rate)
        for c in range(2):
            music[i0:i1, c] = np.interp(pos, np.arange(len(music)), music[:, c]) * np.linspace(1, 0.2, i1 - i0)
    return music


def synth_music(p, n):
    mc = p.cfg.get("music", {})
    beat = 60 / mc.get("bpm", 100)
    bar = 4 * beat
    root = NOTES.index(FLATS.get(mc.get("root", "D"), mc.get("root", "D")))
    prog = [(0, (0, 3, 7)), (8, (0, 4, 7)), (3, (0, 4, 7)), (10, (0, 4, 7))]   # i VI III VII
    if mc.get("scale") == "major":
        prog = [(0, (0, 4, 7)), (7, (0, 4, 7)), (9, (0, 3, 7)), (5, (0, 4, 7))]  # I V vi IV

    def hz(semi, octv):
        return 440 * 2 ** ((semi - 9) / 12 + octv - 4)

    def saw(f, m):
        return 2 * ((f * tt(m)) % 1.0) - 1

    pad, bass, arp, arp_hi = (np.zeros(n) for _ in range(4))
    for b in range(int(np.ceil(n / SR / bar))):
        deg, tri = prog[b % 4]
        notes = [root + deg + x for x in tri]
        t0 = b * bar
        m = int((bar + 0.6) * SR)
        e = np.minimum(1, tt(m) / 0.35) * np.clip((bar + 0.6 - tt(m)) / 0.6, 0, 1)
        v = sum(saw(hz(nt, 3) * 2 ** (d / 1200), m) for nt in notes for d in (-8, 0, 8)) * e
        i = int(t0 * SR); k = min(m, n - i)
        pad[i:i + k] += v[:k]
        for s8 in range(8):
            tn = t0 + s8 * beat / 2
            nb = int(0.3 * SR); f = hz(root + deg, 2)
            x = (np.sin(2 * np.pi * f * tt(nb)) + 0.35 * np.sin(4 * np.pi * f * tt(nb))) * np.exp(-tt(nb) / 0.16)
            x *= np.minimum(1, tt(nb) / 0.005)
            j = int(tn * SR); k = min(nb, n - j)
            if k > 0:
                bass[j:j + k] += np.tanh(1.5 * x[:k])
            idx = [0, 1, 2, 1, 0, 2, 1, 2][s8]
            for octv, tgt in ((4, arp), (5, arp_hi)):
                f = hz(notes[idx], octv + (1 if idx == 0 and s8 == 4 else 0))
                na = int(0.5 * SR)
                x = (np.sin(2 * np.pi * f * tt(na)) * np.exp(-tt(na) / 0.18)
                     + 0.25 * np.sin(2 * np.pi * 4 * f * tt(na)) * np.exp(-tt(na) / 0.03)) * np.minimum(1, tt(na) / 0.002)
                k = min(na, n - j)
                if k > 0:
                    tgt[j:j + k] += x[:k] * (1.0 if s8 % 2 == 0 else 0.7)
    pad = filt(pad, "lowpass", 1400) / 9

    kick, hats, heart = np.zeros(n), np.zeros(n), np.zeros(n)
    nk = int(0.45 * SR)
    ph = 2 * np.pi * np.cumsum(45 + 85 * np.exp(-tt(nk) / 0.04)) / SR
    KICK = np.sin(ph) * np.exp(-tt(nk) / 0.22) + 0.3 * filt(rng.standard_normal(nk), "highpass", 3000) * np.exp(-tt(nk) / 0.004)
    HEART = filt(KICK, "lowpass", 180)
    nh = int(0.08 * SR)
    HAT = filt(rng.standard_normal(nh), "highpass", 7000) * np.exp(-tt(nh) / 0.02)
    for k in range(int(n / SR / beat)):
        t0 = k * beat
        j = int(t0 * SR); m = min(nk, n - j)
        if m > 0:
            kick[j:j + m] += KICK[:m] * (1.0 if k % 2 == 0 else 0.8)
        for s in range(4):
            js = int((t0 + s * beat / 4) * SR); ms = min(nh, n - js)
            if ms > 0:
                hats[js:js + ms] += HAT[:ms] * (0.9 if s == 2 else 0.45)
        if k % 2 == 0:
            for off, a in ((0, 1.0), (0.22, 0.7)):
                jh = int((t0 + off) * SR); mh = min(nk, n - jh)
                if mh > 0:
                    heart[jh:jh + mh] += HEART[:mh] * a
    T = tt(n)
    drone = (np.sin(2 * np.pi * hz(root, 1) * T) + 0.6 * np.sin(2 * np.pi * hz(root, 2) * T * 1.002)
             + 0.25 * np.sin(2 * np.pi * hz(root + 7, 2) * T)) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * T))
    air = filt(rng.standard_normal(n), "bandpass", [200, 900]) * 0.6

    modes = mode_points(p, n)
    A = {k: automation(modes, k, LEVELS, n) for k in ("pad", "groove", "hat16", "tick", "mystery", "bright")}
    mono = (pad * A["pad"] * 0.9
            + A["groove"] * (0.55 * bass + 0.55 * kick + 0.10 * hats * (0.5 + 0.5 * A["hat16"]) + 0.22 * arp)
            + 0.14 * hats * A["tick"]
            + A["mystery"] * (0.35 * drone + 0.42 * heart + 0.05 * air + 0.10 * arp)
            + A["bright"] * 0.18 * arp_hi)
    wide = 0.04 * filt(pad, "highpass", 300) * A["pad"]
    music = np.stack([mono + wide + A["bright"] * 0.05 * arp_hi, mono - wide + A["groove"] * 0.04 * arp], 1)
    return tape_stops(music, modes)


def file_music(p, n, path):
    x = load(path)
    reps = int(np.ceil(n / len(x)))
    x = np.tile(x, (reps, 1))[:n]
    modes = mode_points(p, n)
    x = x * automation(modes, None, FILE_LEVEL, n)[:, None]
    return tape_stops(x, modes)


# ---------------------------------------------------------------- sound effects
class Sfx:
    def __init__(self, p, n):
        self.p, self.bus = p, Bus(n)
        lib = p.cfg.get("sfx_library") or {}
        self.lib_dir = Path(lib.get("dir", ".")).expanduser()
        if not self.lib_dir.is_absolute():
            self.lib_dir = (p.proj / self.lib_dir).resolve()
        self.lib = lib
        self.cache, self.rot = {}, {}

    def lib_file(self, kind, explicit=None):
        name = explicit or self.lib.get(kind)
        if not name:
            return None
        if isinstance(name, list):
            k = self.rot.get(kind, 0); self.rot[kind] = k + 1
            name = name[k % len(name)]
        path = Path(name).expanduser()
        if not path.is_absolute():
            path = self.lib_dir / name
        if not path.exists():
            print(f"  ! sfx file missing, using synth: {path}")
            return None
        if path not in self.cache:
            x = load(path)
            self.cache[path] = x / (np.abs(x).max() + 1e-9)
        return self.cache[path]

    def place_file(self, x, t, align, gain, length=None):
        if length:
            m = int(length * SR)
            x = x[:m].copy()
            fade = min(len(x), int(0.15 * SR))
            x[-fade:] *= np.linspace(1, 0, fade)[:, None]
        mag = np.abs(x).max(1)
        if align == "peak":
            off = int(np.argmax(mag))
        elif align == "end":
            off = len(x)
        else:  # onset
            off = int(np.argmax(mag > 0.1))
        self.bus.add(x, t - off / SR, gain)

    # synth fallbacks
    def whoosh(self, t_mid, gain=0.55, direction=1, dur=0.45):
        n = int(dur * SR)
        x = rng.standard_normal(n)
        k = np.linspace(0, 1, n)
        sig = (filt(x, "bandpass", [300, 1500]) * (1 - k) + filt(x, "bandpass", [1500, 6000]) * k) * np.exp(-((k - 0.55) / 0.2) ** 2)
        a = (np.linspace(-0.8, 0.8, n) * direction + 1) * np.pi / 4
        self.bus.add(np.stack([sig * np.cos(a), sig * np.sin(a)], 1), t_mid - 0.55 * dur, gain)

    def boom(self, t0, gain=1.0, length=1.6):
        n = int(length * SR)
        ph = 2 * np.pi * np.cumsum(38 + 70 * np.exp(-tt(n) / 0.06)) / SR
        body = np.sin(ph) * np.exp(-tt(n) / 0.45)
        crack = filt(rng.standard_normal(n), "lowpass", 2500) * np.exp(-tt(n) / 0.05)
        self.bus.add(reverb(np.tanh(1.8 * (body + 0.5 * crack)), 1.4, 0.3), t0, gain)

    def thud(self, t0, gain=0.9):
        n = int(0.9 * SR)
        ph = 2 * np.pi * np.cumsum(32 + 55 * np.exp(-tt(n) / 0.05)) / SR
        rumble = filt(rng.standard_normal(n), "lowpass", 260) * np.exp(-tt(n) / 0.25)
        self.bus.add(np.tanh(2 * (np.sin(ph) * np.exp(-tt(n) / 0.3) + 0.8 * rumble)), t0, gain)

    def pop(self, t0, gain=0.4, f0=600):
        n = int(0.12 * SR)
        f = f0 + f0 * (1 - np.exp(-tt(n) / 0.02))
        self.bus.add(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt(n) / 0.035), t0, gain)

    def shutter(self, t0, gain=0.6):
        for off, a in ((0, 1.0), (0.075, 0.8)):
            n = int(0.03 * SR)
            s = filt(rng.standard_normal(n), "bandpass", [1800, 7000]) * np.exp(-tt(n) / 0.006)
            s += 0.6 * np.sin(2 * np.pi * 180 * tt(n)) * np.exp(-tt(n) / 0.01)
            self.bus.add(s, t0 + off, gain * a)

    def ding(self, t0, gain=0.3, f=1567.98):
        n = int(1.2 * SR)
        s = (np.sin(2 * np.pi * f * tt(n)) + 0.4 * np.sin(2 * np.pi * 2.76 * f * tt(n)) * np.exp(-tt(n) / 0.15)
             + 0.2 * np.sin(2 * np.pi * 5.4 * f * tt(n)) * np.exp(-tt(n) / 0.05)) * np.exp(-tt(n) / 0.35)
        self.bus.add(reverb(s * np.minimum(1, tt(n) / 0.002), 0.8, 0.2), t0, gain)

    def riser(self, t0, t1, gain=0.45):
        n = int((t1 - t0) * SR)
        k = np.linspace(0, 1, n)
        x = rng.standard_normal(n)
        bands = [filt(x, "bandpass", [f, f * 2]) for f in (250, 500, 1000, 2000, 4000)]
        sig = sum(b * np.clip(1 - np.abs(k * 4 - j), 0, 1) for j, b in enumerate(bands))
        sig = sig + 0.35 * np.sin(2 * np.pi * np.cumsum(180 * 2 ** (2.5 * k)) / SR) * k
        self.bus.add(sig * k ** 2, t0, gain)

    def scrape(self, t0, t1, style="brush", gain=None):
        band, stroke, g = ((1800, 5000), 0.28, 0.18) if style == "brush" else ((3000, 8000), 0.16, 0.12)
        t = t0
        while t < t1:
            n = int(stroke * SR)
            e = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
            self.bus.add(filt(rng.standard_normal(n), "bandpass", list(band)) * e, t, gain or g, pan=rng.uniform(-0.3, 0.3))
            t += stroke + rng.uniform(0.04, 0.12)

    # library-aware entry points
    def hit(self, kind, t, gain, **kw):
        x = self.lib_file(kind, kw.get("file"))
        if x is not None:
            align = kw.get("align", "peak" if kind in ("whoosh", "riser") else "onset")
            if kind == "riser" and "to" in kw:
                t = kw["to"]
            self.place_file(x, t, align, gain, kw.get("length"))
            return
        if kind == "whoosh":
            self.whoosh(t, gain, kw.get("direction", 1))
        elif kind == "boom":
            self.boom(t, gain, kw.get("length") or 1.6)
        elif kind == "riser":
            self.riser(kw.get("from", t - 1.5), kw.get("to", t), gain)
        else:
            getattr(self, kind)(t, gain)


def build_sfx(p, n):
    s = Sfx(p, n)
    if p.cfg.get("auto_sfx", True):
        s.hit("boom", 0.0, 1.0)
        for k in range(1, len(p.scenes)):
            s.hit("whoosh", p.T[k] - p.xf / 2, 0.55, direction=1 if k % 2 else -1)
        for e in p.events():
            kind = e["kind"]
            if kind == "card":
                s.hit("shutter", e["t_in"], 0.6)
            elif kind == "map":
                s.ding(e["t_in"], 0.3, 1318.5 if e.get("chime") == "low" else 1567.98)
            elif kind in ("stamp", "strike", "warn"):
                s.pop(e["t_in"], 0.4, 600 if e.get("color", "yellow") == "yellow" else 380)
                if kind == "strike" and "strike_at" in e:
                    s.pop(e["strike_at"], 0.45, 300)
            elif kind == "endlogo":
                s.pop(e["t_in"] + 0.02, 0.5, 700)
                s.ding(e["t_in"] + 0.05, 0.35, 2093.0)
                s.shutter(e["t_in"] + 0.45, 0.35)
    for x in p.cfg.get("sfx", []):
        typ, gain = x["type"], x.get("gain")
        kw = {k: v for k, v in x.items() if k in ("file", "align", "length", "direction")}
        if typ == "file":
            path = s.lib_file("custom", x["file"])
            if path is not None:
                s.place_file(path, p.t(x["at"]), x.get("align", "onset"), gain or 0.6, x.get("length"))
        elif typ == "riser":
            s.hit("riser", p.t(x["to"]), gain or 0.45, **kw, **{"from": p.t(x["from"]), "to": p.t(x["to"])})
        elif typ == "scrape":
            s.scrape(p.t(x["from"]), p.t(x["to"]), x.get("style", "brush"), gain)
        elif typ in ("boom", "whoosh", "thud", "pop", "shutter", "ding"):
            s.hit(typ, p.t(x["at"]), gain or dict(boom=0.7, whoosh=0.55, thud=0.9, pop=0.4, shutter=0.6, ding=0.3)[typ], **kw)
        else:
            raise SystemExit(f"Unknown sfx type {typ!r}")
    buf = s.bus.buf
    return buf / max(1.0, np.abs(buf).max())


def build_vo(p, n):
    bus = Bus(n)
    for i, sc in enumerate(p.scenes):
        a = p.an["scenes"][str(sc["n"])]
        x = load(p.proj / "sound" / f"{sc['n']}.mp3", mono=True)
        x = x[int(a["trim_start"] * SR): int((a["trim_start"] + a["speech_end"] + 0.12) * SR)].copy()
        f = int(0.06 * SR)
        x[-f:] *= np.linspace(1, 0, f)
        bus.add(x, p.T[i])
    return bus.buf


def run(p):
    n = int((p.total + 0.6) * SR)
    mc = p.cfg.get("music", {})
    if mc.get("file"):
        music = file_music(p, n, (p.proj / mc["file"]).resolve())
    else:
        music = synth_music(p, n)
    fade = int(0.6 * SR)
    music[-fade:] *= np.linspace(1, 0, fade)[:, None]
    music /= np.abs(music).max() + 1e-9
    sfx, vo = build_sfx(p, n), build_vo(p, n)
    for name, buf in (("music", music), ("sfx", sfx), ("vo", vo)):
        wavfile.write(p.work / f"{name}.wav", SR, (buf * 0.89).astype(np.float32))
    mix = p.cfg.get("mix", {})
    w = p.work
    graph = (f"[0]loudnorm=I={mix.get('vo_lufs', -16)}:TP=-2:LRA=7,asplit[v1][v2];"
             f"[1]volume={mix.get('music_db', -9)}dB[m];"
             f"[m][v2]sidechaincompress=threshold=0.02:ratio=5:attack=15:release=350[md];"
             f"[2]volume={mix.get('sfx_db', -5)}dB[s];"
             f"[v1][md][s]amix=inputs=3:normalize=0,alimiter=limit=0.95,"
             f"loudnorm=I={mix.get('final_lufs', -14)}:TP=-1.5:LRA=11[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w / "vo.wav"), "-i", str(w / "music.wav"),
                    "-i", str(w / "sfx.wav"), "-filter_complex", graph, "-map", "[a]", "-ar", str(SR),
                    str(w / "mix.wav")], check=True)
