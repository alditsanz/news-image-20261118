#!/usr/bin/env python3
"""Draw Wednesday 18 November 2026's world news as a single newspaper
front page and write it to /output/entry.png (1024x1024 PNG).

Standard library only. The program draws everything itself: it owns a
tiny PNG encoder (zlib + struct), a hand-built 5x7 bitmap font, and all
shapes (rectangles, lines, circles, polygons) used for the masthead,
the burning-tanker hero illustration and the story panels.

Deterministic: no wall clock, no randomness, no dict-order dependence.
Running it twice produces byte-identical output.

Stories used (all reported 18 November 2026, see the research dossier
research-nov18-partial.md, passes 1-3):
  lead  - US says it destroyed five Iranian tankers in the Gulf;
          Iran claims missile strikes on the US base in Jordan;
          oil over $100 a barrel
  1     - Trump lands in Shenzhen; Xi greets him on the tarmac;
          first-ever trilateral with Putin set for Thursday
  2     - Ukraine brings down the Kerch Bridge road span
          (second strike in two days)
  3     - Nvidia beats with a record $115.8B quarter; futures
          rebound after Tuesday's 849-point Dow rout
          (Wednesday close not yet known at build time)
  4     - Category 5 Cyclone Xavier bears down on the
          Northern Cook Islands, 220 km/h winds
  5     - Ebola in DR Congo passes 11,000 cases, 5,400 deaths
  6     - Peltola flips Alaska; Democrats take the Senate 56-44
  7     - Zverev beats Shelton 6-2, 7-6 to reach the ATP semis
  also  - Anthropic IPO prices tonight; Fed minutes due 2pm ET;
          US loses measles-free status after 26 years
"""

import math
import os
import struct
import zlib

# ---------------------------------------------------------------- canvas

W, H = 1024, 1024

PAPER = (247, 242, 231)      # newsprint cream
PAPER2 = (255, 253, 246)     # lighter panel paper
INK = (18, 18, 18)           # near-black text
NAVY = (13, 42, 71)          # masthead blue
NAVY2 = (24, 62, 102)
RED = (178, 34, 34)          # headline red
RED2 = (150, 24, 24)
TEAL = (14, 94, 88)
GOLD = (176, 124, 22)
GREY = (90, 88, 82)          # body grey
LINE = (40, 40, 40)
SKY1 = (186, 214, 235)
SKY2 = (214, 231, 242)
SEA1 = (38, 98, 138)
SEA2 = (24, 74, 110)
STEEL = (74, 78, 84)
STEEL2 = (52, 56, 62)
SMOKE = (150, 150, 148)
WHITE = (255, 255, 255)
ORANGE = (230, 110, 20)
FLAME = (240, 170, 30)
GREEN = (22, 120, 60)


class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)
        r, g, b = bg
        for i in range(0, len(self.px), 3):
            self.px[i] = r
            self.px[i + 1] = g
            self.px[i + 2] = b

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i] = c[0]
            self.px[i + 1] = c[1]
            self.px[i + 2] = c[2]

    def rect(self, x, y, w, h, c):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        for yy in range(y0, y1):
            base = (yy * self.w + x0) * 3
            for xx in range(x0, x1):
                i = base + (xx - x0) * 3
                self.px[i] = c[0]
                self.px[i + 1] = c[1]
                self.px[i + 2] = c[2]

    def hline(self, x0, x1, y, c, t=1):
        for yy in range(y, y + t):
            for xx in range(min(x0, x1), max(x0, x1) + 1):
                self.set(xx, yy, c)

    def vline(self, x, y0, y1, c, t=1):
        for xx in range(x, x + t):
            for yy in range(min(y0, y1), max(y0, y1) + 1):
                self.set(xx, yy, c)

    def line(self, x0, y0, x1, y1, c, t=1):
        """Bresenham line, thickness t (square brush)."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        half = t // 2
        while True:
            for oy in range(-half, half + 1):
                for ox in range(-half, half + 1):
                    self.set(x + ox, y + oy, c)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def disc(self, cx, cy, r, c):
        if r <= 0:
            return
        for yy in range(cy - r, cy + r + 1):
            dy = yy - cy
            if abs(dy) > r:
                continue
            dx = int((r * r - dy * dy) ** 0.5)
            for xx in range(cx - dx, cx + dx + 1):
                self.set(xx, yy, c)

    def circle(self, cx, cy, r, c):
        steps = max(8, int(6.28 * r))
        for k in range(steps):
            a = 6.283185307179586 * k / steps
            self.set(cx + int(r * math.cos(a)),
                     cy + int(r * math.sin(a)), c)

    def arc(self, cx, cy, r, a0, a1, c, t=2):
        """Arc from angle a0 to a1 (radians), thickness t."""
        steps = max(4, int(abs(a1 - a0) * r))
        for k in range(steps + 1):
            a = a0 + (a1 - a0) * k / steps
            x = cx + int(r * math.cos(a))
            y = cy + int(r * math.sin(a))
            for oy in range(-t // 2, t // 2 + 1):
                for ox in range(-t // 2, t // 2 + 1):
                    self.set(x + ox, y + oy, c)

    def poly(self, pts, c):
        """Fill a polygon by scanline (pts = list of (x, y))."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        for y in range(min(ys), max(ys) + 1):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if y0 == y1:
                    continue
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            if len(xs) >= 2:
                xs.sort()
                for k in range(0, len(xs) - 1, 2):
                    for xx in range(int(xs[k]), int(xs[k + 1]) + 1):
                        self.set(xx, y, c)


