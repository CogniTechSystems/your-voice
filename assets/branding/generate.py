"""Generate the editable Your Voice brand graphics."""

from pathlib import Path

DESTINATION = Path(__file__).resolve().parent


def mark(x: int, y: int, size: int) -> str:
    return f'''<g transform="translate({x} {y}) scale({size / 100})">
  <rect width="100" height="100" rx="25" fill="#16323d" stroke="#4dc6c7" stroke-opacity=".5"/>
  <path d="M23 29h54a7 7 0 0 1 7 7v33a7 7 0 0 1-7 7H48L32 88V76h-9a7 7 0 0 1-7-7V36a7 7 0 0 1 7-7Z" fill="none" stroke="#e9f4ef" stroke-width="5" stroke-linejoin="round"/>
  <path d="M31 53h9l6-11 9 22 6-11h10" fill="none" stroke="#61dad2" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
</g>'''


def background(width: int, height: int) -> str:
    return f'''<defs>
  <linearGradient id="bg" x2="1" y2="1"><stop stop-color="#101b25"/><stop offset="1" stop-color="#152d35"/></linearGradient>
  <linearGradient id="line" x2="1" y2="0"><stop stop-color="#40bdbc" stop-opacity="0"/><stop offset=".55" stop-color="#48c7c2" stop-opacity=".55"/><stop offset="1" stop-color="#7edbd0" stop-opacity=".08"/></linearGradient>
  <radialGradient id="glow"><stop stop-color="#399f9d" stop-opacity=".3"/><stop offset="1" stop-color="#399f9d" stop-opacity="0"/></radialGradient>
</defs>
<rect width="{width}" height="{height}" fill="url(#bg)"/>
<circle cx="{width * .83:.0f}" cy="{height * .45:.0f}" r="{height * .65:.0f}" fill="url(#glow)"/>
<g fill="none" stroke="url(#line)" stroke-width="2">{''.join(f'<path d="M{width * .48:.0f} {height * (.3 + i * .09):.0f} C{width * .68:.0f} {height * (.02 + i * .08):.0f} {width * .8:.0f} {height * (.84 - i * .04):.0f} {width + 60} {height * (.32 + i * .08):.0f}"/>' for i in range(9))}</g>
<path d="M0 {height - 8}H{width}" stroke="#64d3ca" stroke-width="8"/>'''


def document(width: int, height: int, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">Your Voice</title><desc id="desc">Your Voice brand banner with a speech and waveform mark.</desc>
{background(width, height)}{body}</svg>\n'''


def wide(width: int, height: int) -> str:
    compact = height <= 500
    left = int(width * .075)
    icon = 76 if compact else 88
    title_size = 94 if width >= 1250 and not compact else 82 if not compact else 72
    top = int(height * (.23 if compact else .25))
    tagline_y = top + icon + title_size + (22 if compact else 34)
    body = f'''{mark(left, top, icon)}
<text x="{left}" y="{top + icon + title_size - 2}" fill="#f1f5ee" font-family="Georgia, serif" font-size="{title_size}" font-weight="bold" letter-spacing="-3">Your Voice</text>
<text x="{left + 3}" y="{tagline_y}" fill="#c2d2cf" font-family="Segoe UI, Arial, sans-serif" font-size="{26 if compact else 30}" letter-spacing=".2">Write with a local model. Sound like yourself.</text>
<path d="M{left + 3} {tagline_y + 29}h{140 if compact else 176}" stroke="#64d3ca" stroke-width="4" stroke-linecap="round"/>'''
    return document(width, height, body)


def stacked(width: int, height: int) -> str:
    left = 95
    top = round(height * .24)
    title_size = 116
    body = f'''{mark(left, top, 122)}
<text x="{left}" y="{top + 270}" fill="#f1f5ee" font-family="Georgia, serif" font-size="{title_size}" font-weight="bold" letter-spacing="-4">Your Voice</text>
<text x="{left + 2}" y="{top + 350}" fill="#c2d2cf" font-family="Segoe UI, Arial, sans-serif" font-size="34">Write with a local model.</text>
<text x="{left + 2}" y="{top + 399}" fill="#c2d2cf" font-family="Segoe UI, Arial, sans-serif" font-size="34">Sound like yourself.</text>
<path d="M{left + 2} {top + 442}h190" stroke="#64d3ca" stroke-width="5" stroke-linecap="round"/>'''
    return document(width, height, body)


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    sizes = {
        "social-1280x720": (1280, 720),
        "social-1200x630": (1200, 630),
        "header-1500x500": (1500, 500),
        "square-1080x1080": (1080, 1080),
        "portrait-1080x1350": (1080, 1350),
        "story-1080x1920": (1080, 1920),
    }
    for name, (width, height) in sizes.items():
        graphic = wide(width, height) if width > height * 1.5 else stacked(width, height)
        (DESTINATION / f"{name}.svg").write_text(graphic, encoding="utf-8")
    (DESTINATION / "avatar-400x400.svg").write_text(
        document(400, 400, mark(70, 70, 260)), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
