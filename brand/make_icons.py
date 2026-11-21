#!/usr/bin/env python3
"""Render the brand icon set into brand/icons/.

Run once on macOS whenever the artwork changes (needs Pillow and iconutil);
the rendered files are committed, so CI never runs this.
"""
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icons")

# Artwork is defined on a 1024 grid.
GRID = 1024
SS = 4  # supersampling factor

BG_TOP = (36, 48, 110)
BG_BOTTOM = (12, 16, 44)
GOLD_TOP = (255, 226, 140)
GOLD_BOTTOM = (245, 176, 20)

CROWN = [(282, 680), (212, 388), (372, 536), (512, 298), (652, 536), (812, 388), (742, 680)]
JEWELS = [(212, 372, 40), (512, 278, 44), (812, 372, 40)]
BAND = (282, 716, 742, 784, 22)


def vertical_gradient(size, top, bottom):
    ramp = Image.linear_gradient("L").resize((size, size))
    return Image.composite(Image.new("RGB", (size, size), bottom), Image.new("RGB", (size, size), top), ramp)


def crown_mask(size):
    k = size / GRID
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.polygon([(x * k, y * k) for x, y in CROWN], fill=255)
    for cx, cy, r in JEWELS:
        d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=255)
    x0, y0, x1, y1, r = BAND
    d.rounded_rectangle([x0 * k, y0 * k, x1 * k, y1 * k], radius=r * k, fill=255)
    return mask


def render(size, inset=0.0):
    """Full icon. inset is the transparent margin as a fraction of the canvas (macOS grid)."""
    big = size * SS
    art = int(round(big * (1 - 2 * inset)))
    tile = vertical_gradient(art, BG_TOP, BG_BOTTOM).convert("RGBA")
    shape = Image.new("L", (art, art), 0)
    ImageDraw.Draw(shape).rounded_rectangle([0, 0, art - 1, art - 1], radius=art * 0.2227, fill=255)
    tile.putalpha(shape)
    gold = vertical_gradient(art, GOLD_TOP, GOLD_BOTTOM).convert("RGBA")
    gold.putalpha(crown_mask(art))
    tile.alpha_composite(gold)
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    off = (big - art) // 2
    canvas.alpha_composite(tile, (off, off))
    return canvas.resize((size, size), Image.LANCZOS)


def glyph(size, color):
    """Crown silhouette only, for the macOS menu bar."""
    big = size * SS
    src = crown_mask(GRID)
    box = src.getbbox()
    crop = src.crop(box)
    pad = int(big * 0.08)
    scale = min((big - 2 * pad) / crop.width, (big - 2 * pad) / crop.height)
    crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
    mask = Image.new("L", (big, big), 0)
    mask.paste(crop, ((big - crop.width) // 2, (big - crop.height) // 2))
    out = Image.new("RGBA", (big, big), color + (0,))
    out.putalpha(mask)
    return out.resize((size, size), Image.LANCZOS)


def write_svg(path):
    pts = " ".join(f"{x},{y}" for x, y in CROWN)
    jewels = "".join(f'<circle cx="{cx}" cy="{cy}" r="{r}"/>' for cx, cy, r in JEWELS)
    x0, y0, x1, y1, r = BAND
    rgb = lambda c: "#%02x%02x%02x" % c
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}">
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{rgb(BG_TOP)}"/><stop offset="1" stop-color="{rgb(BG_BOTTOM)}"/></linearGradient>
<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{rgb(GOLD_TOP)}"/><stop offset="1" stop-color="{rgb(GOLD_BOTTOM)}"/></linearGradient>
</defs>
<rect width="{GRID}" height="{GRID}" rx="{GRID * 0.2227:.0f}" fill="url(#bg)"/>
<g fill="url(#gold)"><polygon points="{pts}"/>{jewels}<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="{r}"/></g>
</svg>
'''
    with open(path, "w") as f:
        f.write(svg)


def write_icns(path):
    tmp = tempfile.mkdtemp()
    iconset = os.path.join(tmp, "AppIcon.iconset")
    os.makedirs(iconset)
    for pt in (16, 32, 128, 256, 512):
        render(pt, inset=0.0977).save(os.path.join(iconset, f"icon_{pt}x{pt}.png"))
        render(pt * 2, inset=0.0977).save(os.path.join(iconset, f"icon_{pt}x{pt}@2x.png"))
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", path], check=True)
    shutil.rmtree(tmp)


def main():
    os.makedirs(OUT, exist_ok=True)
    render(1024).save(os.path.join(OUT, "icon-1024.png"))
    render(1024, inset=0.0977).save(os.path.join(OUT, "mac-icon-1024.png"))
    for s in (32, 64, 128, 256):
        render(s).save(os.path.join(OUT, f"icon-{s}.png"))
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    render(256).save(os.path.join(OUT, "icon.ico"), sizes=[(s, s) for s in ico_sizes])
    render(32).save(os.path.join(OUT, "tray.ico"), sizes=[(32, 32)])
    glyph(60, (0, 0, 0)).save(os.path.join(OUT, "mac-tray-dark-x2.png"))
    glyph(48, (255, 255, 255)).save(os.path.join(OUT, "mac-tray-light-x2.png"))
    write_svg(os.path.join(OUT, "icon.svg"))
    write_icns(os.path.join(OUT, "AppIcon.icns"))
    print("wrote", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
