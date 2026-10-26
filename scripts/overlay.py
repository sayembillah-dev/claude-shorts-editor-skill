"""Step 4: composite hook, captions, stamps, photo/map cards, logo and camera moves over base.mp4, encode with mix.wav."""
import math, re, subprocess
import numpy as np
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from common import font_path

YELLOW, RED, GREEN, WHITE, BLACK = (255, 214, 10), (255, 59, 48), (40, 200, 90), (255, 255, 255), (0, 0, 0)
BLUE, ORANGE = (10, 132, 255), (255, 159, 10)
PILL = {"yellow": (YELLOW, BLACK), "green": (GREEN, WHITE), "red": (RED, WHITE), "white": (WHITE, BLACK),
        "blue": (BLUE, WHITE), "orange": (ORANGE, BLACK)}
TEXT = {"yellow": YELLOW, "red": RED, "green": GREEN, "white": WHITE, "blue": BLUE, "orange": ORANGE}
FONT = None


@lru_cache(None)
def font(size):
    return ImageFont.truetype(FONT, size)


def back(x):  # easeOutBack
    c1 = 1.70158
    x = min(max(x, 0), 1)
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease(x):
    x = min(max(x, 0), 1)
    return 1 - (1 - x) ** 3


def with_shadow(img, off=(0, 10), blur=14, alpha=150):
    pad = blur * 3
    canvas = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 255))
    sh.putalpha(img.getchannel("A").point(lambda v: v * alpha // 255))
    canvas.paste(sh, (pad + off[0], pad + off[1]), sh)
    canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(img, (pad, pad))
    return canvas


def text_img(text, size, fill, stroke=10):
    f = font(size)
    l, t, r, b = f.getbbox(text, stroke_width=stroke)
    img = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 - l, 2 - t), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=BLACK)
    return img


