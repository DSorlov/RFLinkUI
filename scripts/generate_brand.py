#!/usr/bin/env python3
"""Generate the local brand images for the RFLink UI integration.

Home Assistant 2026.3 and newer serve brand images straight from
``custom_components/<domain>/brand/``, so they no longer have to live in the
home-assistant/brands repository. Run this script to regenerate them:

    python scripts/generate_brand.py

Requires Pillow.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "custom_components" / "rflink_ui" / "brand"

LIGHT_ACCENT = (3, 155, 229, 255)  # Blue that reads well on white
LIGHT_MAST = (33, 47, 61, 255)
DARK_ACCENT = (79, 195, 247, 255)  # Lighter blue for dark backgrounds
DARK_MAST = (236, 240, 241, 255)

FONT_CANDIDATES = (
    "/System/Library/Fonts/Avenir Next.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size, index=1)
            except OSError:
                continue
    return ImageFont.load_default(size)


def _draw_tower(
    draw: ImageDraw.ImageDraw,
    *,
    center_x: float,
    top: float,
    height: float,
    accent: tuple[int, int, int, int],
    mast: tuple[int, int, int, int],
) -> None:
    """Draw a transmitter mast with radio waves radiating from the tip."""
    unit = height / 100
    stroke = max(2, round(7 * unit))

    tip_y = top + 26 * unit
    base_y = top + height
    half_base = 20 * unit

    # Mast legs and cross braces.
    draw.line(
        [(center_x - half_base, base_y), (center_x - 4 * unit, tip_y)],
        fill=mast,
        width=stroke,
    )
    draw.line(
        [(center_x + half_base, base_y), (center_x + 4 * unit, tip_y)],
        fill=mast,
        width=stroke,
    )
    for fraction in (0.42, 0.68, 0.94):
        y = tip_y + (base_y - tip_y) * fraction
        spread = 4 * unit + (half_base - 4 * unit) * fraction
        draw.line(
            [(center_x - spread, y), (center_x + spread, y)],
            fill=mast,
            width=max(2, round(stroke * 0.7)),
        )

    # Emitter.
    radius = 7 * unit
    draw.ellipse(
        [
            center_x - radius,
            tip_y - radius,
            center_x + radius,
            tip_y + radius,
        ],
        fill=accent,
    )

    # Radio waves on both sides of the emitter.
    for index, wave in enumerate((22, 38, 54), start=1):
        size = wave * unit
        box = [center_x - size, tip_y - size, center_x + size, tip_y + size]
        width = max(2, round(stroke * (1.0 - index * 0.15)))
        draw.arc(box, start=200, end=250, fill=accent, width=width)
        draw.arc(box, start=290, end=340, fill=accent, width=width)


def build_icon(size: int, *, dark: bool) -> Image.Image:
    """Render the square icon."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    accent = DARK_ACCENT if dark else LIGHT_ACCENT
    mast = DARK_MAST if dark else LIGHT_MAST

    _draw_tower(
        draw,
        center_x=size / 2,
        top=size * 0.28,
        height=size * 0.62,
        accent=accent,
        mast=mast,
    )
    return image


def build_logo(width: int, height: int, *, dark: bool) -> Image.Image:
    """Render the wide logo: icon on the left, wordmark on the right."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    accent = DARK_ACCENT if dark else LIGHT_ACCENT
    mast = DARK_MAST if dark else LIGHT_MAST

    tower_height = height * 0.66
    _draw_tower(
        draw,
        center_x=height * 0.52,
        top=(height - tower_height) / 2,
        height=tower_height,
        accent=accent,
        mast=mast,
    )

    font = _load_font(round(height * 0.36))
    text_x = height * 1.02
    text_y = height / 2
    draw.text((text_x, text_y), "RFLink", font=font, fill=mast, anchor="lm")

    left, _, right, _ = draw.textbbox((0, 0), "RFLink", font=font)
    draw.text(
        (text_x + (right - left) + height * 0.12, text_y),
        "UI",
        font=font,
        fill=accent,
        anchor="lm",
    )
    return image


def main() -> None:
    """Write every brand image variant."""
    BRAND_DIR.mkdir(parents=True, exist_ok=True)

    build_icon(256, dark=False).save(BRAND_DIR / "icon.png")
    build_icon(512, dark=False).save(BRAND_DIR / "icon@2x.png")
    build_icon(256, dark=True).save(BRAND_DIR / "dark_icon.png")
    build_icon(512, dark=True).save(BRAND_DIR / "dark_icon@2x.png")

    build_logo(512, 172, dark=False).save(BRAND_DIR / "logo.png")
    build_logo(1024, 344, dark=False).save(BRAND_DIR / "logo@2x.png")
    build_logo(512, 172, dark=True).save(BRAND_DIR / "dark_logo.png")
    build_logo(1024, 344, dark=True).save(BRAND_DIR / "dark_logo@2x.png")

    for path in sorted(BRAND_DIR.glob("*.png")):
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
