#!/usr/bin/env python3
"""Generate placeholder head-and-shoulders portraits, one per actor type.

Flat silhouette on a role-tinted background, in the game's industrial palette.
Replace them with real artwork later; keep the filenames and the 512x512 size.

    python3 assets/make_placeholder_portraits.py
"""
import pathlib

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
OUT = pathlib.Path(__file__).parent / "portraits"

# role -> (background, silhouette, accent) in the console palette
ROLES = {
    "security":     ("#1b2a33", "#5d7d8f", "#00e5ff"),
    "construction": ("#33291b", "#8f7a4f", "#ffb000"),
    "cargo":        ("#1f2b1f", "#6c8a6c", "#00ff40"),
    "medical":      ("#331b22", "#96626f", "#ff4d6d"),
    "civilian":     ("#26262b", "#7e7e8a", "#c8d0d4"),
    "system":       ("#101010", "#4a4a4a", "#ff1a1a"),
}


def font(px):
    for name in ("DejaVuSansMono-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_portrait(role, bg, fg, accent):
    img = Image.new("RGB", (SIZE, SIZE), bg)
    d = ImageDraw.Draw(img)

    # faint grid, so a placeholder reads as a placeholder
    for i in range(0, SIZE, 32):
        d.line([(i, 0), (i, SIZE)], fill=bg, width=1)

    if role == "system":
        # not a person: a speaker grille
        d.rectangle([136, 136, 376, 376], outline=fg, width=6)
        for y in range(170, 350, 22):
            d.line([(170, y), (342, y)], fill=fg, width=7)
        d.ellipse([236, 236, 276, 276], fill=accent)
    else:
        # shoulders: a wide rounded slab rising from the bottom edge
        d.rounded_rectangle([96, 330, 416, 560], radius=64, fill=fg)
        # neck
        d.rectangle([228, 286, 284, 348], fill=fg)
        # head
        d.ellipse([176, 132, 336, 300], fill=fg)
        # accent collar, so the roles are told apart at a glance
        d.rounded_rectangle([150, 352, 362, 386], radius=16, fill=accent)

    label = role.upper()
    f = font(30)
    w = d.textlength(label, font=f)
    d.rectangle([0, SIZE - 62, SIZE, SIZE], fill="#000000")
    d.text(((SIZE - w) / 2, SIZE - 48), label, font=f, fill=accent)

    f2 = font(17)
    tag = "PLACEHOLDER"
    w2 = d.textlength(tag, font=f2)
    d.text((SIZE - w2 - 12, 12), tag, font=f2, fill=fg)
    return img


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for role, (bg, fg, accent) in ROLES.items():
        path = OUT / f"{role}.png"
        draw_portrait(role, bg, fg, accent).save(path)
        print(f"  wrote {path.relative_to(OUT.parent.parent)}")
    print(f"{len(ROLES)} placeholder portraits, {SIZE}x{SIZE} PNG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