def fit_text(text, size, fill, max_w, stroke_div=11):
    while True:
        img = text_img(text, size, fill, max(6, size // stroke_div))
        if img.width <= max_w or size < 40:
            return img
        size -= 4


def rounded(img, radius):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius, fill=255)
    img = img.convert("RGBA")
    img.putalpha(m)
    return img


def pill(text, color, size=62, rot=-3, max_w=1000):
    bg, fg = PILL[color]
    while True:
        f = font(size)
        l, t, r, b = f.getbbox(text)
        if r - l + 80 <= max_w or size < 30:
            break
        size -= 4
    pw, ph = 40, 22
    w, h = r - l + 2 * pw, b - t + 2 * ph
    img = Image.new("RGBA", (w + 12, h + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, w + 5, h + 5], 26, fill=bg, outline=BLACK, width=6)
    d.text((6 + pw - l, 6 + ph - t), text, font=f, fill=fg)
    return with_shadow(img, blur=10).rotate(rot, Image.BICUBIC, expand=True)


def place(frame, img, cx, cy, scale=1.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    if abs(scale - 1) > 0.005:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BILINEAR)
    if alpha < 0.995:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    x, y = int(cx - img.width / 2), int(cy - img.height / 2)
    if x >= 0 and y >= 0 and x + img.width <= frame.width and y + img.height <= frame.height:
        frame.alpha_composite(img, (x, y))
    else:
        frame.paste(img, (x, y), img)


def life(t, t_in, t_out, tin=0.25, tout=0.14):
    """(scale, alpha) for a pop-in / shrink-out element, or None when hidden."""
    if t < t_in or t >= t_out:
        return None
    s = back((t - t_in) / tin) if tin else 1.0
    a = min(1.0, (t - t_in) / 0.06)
    if t > t_out - tout:
        k = (t_out - t) / tout
        s *= 0.85 + 0.15 * k
        a *= k
    return s, a


class Renderer:
    def __init__(self, p):
        global FONT
        FONT = font_path(p.cfg)
        self.p, c = p, p.cfg
        self.W, self.H = p.W, p.H
        lay = c.get("layout", {})
        self.stamp_y = lay.get("stamp_y", [375, 515])
        self.card_y = lay.get("card_y", 800)
        self.cap_y = lay.get("caption_y", 1290)
        self.hook_y = lay.get("hook_y", 330)
        self.end_logo_y = lay.get("end_logo_y", 255)
        self.events = p.events()
        self.punches = p.punches()

        logo = p.proj / c.get("logo", "logo.png")
        self.logo_small = self.logo_big = None
        if logo.exists():
            src = Image.open(logo).convert("RGBA")
            if c.get("watermark", True):
                self.logo_small = with_shadow(rounded(src.resize((118, 118), Image.LANCZOS), 26), blur=8, alpha=120)
            self.logo_big = with_shadow(rounded(src.resize((290, 290), Image.LANCZOS), 58), blur=18)

        self.assets, tilt = {}, -3
        for e in self.events:
            k = e["kind"]
            if k == "card" and e["image"] not in self.assets:
                self.assets[e["image"]] = self.make_card(e["image"], e.get("tilt", tilt), e.get("label", "REAL PHOTO"))
                tilt = -tilt
            elif k == "map" and e["image"] not in self.assets:
                self.assets[e["image"]] = self.make_map(e["image"])
            elif k in ("stamp", "strike", "warn"):
                row = e.get("row", 2 if k == "warn" else 1)
                color = e.get("color", {"warn": "red", "strike": "white"}.get(k, "yellow"))
                key = ("pill", e["text"], color, row)
                if key not in self.assets:
                    self.assets[key] = pill(e["text"], color, 62 if row == 1 else 50, -3 if row == 1 else 2)
                e["_key"] = key
            elif k == "hook":
                self.hook = self.make_hook(e)
        hook_ev = [e for e in self.events if e["kind"] == "hook"]
        self.grad = None
        if hook_ev:
            g = Image.new("RGBA", (self.W, 900), (0, 0, 0, 0))
            g.putalpha(Image.fromarray(np.linspace(170, 0, 900)[:, None].repeat(self.W, 1).astype(np.uint8)))
            self.grad = g
        self.build_captions()

    # ---- assets
    def make_card(self, name, rot, label):
        ph = Image.open(self.p.proj / name).convert("RGBA")
        side = 690
        ph.thumbnail((side, side), Image.LANCZOS)
        card = Image.new("RGBA", (ph.width + 32, ph.height + 32), WHITE + (255,))
        card.paste(ph, (16, 16))
        card = rounded(card, 22)
        big = Image.new("RGBA", (card.width + 60, card.height + 60), (0, 0, 0, 0))
        big.alpha_composite(card, (30, 30))
        if label:
            big.alpha_composite(pill(label, "red", 40, 0), (0, 0))
        return with_shadow(big, blur=18).rotate(rot, Image.BICUBIC, expand=True)

    def make_map(self, name):
        m = Image.open(self.p.proj / name).convert("RGBA")
        m.thumbnail((600, 600), Image.LANCZOS)
        card = Image.new("RGBA", (640, 640), (255, 246, 229, 255))
        card.alpha_composite(m, ((640 - m.width) // 2, (640 - m.height) // 2))
        ImageDraw.Draw(card).rounded_rectangle([0, 0, 639, 639], 36, outline=(30, 30, 30), width=8)
        return with_shadow(rounded(card, 36), blur=16)

    def make_hook(self, e):
        lines, hi = e["lines"], e.get("highlight", 1)
        imgs = []
        for j, line in enumerate(lines):
            if j == hi:
                size, col = 138, YELLOW
            elif j == hi - 1:
                size, col = 74, WHITE
            else:
                size, col = 104, WHITE
            imgs.append(with_shadow(fit_text(line, size, col, 1000), blur=10))
        ys, y = [], self.hook_y
        for j, im in enumerate(imgs):
            if j:
                y += (imgs[j - 1].height + im.height) / 2 - 62
            ys.append(y)
        return list(zip(imgs, ys))

    # ---- captions
    def build_captions(self):
        cc = self.p.cfg.get("captions", {})
        self.cap_on = cc.get("enabled", True)
        max_words, max_chars = cc.get("max_words", 3), cc.get("max_chars", 15)
        self.cap_size = cc.get("size", 84)
        self.colors = self.p.caption_colors()
        chunks, cur = [], []
        for w in self.p.words:
            w = dict(w, text=w["text"].upper())
            if cur and (len(cur) == max_words or len(" ".join(x["text"] for x in cur)) + len(w["text"]) > max_chars
                        or re.search(r"[.,?!]$", cur[-1]["text"]) or cur[-1]["scene"] != w["scene"]):
                chunks.append(cur)
                cur = []
            cur.append(w)
        if cur:
            chunks.append(cur)
        for k, c in enumerate(chunks):
            nxt = chunks[k + 1][0]["start"] if k + 1 < len(chunks) else self.p.total
            end = c[-1]["end"] + 0.25
            c[0]["chunk_end"] = nxt if nxt - c[-1]["end"] < 0.45 else min(end, nxt)
        self.chunks = chunks

    @lru_cache(None)
    def caption_img(self, k, active):
        c = self.chunks[k]
        size = self.cap_size
        parts = [w["text"] if w["text"].endswith("?") else w["text"].rstrip(",.") for w in c]
        while True:
            sw = max(8, size // 8)
            sizes = [int(size * 1.12) if i == active else size for i in range(len(c))]
            widths = [font(s).getlength(t) + 2 * sw for t, s in zip(parts, sizes)]
            total = sum(widths) + 22 * (len(c) - 1)
            if total <= self.W - 80 or size < 50:
                break
            size -= 4
        hgt = int(size * 1.12 * 1.25) + 2 * sw
        img = Image.new("RGBA", (int(total) + 10, hgt + 10), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = 5
        for i, (t, s, wd) in enumerate(zip(parts, sizes, widths)):
            col = WHITE
            if i == active:
                col = TEXT.get(self.colors.get((c[i]["scene"], c[i]["k"])), YELLOW)
            d.text((x + sw, hgt - int(size * 0.28)), t, font=font(s), fill=col, anchor="ls", stroke_width=sw, stroke_fill=BLACK)
            x += wd + 22
        return with_shadow(img, off=(0, 8), blur=8, alpha=170)

    def caption_at(self, t):
        for k, c in enumerate(self.chunks):
            if c[0]["start"] <= t < c[0]["chunk_end"]:
                active = max(i for i, w in enumerate(c) if t >= w["start"] or i == 0)
                return k, active, t - c[0]["start"]
        return None

    # ---- camera
    def camera(self, t):
        p = self.p
        i = max(k for k in range(len(p.T)) if p.T[k] <= t + 1e-6)
        z = 1.0 + p.scenes[i].get("push", 0.035) * (t - p.T[i]) / p.D[i]
        dx = dy = 0.0
        for tp, s, sh in self.punches:
            if tp <= t < tp + 1.2:
                u = t - tp
                z *= 1 + s * min(1, u / 0.05) * math.exp(-max(0, u - 0.05) / 0.35)
                if sh and u < 0.45:
                    amp = 16 * sh * math.exp(-u / 0.14)
                    dx += amp * math.sin(u * 97)
                    dy += amp * math.cos(u * 83)
        return z, dx, dy

    def apply_camera(self, img, t):
        z, dx, dy = self.camera(t)
        if z < 1.001 and not dx and not dy:
            return img
        z = max(z, 1.0 + (abs(dx) + abs(dy)) * 2 / self.W + 0.002)
        w, h = self.W / z, self.H / z
        x0 = min(max(self.W / 2 + dx - w / 2, 0), self.W - w)
        y0 = min(max(self.H / 2 + dy - h / 2, 0), self.H - h)
        return img.resize((self.W, self.H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))

    # ---- per frame
    def draw(self, frame, t):
        W = self.W
        for e in self.events:
            kind, t_in, t_out = e["kind"], e["t_in"], e["t_out"]
            if not (t_in <= t < t_out):
                continue
            if kind == "hook":
                fade = 1 - max(0, (t - (t_out - 0.12)) / 0.12)
                place(frame, self.grad, W / 2, 450, 1, fade)
                for j, (img, y) in enumerate(self.hook):
                    lf = life(t, t_in - 0.3 + 0.06 * j, t_out, 0.3, 0.12)  # already on screen at frame one
                    if lf:
                        place(frame, img, W / 2, y, lf[0], lf[1])
            elif kind == "card":
                lf = life(t, t_in, t_out, 0.3, 0.15)
                if lf:
                    rise = (1 - ease((t - t_in) / 0.3)) * 260
                    place(frame, self.assets[e["image"]], W / 2, e.get("y", self.card_y) + rise,
                          lf[0] * (1 + 0.03 * (t - t_in)), lf[1])
                    if t - t_in < 0.16:  # camera flash
                        frame.alpha_composite(Image.new("RGBA", frame.size, (255, 255, 255, int(150 * (1 - (t - t_in) / 0.16)))))
            elif kind == "map":
                lf = life(t, t_in, t_out, 0.28, 0.12)
                if lf:
                    cy = e.get("y", self.card_y)
                    place(frame, self.assets[e["image"]], W / 2, cy, lf[0], lf[1])
                    if e.get("pin") and lf[0] > 0.97 and t - t_in > 0.2:
                        fx, fy = e["pin"]
                        px, py = W / 2 - 300 + fx * 600, cy - 300 + fy * 600
                        u = ((t - t_in - 0.2) % 0.9) / 0.9
                        r = 14 + 46 * u
                        ring = Image.new("RGBA", (130, 130), (0, 0, 0, 0))
                        d = ImageDraw.Draw(ring)
                        d.ellipse([65 - r, 65 - r, 65 + r, 65 + r], outline=RED + (int(255 * (1 - u) * lf[1]),), width=7)
                        d.ellipse([53, 53, 77, 77], fill=RED + (int(255 * lf[1]),), outline=WHITE, width=4)
                        frame.alpha_composite(ring, (int(px - 65), int(py - 65)))
            elif kind in ("stamp", "strike", "warn"):
                lf = life(t, t_in, t_out, 0.22, 0.12)
                if lf:
                    img = self.assets[e["_key"]]
                    y = self.stamp_y[e["_key"][3] - 1]
                    if "wobble_at" in e and e["wobble_at"] <= t < e["wobble_at"] + 0.5:
                        u = t - e["wobble_at"]
                        img = img.rotate(9 * math.sin(u * 40) * math.exp(-u / 0.15), Image.BICUBIC, expand=True)
                    place(frame, img, W / 2, y, lf[0], lf[1])
                    if kind == "strike" and t >= e.get("strike_at", t_in + 0.6):
                        q = ease((t - e.get("strike_at", t_in + 0.6)) / 0.15)
                        x0, x1 = W / 2 - img.width / 2 + 30, W / 2 + img.width / 2 - 30
                        ImageDraw.Draw(frame).line([(x0, y + 18), (x0 + (x1 - x0) * q, y - 18)],
                                                   fill=RED + (int(255 * lf[1]),), width=16)
            elif kind == "endlogo" and self.logo_big:
                lf = life(t, t_in, t_out + 1, 0.35, 0.01)
                if lf:
                    place(frame, self.logo_big, W / 2, self.end_logo_y + 10 * math.sin((t - t_in) * 3.2), lf[0], lf[1])
        end_logo_t = next((e["t_in"] for e in self.events if e["kind"] == "endlogo"), self.p.total + 1)
        if self.logo_small and t < end_logo_t:
            place(frame, self.logo_small, 40 + self.logo_small.width / 2 - 24, 160, 1, 0.92)
        cap = self.caption_at(t) if self.cap_on else None
        if cap:
            k, active, age = cap
            place(frame, self.caption_img(k, active), W / 2, self.cap_y, 0.82 + 0.18 * back(age / 0.14), min(1, age / 0.05))


def run(p, out=None, times=None, outdir=None):
    r = Renderer(p)
    W, H = p.W, p.H
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(p.work / "base.mp4"), "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    enc, want, saved = None, None, []
    if times:
        want = {int(round(x * p.fps)): x for x in times}
    else:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", str(p.fps), "-i", "-", "-i", str(p.work / "mix.wav"),
                                "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                                "-profile:v", "high", "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                                "-shortest", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    n, sz = 0, W * H * 3
    while True:
        buf = dec.stdout.read(sz)
        if len(buf) < sz:
            break
        t = n / p.fps
        if want is None or n in want:
            img = r.apply_camera(Image.frombuffer("RGB", (W, H), buf), t).convert("RGBA")
            r.draw(img, t)
            if want is not None:
                path = outdir / f"f_{t:07.2f}.jpg"
                img.convert("RGB").save(path, quality=85)
                saved.append(path)
            else:
                enc.stdin.write(img.convert("RGB").tobytes())
        n += 1
        if want is not None and n > max(want):
            break
    dec.stdout.close()
    dec.terminate()
    if enc:
        enc.stdin.close()
        enc.wait()
    return saved