# ---------------------------------------------------------------- font
# Hand-built 5x7 bitmap font. Each glyph is 7 rows of 5 characters,
# '#' = ink, '.' = blank. All poster text is set in capitals.

FONT = {
    'A': (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    'B': ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    'C': (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    'D': ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    'E': ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    'F': ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    'G': (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    'H': ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    'I': ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    'J': ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    'K': ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    'L': ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    'M': ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    'N': ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    'O': (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    'P': ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    'Q': (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    'R': ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    'S': (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    'T': ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    'U': ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    'V': ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    'W': ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    'X': ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    'Y': ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    'Z': ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    '0': (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    '1': ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    '2': (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    '3': ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    '4': ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    '5': ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    '6': (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    '7': ("#####", "....#", "...#.", "...#.", "..#..", "..#..", "..#.."),
    '8': (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    '9': (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    ' ': (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    '.': (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ',': (".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."),
    ':': (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    ';': (".....", ".##..", ".##..", ".....", ".##..", ".##..", ".#..."),
    '!': ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    '?': (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    "'": ("..#..", "..#..", ".#...", ".....", ".....", ".....", "....."),
    '-': (".....", ".....", ".....", ".###.", ".....", ".....", "....."),
    '(': ("...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."),
    ')': (".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."),
    '/': ("....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."),
    '%': ("##...", "##.#.", "...#.", "..#..", ".#...", ".#.##", "...##"),
    '$': ("..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."),
    '+': (".....", "..#..", "..#..", ".###.", "..#..", "..#..", "....."),
    '=': (".....", ".....", ".###.", ".....", ".###.", ".....", "....."),
}

CHAR_W = 6  # advance per character, in font units (5 glyph + 1 space)


def text_width(s, scale):
    return len(s) * CHAR_W * scale - scale


def draw_text(cv, s, x, y, scale, color, align="left"):
    """Draw uppercase text; returns the x of the right edge + scale."""
    w = text_width(s, scale)
    if align == "center":
        x = x - w // 2
    elif align == "right":
        x = x - w
    cx = x
    for ch in s:
        glyph = FONT.get(ch, FONT[' '])
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits[col] == '#':
                    cv.rect(cx + col * scale, y + row * scale,
                            scale, scale, color)
        cx += CHAR_W * scale
    return x + w


def wrap_text(s, max_chars):
    """Greedy word wrap; returns a list of lines."""
    words = s.split()
    lines = []
    cur = ""
    for word in words:
        if cur == "":
            cur = word
        elif len(cur) + 1 + len(word) <= max_chars:
            cur = cur + " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_para(cv, s, x, y, max_chars, scale, color, line_h=None):
    """Draw a wrapped paragraph; returns y just below the last line."""
    if line_h is None:
        line_h = 7 * scale + 3 * scale // 2
    for line in wrap_text(s, max_chars):
        draw_text(cv, line, x, y, scale, color)
        y += line_h
    return y


# ---------------------------------------------------------------- png

def write_png(path, cv):
    raw = bytearray()
    row_len = cv.w * 3
    for y in range(cv.h):
        raw.append(0)  # filter: none
        raw += cv.px[y * row_len:(y + 1) * row_len]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        c += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# ---------------------------------------------------------------- icons
# Small flat illustrations, one per story. Each draws inside a
# box (x, y, w, h) and uses only rect/line/circle/poly/arc.

def icon_tanker(cv, x, y, w, h):
    """Burning oil tanker in the strait: hull, deck tanks, flames."""
    cx = x + w // 2
    hull_y = y + h - 26
    # hull: long dark trapezoid
    cv.poly([(x + 8, hull_y), (x + w - 8, hull_y),
             (x + w - 26, hull_y + 18), (x + 26, hull_y + 18)], STEEL2)
    cv.rect(x + 8, hull_y, w - 16, 4, RED2)
    # deck tanks
    for i, tx in enumerate((x + 22, x + 66, x + 110)):
        cv.rect(tx, hull_y - 18, 34, 18, (200, 200, 195))
        cv.rect(tx, hull_y - 18, 34, 3, STEEL)
    # bridge tower
    cv.rect(x + w - 52, hull_y - 34, 30, 34, PAPER2)
    cv.rect(x + w - 52, hull_y - 34, 30, 4, NAVY)
    cv.rect(x + w - 46, hull_y - 28, 18, 6, SKY1)
    # flames over the mid tanks
    fx = x + 62
    fy = hull_y - 18
    cv.poly([(fx - 16, fy), (fx - 4, fy - 26), (fx + 6, fy - 10),
             (fx + 14, fy - 30), (fx + 26, fy)], ORANGE)
    cv.poly([(fx - 6, fy), (fx + 2, fy - 16), (fx + 10, fy - 6),
             (fx + 16, fy)], FLAME)
    cv.poly([(fx + 34, fy), (fx + 42, fy - 18), (fx + 52, fy)], ORANGE)
    # smoke
    for sx, sy, sr in ((fx + 4, fy - 38, 8), (fx + 16, fy - 48, 10),
                       (fx + 30, fy - 40, 7)):
        cv.disc(sx, sy, sr, SMOKE)
    # waves
    for wy in (hull_y + 24, hull_y + 34):
        for wx in range(x + 6, x + w - 20, 34):
            cv.hline(wx, wx + 18, wy, SEA2, 2)


def icon_flags(cv, x, y, w, h):
    """Three small flags: US, China, Russia, side by side."""
    fw, fh = 52, 34
    gap = 10
    total = fw * 3 + gap * 2
    sx = x + (w - total) // 2
    sy = y + (h - fh) // 2
    # US flag
    for i in range(5):
        cv.rect(sx, sy + i * 7, fw, 4, RED if i % 2 == 0 else WHITE)
    cv.rect(sx, sy, 22, 17, NAVY)
    for dy in (4, 10):
        for dx in (4, 11, 17):
            cv.set(sx + dx, sy + dy, WHITE)
    cv.rect(sx, sy, fw, 1, LINE)
    cv.rect(sx, sy + fh - 1, fw, 1, LINE)
    cv.rect(sx, sy, 1, fh, LINE)
    cv.rect(sx + fw - 1, sy, 1, fh, LINE)
    # China flag
    cx = sx + fw + gap
    cv.rect(cx, sy, fw, fh, RED2)
    cv.disc(cx + 10, sy + 10, 5, (255, 222, 0))
    for dx, dy in ((25, 7), (31, 12), (31, 19), (25, 23)):
        cv.disc(cx + dx, sy + dy, 2, (255, 222, 0))
    cv.rect(cx, sy, fw, 1, LINE)
    cv.rect(cx, sy + fh - 1, fw, 1, LINE)
    cv.rect(cx, sy, 1, fh, LINE)
    cv.rect(cx + fw - 1, sy, 1, fh, LINE)
    # Russia flag: white / blue / red
    rx = cx + fw + gap
    cv.rect(rx, sy, fw, 11, WHITE)
    cv.rect(rx, sy + 11, fw, 12, (0, 57, 166))
    cv.rect(rx, sy + 23, fw, 11, (213, 0, 50))
    cv.rect(rx, sy, fw, 1, LINE)
    cv.rect(rx, sy + fh - 1, fw, 1, LINE)
    cv.rect(rx, sy, 1, fh, LINE)
    cv.rect(rx + fw - 1, sy, 1, fh, LINE)


def icon_bridge(cv, x, y, w, h):
    """Kerch Bridge: standing arch left, fallen road span in the sea."""
    deck_y = y + h - 34
    # sea
    cv.rect(x, deck_y + 8, w, h - (deck_y + 8 - y), SEA1)
    for wy in range(deck_y + 16, y + h - 4, 12):
        for wx in range(x + 8, x + w - 20, 36):
            cv.hline(wx, wx + 16, wy, SEA2, 2)
    # standing deck, left
    cv.rect(x + 6, deck_y, 96, 7, STEEL)
    # arch over the left deck
    ax0, ax1 = x + 12, x + 96
    apex_y = y + 8
    prev = None
    for k in range(0, 41):
        t = k / 40.0
        px = int(ax0 + (ax1 - ax0) * t)
        py = int(deck_y - (deck_y - apex_y) * (1 - (2 * t - 1) ** 2))
        if prev is not None:
            cv.line(prev[0], prev[1], px, py, STEEL2, 5)
        prev = (px, py)
    # broken stub tilting down into the water
    cv.line(x + 96, deck_y, x + 132, deck_y + 22, STEEL, 7)
    # fallen span in the water
    cv.line(x + 132, deck_y + 26, x + 176, deck_y + 40, STEEL2, 6)
    cv.line(x + 176, deck_y + 40, x + 206, deck_y + 24, STEEL2, 6)
    # splash
    for sx, sy, sr in ((150, deck_y + 34, 5), (168, deck_y + 42, 6),
                       (188, deck_y + 38, 5)):
        cv.disc(sx, sy, sr, WHITE)
    # smoke at the break
    for sx, sy, sr in ((108, deck_y - 14, 8), (120, deck_y - 24, 10),
                       (132, deck_y - 14, 7)):
        cv.disc(sx, sy, sr, SMOKE)


def icon_chip(cv, x, y, w, h):
    """Green chip with pins and a rising arrow."""
    cx = x + 62
    cy = y + h // 2 + 2
    s = 36
    for i in range(4):
        off = -13 + i * 9
        cv.rect(cx - s // 2 - 9, cy + off, 9, 3, GREEN)
        cv.rect(cx + s // 2, cy + off, 9, 3, GREEN)
        cv.rect(cx + off, cy - s // 2 - 9, 3, 9, GREEN)
        cv.rect(cx + off, cy + s // 2, 3, 9, GREEN)
    cv.rect(cx - s // 2, cy - s // 2, s, s, GREEN)
    cv.rect(cx - s // 2, cy - s // 2, s, 5, (16, 90, 45))
    cv.rect(cx - 9, cy - 9, 18, 18, (220, 245, 225))
    cv.rect(cx - 9, cy - 9, 18, 4, (16, 90, 45))
    # rising arrow chart, right side
    ax = x + w - 82
    ay = y + h - 14
    cv.line(ax, ay, ax + 20, ay - 18, GREEN, 4)
    cv.line(ax + 20, ay - 18, ax + 38, ay - 12, GREEN, 4)
    cv.line(ax + 38, ay - 12, ax + 56, ay - 36, GREEN, 4)
    cv.poly([(ax + 56, ay - 36), (ax + 43, ay - 36), (ax + 56, ay - 23)],
            GREEN)


def icon_cyclone(cv, x, y, w, h):
    """Cyclone spiral: broken concentric arcs around a calm eye."""
    cx = x + w // 2
    cy = y + h // 2
    cv.disc(cx, cy, 8, PAPER2)
    cv.circle(cx, cy, 8, TEAL)
    cv.arc(cx, cy, 16, 0.4, 5.2, TEAL, 3)
    cv.arc(cx, cy, 24, 1.2, 6.0, (20, 120, 110), 3)
    cv.arc(cx, cy, 32, 2.0, 6.9, (30, 140, 128), 3)
    # rain streaks at the corners
    for rx, ry in ((x + 10, y + 6), (x + 26, y + 12), (x + w - 14, y + 8),
                   (x + w - 28, y + 16), (x + 14, y + h - 10),
                   (x + w - 12, y + h - 12)):
        cv.line(rx, ry, rx - 4, ry + 10, SEA2, 2)


def icon_virus(cv, x, y, w, h):
    """Ebola virus: spiked dark-red ball."""
    cx = x + w // 2
    cy = y + h // 2
    for k in range(10):
        a = 6.283185307179586 * k / 10
        x1 = cx + int(18 * math.cos(a))
        y1 = cy + int(18 * math.sin(a))
        x2 = cx + int(28 * math.cos(a))
        y2 = cy + int(28 * math.sin(a))
        cv.line(x1, y1, x2, y2, RED2, 3)
        cv.disc(x2, y2, 3, RED2)
    cv.disc(cx, cy, 18, RED)
    cv.disc(cx - 5, cy - 5, 5, (255, 120, 120))
    cv.disc(cx + 6, cy + 4, 3, (255, 150, 150))


def icon_ballot(cv, x, y, w, h):
    """Ballot box with a check mark and a 56-44 tag."""
    cx = x + w // 2 - 30
    cy = y + h // 2 + 4
    # ballot paper going into the slot
    cv.poly([(cx - 18, cy - 34), (cx + 18, cy - 34), (cx + 14, cy - 8),
             (cx - 14, cy - 8)], PAPER2)
    cv.line(cx - 10, cy - 26, cx + 10, cy - 26, GREY, 2)
    cv.line(cx - 10, cy - 20, cx + 6, cy - 20, GREY, 2)
    # box
    cv.rect(cx - 34, cy - 8, 68, 34, NAVY2)
    cv.rect(cx - 34, cy - 8, 68, 4, NAVY)
    cv.rect(cx - 20, cy - 8, 40, 3, INK)
    # big check mark
    cv.line(cx - 26, cy + 8, cx - 12, cy + 20, WHITE, 4)
    cv.line(cx - 12, cy + 20, cx + 24, cy - 14, WHITE, 4)
    # 56-44 tag
    cv.rect(x + w - 78, y + 2, 72, 20, RED)
    draw_text(cv, "56-44", x + w - 74, y + 6, 2, WHITE)


def icon_tennis(cv, x, y, w, h):
    """Tennis ball with curved seam, plus a score tag."""
    cx = x + w // 2 - 34
    cy = y + h // 2
    cv.disc(cx, cy, 26, (190, 220, 40))
    cv.arc(cx, cy, 26, -1.2, 1.2, WHITE, 3)
    cv.arc(cx, cy, 26, 1.9, 4.3, WHITE, 3)
    cv.arc(cx - 8, cy, 14, -1.0, 1.0, WHITE, 2)
    # score tag
    cv.rect(x + w - 108, y + 2, 102, 20, TEAL)
    draw_text(cv, "6-2, 7-6", x + w - 104, y + 6, 2, WHITE)


# ---------------------------------------------------------------- hero

def draw_hero(cv, x, y, w, h):
    """Burning tanker in the Strait of Hormuz at dusk."""
    # sky bands
    cv.rect(x, y, w, h // 2, SKY1)
    cv.rect(x, y + h // 2, w, h - h // 2, SEA1)
    # low sun (kept clear of the oil-price tag at top right)
    cv.disc(x + w - 280, y + 30, 18, (255, 214, 120))
    # sea waves
    for wy in range(y + h // 2 + 16, y + h - 6, 16):
        for wx in range(x + 14, x + w - 30, 48):
            cv.hline(wx, wx + 24, wy, SEA2, 2)
    # big tanker, centre-left
    tx = x + 30
    hull_y = y + h - 52
    cv.poly([(tx, hull_y), (tx + 560, hull_y),
             (tx + 530, hull_y + 34), (tx + 30, hull_y + 34)], STEEL2)
    cv.rect(tx, hull_y, 560, 5, RED2)
    for i, bx in enumerate((tx + 30, tx + 130, tx + 230, tx + 330)):
        cv.rect(bx, hull_y - 30, 80, 30, (200, 200, 195))
        cv.rect(bx, hull_y - 30, 80, 4, STEEL)
    # bridge tower, right end
    cv.rect(tx + 470, hull_y - 62, 60, 62, PAPER2)
    cv.rect(tx + 470, hull_y - 62, 60, 6, NAVY)
    cv.rect(tx + 480, hull_y - 50, 40, 10, SKY1)
    # flames over the mid tanks
    for fx, fh in ((tx + 150, 64), (tx + 260, 84), (tx + 360, 56)):
        fy = hull_y - 30
        cv.poly([(fx - 26, fy), (fx - 8, fy - fh), (fx + 6, fy - fh // 2),
                 (fx + 16, fy - fh - 10), (fx + 30, fy)], ORANGE)
        cv.poly([(fx - 11, fy), (fx - 2, fy - fh // 2),
                 (fx + 9, fy - fh // 3), (fx + 15, fy)], FLAME)
    # smoke column
    for sx, sy, sr in ((tx + 180, hull_y - 96, 18), (tx + 210, hull_y - 118, 22),
                       (tx + 250, hull_y - 104, 16), (tx + 290, hull_y - 126, 14)):
        cv.disc(sx, sy, sr, SMOKE)
    cv.disc(tx + 210, hull_y - 118, 10, (110, 110, 108))
    # second, smaller tanker burning far right
    sx2 = x + w - 190
    cv.poly([(sx2, hull_y + 6), (sx2 + 130, hull_y + 6),
             (sx2 + 118, hull_y + 24), (sx2 + 12, hull_y + 24)], STEEL)
    cv.poly([(sx2 + 40, hull_y + 6), (sx2 + 52, hull_y - 22),
             (sx2 + 66, hull_y + 6)], ORANGE)
    cv.disc(sx2 + 56, hull_y - 34, 9, SMOKE)
    # "LEAD STORY" tag
    cv.rect(x + 16, y + 12, 148, 26, RED)
    draw_text(cv, "LEAD STORY", x + 26, y + 18, 2, WHITE)
    # oil price tag
    cv.rect(x + w - 176, y + 12, 160, 26, INK)
    draw_text(cv, "OIL OVER $100", x + w - 166, y + 18, 2, WHITE)


# ---------------------------------------------------------------- page

PANELS = [
    # (kicker, kicker colour, headline, body, icon fn)
    ("UKRAINE", RED2, "KERCH BRIDGE ROAD SPAN FALLS",
     "SECOND NIGHT RUNNING. ROAD SPAN DOWN.",
     icon_bridge),
    ("MARKETS", GREEN, "NVIDIA BEATS: RECORD $115.8B",
     "FUTURES REBOUND AFTER DOW FELL 849 TUESDAY.",
     icon_chip),
    ("WEATHER", TEAL, "CYCLONE XAVIER, CATEGORY 5",
     "220 KM/H WINDS BEAR DOWN ON COOK ISLANDS.",
     icon_cyclone),
    ("HEALTH", RED, "EBOLA CASES PASS 11,000",
     "DEATHS TOP 5,400 IN DR CONGO. KIDS HIT HARDEST.",
     icon_virus),
    ("POLITICS", NAVY, "PELTOLA FLIPS ALASKA SENATE",
     "DEMOCRATS TAKE THE SENATE 56-44.",
     icon_ballot),
    ("SPORT", GOLD, "ZVEREV INTO ATP SEMI-FINALS",
     "BEATS SHELTON 6-2, 7-6 IN TURIN.",
     icon_tennis),
]


def draw_panel(cv, x, y, w, h, kicker, kcolor, headline, body, icon):
    cv.rect(x, y, w, h, PAPER2)
    # border (2px)
    cv.rect(x, y, w, 2, LINE)
    cv.rect(x, y + h - 2, w, 2, LINE)
    cv.rect(x, y, 2, h, LINE)
    cv.rect(x + w - 2, y, 2, h, LINE)
    # kicker band
    cv.rect(x + 2, y + 2, w - 4, 24, kcolor)
    draw_text(cv, kicker, x + 12, y + 7, 2, WHITE)
    # icon
    icon(cv, x + 10, y + 30, w - 20, 52)
    # headline (up to 2 lines)
    max_chars = (w - 24) // (CHAR_W * 3)
    lines = wrap_text(headline, max_chars)
    ty = y + 86
    for line in lines[:2]:
        draw_text(cv, line, x + 12, ty, 3, INK)
        ty += 22
    # body (up to 2 lines)
    max_body = (w - 24) // (CHAR_W * 2)
    by = ty + 2
    for line in wrap_text(body, max_body)[:2]:
        draw_text(cv, line, x + 12, by, 2, GREY)
        by += 14


def build():
    cv = Canvas(W, H, PAPER)

    # ---- masthead
    cv.rect(0, 0, W, 108, NAVY)
    cv.rect(0, 108, W, 4, RED)
    draw_text(cv, "THE WORLD IN ONE DAY", W // 2, 22, 6, WHITE,
              align="center")
    draw_text(cv, "FRONT PAGE - EVERY STORY REPORTED ON THE DAY",
              W // 2, 78, 2, (190, 205, 220), align="center")

    # ---- date banner
    cv.rect(24, 122, W - 48, 44, PAPER2)
    cv.rect(24, 122, W - 48, 2, LINE)
    cv.rect(24, 164, W - 48, 2, LINE)
    draw_text(cv, "WEDNESDAY 18 NOVEMBER 2026", W // 2, 130, 4, RED,
              align="center")

    # ---- hero: burning tanker illustration + headline
    hx, hy, hw, hh = 24, 178, W - 48, 300
    cv.rect(hx, hy, hw, hh, PAPER2)
    draw_hero(cv, hx + 2, hy + 2, hw - 4, 178)
    ty = hy + 188
    draw_text(cv, "US DESTROYS FIVE", hx + 14, ty, 5, INK)
    draw_text(cv, "IRANIAN TANKERS", hx + 14, ty + 38, 5, RED)
    draw_para(cv,
              "IRAN CLAIMS MISSILE STRIKES ON THE US BASE IN JORDAN. "
              "FIVE TANKERS HIT IN THE GULF.",
              hx + 14, ty + 80, (hw - 28) // (CHAR_W * 2), 2, GREY)

    # ---- APEC strip: three flags + arrival headline
    ax, ay, aw, ah = 24, 488, W - 48, 96
    cv.rect(ax, ay, aw, ah, PAPER2)
    cv.rect(ax, ay, aw, 2, LINE)
    cv.rect(ax, ay + ah - 2, aw, 2, LINE)
    cv.rect(ax, ay, 2, ah, LINE)
    cv.rect(ax + aw - 2, ay, 2, ah, LINE)
    cv.rect(ax + 2, ay + 2, 208, ah - 4, NAVY2)
    icon_flags(cv, ax + 10, ay + 10, 192, ah - 20)
    draw_text(cv, "XI HUGS TRUMP ON THE", ax + 226, ay + 8, 4, INK)
    draw_text(cv, "TARMAC IN SHENZHEN", ax + 226, ay + 38, 4, RED)
    draw_para(cv,
              "FIRST-EVER TRILATERAL WITH PUTIN SET FOR THURSDAY.",
              ax + 226, ay + 70, (aw - 250) // (CHAR_W * 2), 2, GREY)

    # ---- story grid: 3 columns x 2 rows
    gx, gy = 24, 592
    pw, ph = 318, 168
    gap = 10
    for i, (kicker, kcolor, headline, body, icon) in enumerate(PANELS):
        px = gx + (i % 3) * (pw + gap)
        py = gy + (i // 3) * (ph + gap)
        draw_panel(cv, px, py, pw, ph, kicker, kcolor, headline, body, icon)

    # ---- footer strip
    fy = gy + 2 * ph + gap + 8
    cv.rect(24, fy, W - 48, 2, LINE)
    draw_para(cv,
              "ALSO: ANTHROPIC IPO PRICES TONIGHT. FED MINUTES DUE 2PM ET. "
              "US LOSES MEASLES-FREE STATUS AFTER 26 YEARS.",
              24, fy + 12, (W - 48) // (CHAR_W * 2), 2, INK)
    # ---- bottom credit bar
    cv.rect(0, 992, W, 32, NAVY)
    draw_text(cv, "DRAWN IN CODE - NO PHOTOGRAPHS - THE WORLD IN ONE DAY",
              W // 2, 1001, 2, (190, 205, 220), align="center")
    return cv


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    cv = build()
    size = write_png(path, cv)
    print(f"wrote {path} ({cv.w}x{cv.h}, {size} bytes)")


if __name__ == "__main__":
    main()
