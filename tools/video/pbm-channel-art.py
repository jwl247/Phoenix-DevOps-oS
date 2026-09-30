#!/usr/bin/env python3
"""PBM Consulting Service channel art: YouTube banner + profile picture.

UnitedSys — United Systems | jwl247 | GPL-3.0

Brand from pbm-consulting-website (styles.css): manila paper, forest, oxblood,
brass; Fraunces for headings, IBM Plex Sans for text; the oxblood stamp is the
mark. Fonts (OFL) are fetched from google/fonts into FONTS below.

  python tools/video/pbm-channel-art.py [--out DIR]
    banner.png   2560x1440, everything that matters inside YouTube's 1546x423
                 safe area (what phones show); the rest shows on TVs/desktop
    profile.png  800x800, the stamp (YouTube crops it to a circle)
"""
import argparse
import math
import os

from PIL import Image, ImageDraw, ImageFont

FONTS = r"E:\Phoenix\video\brand\fonts"
PAPER, PAPER_DARK, INK = "#EFEAD9", "#E4DDC6", "#2B2620"
FOREST, OXBLOOD, BRASS, LINE = "#1F3D2B", "#8C2F1B", "#A6832E", "#CFC6A8"

NAME = "PBM Consulting Service"
TAGLINE = "Steel buildings, federal set-asides, and the software behind them."
STAMP_TOP, STAMP_BOTTOM, STAMP_CENTER = "PBM CONSULTING SERVICE", "GUTHRIE, OKLAHOMA", "PBM"


def fraunces(size, weight=600):
    f = ImageFont.truetype(os.path.join(FONTS, "Fraunces[SOFT,WONK,opsz,wght].ttf"), size)
    f.set_variation_by_axes([min(144, max(9, size)), weight, 0, 0])      # opsz, wght, SOFT, WONK
    return f


def plex(size, weight=500):
    f = ImageFont.truetype(os.path.join(FONTS, "IBMPlexSans[wdth,wght].ttf"), size)
    f.set_variation_by_axes([weight, 100])                               # wght, wdth
    return f


def arc_text(img, text, cx, cy, r, font, fill, top=True, spacing=4):
    """Letters around a circle: along the top reading left to right, or along
    the bottom reading left to right (upright), like a rubber stamp."""
    d = ImageDraw.Draw(img)
    widths = [d.textlength(ch, font=font) + spacing for ch in text]
    total = sum(widths) - spacing
    angle_span = total / r
    a = -math.pi / 2 - angle_span / 2 if top else math.pi / 2 + angle_span / 2
    for ch, w in zip(text, widths):
        step = w / r
        mid = a + step / 2 if top else a - step / 2
        x, y = cx + r * math.cos(mid), cy + r * math.sin(mid)
        tile = Image.new("RGBA", (int(font.size * 2), int(font.size * 2)), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((font.size, font.size), ch, font=font, fill=fill, anchor="mm")
        rot = -math.degrees(mid) - 90 if top else -math.degrees(mid) + 90
        tile = tile.rotate(rot, resample=Image.BICUBIC)
        img.alpha_composite(tile, (int(x - tile.width / 2), int(y - tile.height / 2)))
        a = a + step if top else a - step


def star(d, cx, cy, r, fill):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def stamp(size, bg=PAPER, ink=OXBLOOD):
    """The PBM stamp. Oxblood on paper for the profile picture; paper on forest in the banner."""
    img = Image.new("RGBA", (size, size), bg)
    d = ImageDraw.Draw(img)
    c, s = size / 2, size / 800
    d.ellipse([c - 368 * s, c - 368 * s, c + 368 * s, c + 368 * s], outline=ink, width=round(14 * s))
    d.ellipse([c - 300 * s, c - 300 * s, c + 300 * s, c + 300 * s], outline=ink, width=round(6 * s))
    ring = plex(round(46 * s), 600)
    arc_text(img, STAMP_TOP, c, c, 334 * s, ring, ink, top=True, spacing=round(7 * s))
    arc_text(img, STAMP_BOTTOM, c, c, 334 * s, ring, ink, top=False, spacing=round(7 * s))
    for side in (-1, 1):             # drawn, not a glyph: IBM Plex has no star character (it came out a box)
        star(d, c + side * 334 * s, c, 17 * s, ink)
    d.text((c, c - 6 * s), STAMP_CENTER, font=fraunces(round(230 * s), 700), fill=ink, anchor="mm")
    d.line([c - 150 * s, c + 118 * s, c + 150 * s, c + 118 * s], fill=ink, width=round(5 * s))
    d.text((c, c + 165 * s), "EST. 2026", font=plex(round(40 * s), 600), fill=ink, anchor="mm")
    return img


def banner():
    W, H = 2560, 1440
    img = Image.new("RGBA", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    for y in range(40, H, 40):                                            # ledger-paper rules (TV/desktop only)
        d.line([0, y, W, y], fill=PAPER_DARK, width=2)
    band_top, band_bot = 470, 970                                         # safe area is y 508..932
    d.rectangle([0, band_top, W, band_bot], fill=FOREST)
    d.line([0, band_top - 14, W, band_top - 14], fill=BRASS, width=4)
    d.line([0, band_bot + 14, W, band_bot + 14], fill=BRASS, width=4)
    st = stamp(280, bg=FOREST, ink=PAPER)
    img.alpha_composite(st, (548, 720 - 140))
    x = 868                                                               # text column; all of it ends inside x 2053
    d.text((x, 668), NAME, font=fraunces(108, 600), fill=PAPER, anchor="ls")
    d.text((x + 4, 752), TAGLINE, font=plex(36, 400), fill=PAPER_DARK, anchor="ls")
    d.text((x + 4, 836), "pbmconsultingservice.com", font=plex(38, 600), fill=BRASS, anchor="ls")
    for label, font, y in ((NAME, fraunces(108, 600), 668), (TAGLINE, plex(36, 400), 752)):
        right = x + d.textlength(label, font=font)
        assert right <= 2053 - 10, f"'{label[:20]}' ends at x={right:.0f}, past the phone safe area (2053)"
    return img


def wordmark(height=132):
    """Site logo: the stamp beside the name on a transparent ground, for the
    website masthead (shown 44 px tall, drawn at 3x for sharp screens)."""
    s = height / 132
    st = stamp(height, bg=(0, 0, 0, 0))
    font, sub = fraunces(round(56 * s), 600), plex(round(22 * s), 600)
    gap = round(22 * s)
    probe = ImageDraw.Draw(st)
    w = st.width + gap + round(probe.textlength("PBM Consulting", font=font)) + round(8 * s)
    img = Image.new("RGBA", (w, height), (0, 0, 0, 0))
    img.alpha_composite(st, (0, 0))
    d = ImageDraw.Draw(img)
    x = st.width + gap
    d.text((x, round(74 * s)), "PBM Consulting", font=font, fill=FOREST, anchor="ls")
    d.text((x + round(2 * s), round(108 * s)), "SERVICE", font=sub, fill=OXBLOOD, anchor="ls")
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"E:\Phoenix\video\brand")
    ap.add_argument("--logo", help="also write the website logo (transparent PNG) to this path")
    a = ap.parse_args()
    if a.logo:
        wordmark().save(a.logo, optimize=True)
        print(f"wrote {a.logo}")
    os.makedirs(a.out, exist_ok=True)
    banner().convert("RGB").save(os.path.join(a.out, "banner.png"), optimize=True)
    stamp(800).convert("RGB").save(os.path.join(a.out, "profile.png"), optimize=True)
    print(f"wrote {a.out}\\banner.png and profile.png")


if __name__ == "__main__":
    main()
