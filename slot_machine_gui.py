"""A graphical slot machine built on top of the original console game.

Run with:  python3 slot_machine_gui.py     (needs: pip install pygame)

Controls
    SPACE / ENTER ....... spin the reels
    UP / DOWN ........... change the number of lines
    LEFT / RIGHT ........ change the bet per line (hold SHIFT for +/-10)
    M ................... mute
    Q / ESC ............. cash out and quit
"""

import array
import math
import random

import pygame

from slot_core import (
    MAX_LINES,
    MAX_BET,
    MIN_BET,
    ROWS,
    COLS,
    symbol_count,
    symbol_value,
    check_winnings,
    get_slot_machine_spin,
)

# ---------------------------------------------------------------------------
# Window and layout
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 1000, 840
FPS = 60

TILE = 132              # width/height of one symbol tile
TILE_GAP = 12
PITCH = TILE + TILE_GAP  # distance from one tile to the next while scrolling

# Cabinet
CAB = pygame.Rect(40, 20, 830, 800)
MARQUEE = pygame.Rect(CAB.x + 22, CAB.y + 18, CAB.w - 44, 92)
GLASS_PAD = 18
GLASS = pygame.Rect(86, 152, COLS * TILE + (COLS - 1) * TILE_GAP + GLASS_PAD * 2,
                    ROWS * TILE + (ROWS - 1) * TILE_GAP + GLASS_PAD * 2)
PAYTABLE = pygame.Rect(GLASS.right + 24, GLASS.y, CAB.right - 24 - (GLASS.right + 24), GLASS.h)
RIBBON = pygame.Rect(GLASS.x, GLASS.bottom + 14, PAYTABLE.right - GLASS.x, 46)
PANEL = pygame.Rect(CAB.x + 22, RIBBON.bottom + 12, CAB.w - 44, CAB.bottom - RIBBON.bottom - 28)

# ---------------------------------------------------------------------------
# Palette -- a red-and-gold Vegas cabinet on a dark purple floor
# ---------------------------------------------------------------------------

BG_TOP = (30, 10, 44)
BG_BOTTOM = (10, 4, 18)
CAB_LIGHT = (172, 32, 58)
CAB_DARK = (84, 12, 30)
CAB_EDGE = (54, 8, 20)
GOLD = (247, 200, 84)
GOLD_DARK = (168, 122, 26)
GOLD_LIGHT = (255, 233, 160)
GLASS_DARK = (16, 12, 28)
GLASS_LIGHT = (38, 30, 58)
CREAM = (255, 248, 231)
INK = (28, 18, 34)
RED = (215, 38, 61)
GREEN = (58, 189, 108)
TEAL = (46, 196, 182)
GREY = (150, 140, 160)

# ---------------------------------------------------------------------------
# Small drawing helpers
# ---------------------------------------------------------------------------


def lerp_color(a, b, t):
    """Blend two colours. t=0 gives a, t=1 gives b."""
    t = max(0.0, min(1.0, t))
    return (round(a[0] + (b[0] - a[0]) * t),
            round(a[1] + (b[1] - a[1]) * t),
            round(a[2] + (b[2] - a[2]) * t))


def vertical_gradient(size, top_color, bottom_color):
    """A surface filled with a top-to-bottom gradient."""
    width, height = size
    surface = pygame.Surface(size).convert()
    for y in range(height):
        colour = lerp_color(top_color, bottom_color, y / max(1, height - 1))
        pygame.draw.line(surface, colour, (0, y), (width, y))
    return surface


def gradient_rect(surface, rect, top_color, bottom_color, radius=0):
    """Draw a rounded rectangle filled with a vertical gradient."""
    grad = vertical_gradient(rect.size, top_color, bottom_color)
    if radius:
        # Use a rounded mask so the gradient gets the same corners as the frame.
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        grad = grad.convert_alpha()
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(grad, rect.topleft)


def bezier(p0, p1, p2, steps=16):
    """Points along a quadratic curve -- used for cherry stems and leaves."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        points.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                       u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return points


def edge_fade(size, colour, height, top=True):
    """A transparent-to-colour strip, so symbols fade out at the glass edges."""
    fade = pygame.Surface((size[0], height), pygame.SRCALPHA)
    for y in range(height):
        t = y / max(1, height - 1)
        alpha = int(235 * ((1 - t) ** 1.6)) if top else int(235 * (t ** 1.6))
        pygame.draw.line(fade, (*colour, alpha), (0, y), (size[0], y))
    return fade


def load_font(size, bold=False):
    """Pick a nice font if the system has one, otherwise fall back to pygame's."""
    candidates = ["Impact", "Haettenschweiler", "Arial Black", "DejaVu Sans",
                  "Verdana", "Helvetica", "Arial"]
    for name in candidates:
        path = pygame.font.match_font(name, bold=bold)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def draw_text(surface, text, font, colour, center=None, midleft=None, midright=None, shadow=None):
    """Blit text with an optional drop shadow, anchored centre, left or right."""

    def place(rendered, offset=0):
        rect = rendered.get_rect()
        if center is not None:
            rect.center = (center[0] + offset, center[1] + offset)
        elif midleft is not None:
            rect.midleft = (midleft[0] + offset, midleft[1] + offset)
        else:
            rect.midright = (midright[0] + offset, midright[1] + offset)
        return rect

    if shadow:
        shade = font.render(text, True, shadow)
        surface.blit(shade, place(shade, 2))
    label = font.render(text, True, colour)
    rect = place(label)
    surface.blit(label, rect)
    return rect


# ---------------------------------------------------------------------------
# Sound. Every effect is synthesised at start-up, so there are no asset files
# to ship. If the machine has no audio device the whole thing quietly no-ops.
# ---------------------------------------------------------------------------


def _wave(freq, ms, volume=0.5, shape="sine", decay=True):
    """Build one tone as raw 16-bit samples."""
    rate, _, channels = pygame.mixer.get_init()
    total = max(1, int(rate * ms / 1000))
    attack = max(1, int(rate * 0.004))
    samples = array.array("h")
    for i in range(total):
        phase = (freq * i / rate) % 1.0
        if shape == "sine":
            value = math.sin(2 * math.pi * phase)
        elif shape == "square":
            value = 1.0 if phase < 0.5 else -1.0
        elif shape == "saw":
            value = 2 * phase - 1
        else:  # noise
            value = random.uniform(-1.0, 1.0)
        if decay:
            envelope = (1 - i / total) ** 2
        else:
            envelope = min(1.0, i / attack, (total - i) / attack)
        sample = int(max(-1.0, min(1.0, value * envelope * volume)) * 32767)
        samples.append(sample)
        if channels == 2:
            samples.append(sample)
    return samples


class SoundBank:
    """Holds the synthesised effects and swallows any audio problems."""

    def __init__(self):
        self.enabled = False
        self.muted = False
        self.sounds = {}
        if pygame.mixer.get_init() is None:
            return
        try:
            self.sounds["click"] = self._sound(_wave(880, 45, 0.30, "square"))
            self.sounds["lever"] = self._sound(_wave(220, 130, 0.30, "saw"))
            self.sounds["stop"] = self._sound(_wave(150, 110, 0.45, "square"))
            self.sounds["coin"] = self._sound(_wave(1560, 90, 0.25) + _wave(2100, 70, 0.20))
            # A little rising arpeggio for a win.
            chime = array.array("h")
            for note in (523, 659, 784, 1047):
                chime += _wave(note, 110, 0.28)
            self.sounds["win"] = self._sound(chime)
            self.sounds["lose"] = self._sound(_wave(196, 180, 0.22, "square"))
            # The spin loop has to contain a whole number of cycles or it clicks.
            whir = _wave(70, 400, 0.14, "saw", decay=False)
            self.sounds["whir"] = self._sound(whir)
            self.enabled = True
        except (pygame.error, ValueError):
            self.enabled = False

    @staticmethod
    def _sound(samples):
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def play(self, name, loops=0):
        if self.enabled and not self.muted and name in self.sounds:
            self.sounds[name].play(loops=loops)

    def stop(self, name):
        if self.enabled and name in self.sounds:
            self.sounds[name].stop()

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            for sound in self.sounds.values():
                sound.stop()
        return self.muted


# ---------------------------------------------------------------------------
# Symbol art. The rules still speak in A/B/C/D, this is only what they look
# like: A=seven (rarest, pays most), B=bell, C=cherry, D=lemon.
# ---------------------------------------------------------------------------

SYMBOL_NAMES = {"A": "SEVEN", "B": "BELL", "C": "CHERRY", "D": "LEMON"}
SYMBOL_ACCENT = {"A": (247, 200, 84), "B": (240, 166, 56), "C": (226, 62, 88), "D": (206, 206, 58)}

SUPERSAMPLE = 3  # draw big, shrink down -> cheap anti-aliasing


def _scaled(points, size):
    return [(x * size, y * size) for x, y in points]


def _draw_seven(surface, size):
    body = [(0.20, 0.14), (0.83, 0.14), (0.83, 0.29), (0.58, 0.88),
            (0.37, 0.88), (0.60, 0.31), (0.20, 0.31)]
    points = _scaled(body, size)
    pygame.draw.polygon(surface, RED, points)
    pygame.draw.polygon(surface, (150, 18, 38), points, int(size * 0.055))
    pygame.draw.polygon(surface, GOLD, points, int(size * 0.030))
    # A highlight down the leg so the digit does not look flat.
    pygame.draw.line(surface, (255, 120, 140), (size * 0.66, size * 0.36),
                     (size * 0.47, size * 0.82), int(size * 0.035))


def _draw_bell(surface, size):
    # Sweep out the bell's profile, then mirror it for the other side.
    left, right = [], []
    steps = 20
    for i in range(steps):
        t = i / (steps - 1)
        y = 0.20 + 0.52 * t
        half = 0.09 + 0.27 * (t ** 2)
        left.append((0.5 - half, y))
        right.append((0.5 + half, y))
    body = _scaled(left + right[::-1], size)
    pygame.draw.polygon(surface, GOLD, body)
    pygame.draw.polygon(surface, GOLD_DARK, body, int(size * 0.035))
    # Rim, clapper and the little knob on top.
    rim = pygame.Rect(size * 0.10, size * 0.695, size * 0.80, size * 0.095)
    pygame.draw.rect(surface, GOLD, rim, border_radius=int(size * 0.045))
    pygame.draw.rect(surface, GOLD_DARK, rim, int(size * 0.032), border_radius=int(size * 0.045))
    pygame.draw.circle(surface, GOLD, (size * 0.5, size * 0.855), size * 0.078)
    pygame.draw.circle(surface, GOLD_DARK, (size * 0.5, size * 0.855), size * 0.078, int(size * 0.030))
    pygame.draw.circle(surface, GOLD, (size * 0.5, size * 0.175), size * 0.058)
    pygame.draw.circle(surface, GOLD_DARK, (size * 0.5, size * 0.175), size * 0.058, int(size * 0.028))
    # Shine on the left shoulder.
    pygame.draw.ellipse(surface, GOLD_LIGHT,
                        pygame.Rect(size * 0.31, size * 0.40, size * 0.10, size * 0.24))


def _draw_cherry(surface, size):
    stem_w = max(2, int(size * 0.040))
    for control, end in (((0.33, 0.30), (0.30, 0.52)), ((0.72, 0.32), (0.70, 0.56))):
        pygame.draw.lines(surface, (74, 142, 56), False,
                          _scaled(bezier((0.52, 0.13), control, end), size), stem_w)
    # Leaf, made from two curves back to back.
    leaf = bezier((0.52, 0.14), (0.68, 0.02), (0.88, 0.13)) + \
        bezier((0.88, 0.13), (0.70, 0.20), (0.52, 0.14))
    pygame.draw.polygon(surface, GREEN, _scaled(leaf, size))
    pygame.draw.polygon(surface, (32, 118, 62), _scaled(leaf, size), max(2, int(size * 0.022)))
    for (cx, cy, r) in ((0.31, 0.68, 0.195), (0.69, 0.72, 0.170)):
        pygame.draw.circle(surface, RED, (size * cx, size * cy), size * r)
        pygame.draw.circle(surface, (146, 16, 36), (size * cx, size * cy), size * r, int(size * 0.030))
        pygame.draw.ellipse(surface, (255, 158, 172),
                            pygame.Rect(size * (cx - r * 0.55), size * (cy - r * 0.62),
                                        size * r * 0.50, size * r * 0.38))


def _draw_lemon(surface, size):
    # An ellipse tilted off the horizontal, built as a polygon so it can rotate.
    cx, cy, a, b, tilt = 0.50, 0.54, 0.37, 0.245, math.radians(-20)
    cos_t, sin_t = math.cos(tilt), math.sin(tilt)
    outline = []
    for i in range(48):
        angle = 2 * math.pi * i / 48
        x, y = a * math.cos(angle), b * math.sin(angle)
        outline.append((cx + x * cos_t - y * sin_t, cy + x * sin_t + y * cos_t))
    points = _scaled(outline, size)
    # The pointed nubs at each end.
    for direction in (1, -1):
        tip_x = cx + direction * (a + 0.040) * cos_t
        tip_y = cy + direction * (a + 0.040) * sin_t
        pygame.draw.circle(surface, (232, 186, 22), (size * tip_x, size * tip_y), size * 0.042)
    pygame.draw.polygon(surface, (245, 199, 30), points)
    pygame.draw.polygon(surface, (186, 138, 12), points, int(size * 0.035))
    pygame.draw.ellipse(surface, (255, 238, 148),
                        pygame.Rect(size * 0.28, size * 0.36, size * 0.22, size * 0.12))


SYMBOL_ART = {"A": _draw_seven, "B": _draw_bell, "C": _draw_cherry, "D": _draw_lemon}

_art_cache = {}
_tile_cache = {}


def symbol_art(letter, size):
    """The icon on its own, with a transparent background."""
    key = (letter, size)
    if key not in _art_cache:
        big = size * SUPERSAMPLE
        canvas = pygame.Surface((big, big), pygame.SRCALPHA)
        SYMBOL_ART[letter](canvas, big)
        _art_cache[key] = pygame.transform.smoothscale(canvas, (size, size))
    return _art_cache[key]


def symbol_tile(letter, size=TILE):
    """A finished reel tile: cream face, coloured ring, icon in the middle."""
    key = (letter, size)
    if key not in _tile_cache:
        tile = pygame.Surface((size, size), pygame.SRCALPHA)
        radius = int(size * 0.14)
        rect = pygame.Rect(0, 0, size, size)
        gradient_rect(tile, rect, CREAM, (226, 212, 188), radius=radius)
        accent = SYMBOL_ACCENT[letter]
        pygame.draw.rect(tile, accent, rect.inflate(-8, -8), max(2, size // 24),
                         border_radius=radius - 3)
        pygame.draw.rect(tile, (120, 96, 70), rect, max(2, size // 44), border_radius=radius)
        art = symbol_art(letter, int(size * 0.66))
        tile.blit(art, art.get_rect(center=(size // 2, int(size * 0.5))))
        _tile_cache[key] = tile
    return _tile_cache[key]


# Weighted pool so the symbols flying past the window appear at the same rate
# they actually land -- sevens stay rare even mid-spin.
SYMBOL_POOL = [letter for letter, count in symbol_count.items() for _ in range(count)]

_fade_cache = {}


def faded_tile(letter, alpha):
    """A tile at reduced opacity, cached in coarse steps so spinning is cheap."""
    alpha = max(0, min(255, int(round(alpha / 15.0)) * 15))
    key = (letter, alpha)
    if key not in _fade_cache:
        tile = symbol_tile(letter).copy()
        tile.set_alpha(alpha)
        _fade_cache[key] = tile
    return _fade_cache[key]


class Reel:
    """One column of the machine.

    `pos` is a floating point index into a long strip of symbols. Whole numbers
    line the tiles up with the window, the fraction is how far the strip has
    scrolled between two tiles. Row i shows strip[base - i], so as pos grows the
    symbols travel downwards like a real reel.
    """

    STRIP_LEN = 30
    SPIN_SPEED = 18.0      # tiles per second
    STOP_TIME = 0.65       # how long the slow-down takes
    SETTLE_TIME = 0.22     # the little bounce after landing

    def __init__(self, x, y, rows):
        self.x = x
        self.y = y
        self.rows = rows
        self.strip = [random.choice(SYMBOL_POOL) for _ in range(self.STRIP_LEN)]
        self.pos = float(random.randrange(self.STRIP_LEN))
        self.state = "idle"          # idle | spinning | stopping
        self.speed = 0.0
        self.blur = 0.0
        self.start_pos = 0.0
        self.target = 0.0
        self.elapsed = 0.0

    def start(self):
        self.state = "spinning"
        self.speed = self.SPIN_SPEED * random.uniform(0.94, 1.06)

    def stop_at(self, result):
        """Write this column's result into the strip a few tiles ahead, then
        glide to it. Those tiles are still above the window, so nothing pops."""
        target = math.floor(self.pos) + 6
        for offset, symbol in enumerate(result):   # result[0] is the top row
            self.strip[(target - offset) % self.STRIP_LEN] = symbol
        self.start_pos = self.pos
        self.target = float(target)
        self.elapsed = 0.0
        self.state = "stopping"

    @property
    def spinning(self):
        return self.state != "idle"

    def update(self, dt):
        """Advance the reel. Returns True on the frame it comes to rest."""
        previous = self.pos
        landed = False

        if self.state == "spinning":
            self.pos += self.speed * dt
        elif self.state == "stopping":
            self.elapsed += dt
            if self.elapsed < self.STOP_TIME:
                # Ease out quadratically -- its starting slope roughly matches
                # the spin speed, so the hand-off has no visible jerk.
                t = self.elapsed / self.STOP_TIME
                self.pos = self.start_pos + (self.target - self.start_pos) * (1 - (1 - t) ** 2)
            else:
                t = (self.elapsed - self.STOP_TIME) / self.SETTLE_TIME
                if t >= 1.0:
                    self.pos = self.target
                    self.state = "idle"
                    landed = True
                else:
                    self.pos = self.target + 0.09 * math.sin(t * 2 * math.pi) * (1 - t)

        # Blur is driven by however fast the reel actually moved this frame.
        speed = abs(self.pos - previous) / max(dt, 1e-6)
        self.blur = min(1.0, speed / self.SPIN_SPEED)
        return landed

    def visible_symbols(self):
        """The three symbols currently sitting in the window, top to bottom."""
        base = math.floor(self.pos + 0.5)
        return [self.strip[(base - i) % self.STRIP_LEN] for i in range(self.rows)]

    def draw(self, surface):
        base = math.floor(self.pos)
        frac = self.pos - base
        for i in range(-1, self.rows + 1):
            symbol = self.strip[(base - i) % self.STRIP_LEN]
            y = self.y + (i + frac) * PITCH
            if self.blur > 0.05:
                # Ghost copies above and below smear the tile into a streak.
                ghost = faded_tile(symbol, 80 * self.blur)
                surface.blit(ghost, (self.x, y - 0.36 * PITCH))
                surface.blit(ghost, (self.x, y + 0.36 * PITCH))
                surface.blit(faded_tile(symbol, 255 - 85 * self.blur), (self.x, y))
            else:
                surface.blit(symbol_tile(symbol), (self.x, y))


class Button:
    """A chunky arcade button."""

    def __init__(self, rect, label, colour, hint=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.colour = colour
        self.hint = hint
        self.enabled = True
        self.hover = False
        self.pressed = 0.0   # seconds left of the "pushed in" look

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)

    def push(self):
        self.pressed = 0.12

    def update(self, dt, mouse_pos):
        self.hover = self.enabled and self.rect.collidepoint(mouse_pos)
        self.pressed = max(0.0, self.pressed - dt)

    def draw(self, surface, font, hint_font):
        rect = self.rect.copy()
        down = self.pressed > 0
        if down:
            rect.y += 3
        else:
            # Drop shadow gives the button its height.
            pygame.draw.rect(surface, (20, 6, 14), rect.move(0, 5), border_radius=12)

        top = self.colour if self.enabled else (92, 86, 98)
        bottom = lerp_color(top, (0, 0, 0), 0.45)
        if self.hover and not down and self.enabled:
            top = lerp_color(top, (255, 255, 255), 0.18)
        gradient_rect(surface, rect, top, bottom, radius=12)
        pygame.draw.rect(surface, GOLD if self.enabled else (120, 112, 124), rect, 3, border_radius=12)

        text_colour = CREAM if self.enabled else (160, 154, 166)
        centre = rect.center if not self.hint else (rect.centerx, rect.centery - 8)
        draw_text(surface, self.label, font, text_colour, center=centre, shadow=(0, 0, 0))
        if self.hint:
            draw_text(surface, self.hint, hint_font, lerp_color(text_colour, INK, 0.35),
                      center=(rect.centerx, rect.centery + 15))


class Coin:
    """A coin tossed out of the machine when you win."""

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = random.uniform(-190, 190)
        self.vy = random.uniform(-580, -300)
        self.spin = random.uniform(0, math.pi)
        self.spin_speed = random.uniform(6, 12)
        self.radius = random.randint(9, 15)
        self.life = random.uniform(1.4, 2.2)

    def update(self, dt):
        self.vy += 1500 * dt          # gravity
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.spin += self.spin_speed * dt
        self.life -= dt
        return self.life > 0

    def draw(self, surface):
        # Squashing the width as it turns makes the coin look like it is flipping.
        width = max(2, abs(math.cos(self.spin)) * self.radius * 2)
        rect = pygame.Rect(0, 0, width, self.radius * 2)
        rect.center = (int(self.x), int(self.y))
        pygame.draw.ellipse(surface, GOLD, rect)
        pygame.draw.ellipse(surface, GOLD_DARK, rect, 2)


# ---------------------------------------------------------------------------
# The machine
# ---------------------------------------------------------------------------

LEVER_X = CAB.right + 44
LEVER_TOP = 300
LEVER_BASE = 560
LEVER_TRAVEL = 120


class SlotMachine:
    """Draws the cabinet and runs the same game loop the console version does."""

    def __init__(self, sounds):
        self.sounds = sounds

        self.font_marquee = load_font(50, bold=True)
        self.font_win = load_font(38, bold=True)
        self.font_big = load_font(30, bold=True)
        self.font_med = load_font(22, bold=True)
        self.font_small = load_font(17, bold=True)
        self.font_tiny = load_font(13, bold=True)

        # Money and the bet, exactly the quantities the console version tracks.
        self.balance = 0
        self.bet = 10
        self.lines = MAX_LINES
        self.state = "deposit"        # deposit | idle | spinning | cashout
        self.deposit_text = ""
        self.message = "Insert coins to play"
        self.message_colour = CREAM

        first_x = GLASS.x + GLASS_PAD
        first_y = GLASS.y + GLASS_PAD
        self.reels = [Reel(first_x + i * PITCH, first_y, ROWS) for i in range(COLS)]

        # Everything about the spin currently in flight.
        self.columns = []
        self.winnings = 0
        self.winning_lines = []
        self.win_shown = 0.0          # the counter that ticks up to `winnings`
        self.total_bet = 0
        self.spin_time = 0.0
        self.stop_times = []
        self.stopped = 0
        self.coins = []
        self.lever = 0.0
        self.glow = 0.0               # drives the pulsing win highlight
        self.bulb_phase = 0.0

        self.buttons = {
            "lines_down": Button((78, 742, 86, 56), "LINES -", (72, 66, 92), "DOWN"),
            "lines_up": Button((170, 742, 86, 56), "LINES +", (72, 66, 92), "UP"),
            "bet_down": Button((272, 742, 86, 56), "BET -", (72, 66, 92), "LEFT"),
            "bet_up": Button((364, 742, 86, 56), "BET +", (72, 66, 92), "RIGHT"),
            "spin": Button((470, 742, 200, 56), "SPIN", RED, "SPACE"),
            "cash_out": Button((682, 742, 150, 56), "CASH OUT", (58, 92, 74), "Q"),
        }

        self.background = self._build_background()
        self.fade_top = edge_fade((GLASS.w - 6, 0), GLASS_DARK, 46, top=True)
        self.fade_bottom = edge_fade((GLASS.w - 6, 0), GLASS_DARK, 46, top=False)

    # -- setup ------------------------------------------------------------

    def _build_background(self):
        """The room behind the cabinet: gradient floor plus a warm spotlight."""
        surface = vertical_gradient((WIDTH, HEIGHT), BG_TOP, BG_BOTTOM)
        glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for radius, alpha in ((520, 10), (420, 12), (320, 14), (220, 16)):
            pygame.draw.circle(glow, (255, 170, 90, alpha), (WIDTH // 2, 300), radius)
        surface.blit(glow, (0, 0))
        return surface

    # -- money and bets ---------------------------------------------------

    @property
    def stake(self):
        return self.bet * self.lines

    @property
    def can_spin(self):
        return self.state == "idle" and self.stake <= self.balance

    def adjust_bet(self, delta):
        new_bet = max(MIN_BET, min(MAX_BET, self.bet + delta))
        if new_bet != self.bet:
            self.bet = new_bet
            self.sounds.play("click")
        self._clear_win()
        self._refresh_stake_message()

    def adjust_lines(self, delta):
        new_lines = max(1, min(MAX_LINES, self.lines + delta))
        if new_lines != self.lines:
            self.lines = new_lines
            self.sounds.play("click")
        self._clear_win()
        self._refresh_stake_message()

    def _refresh_stake_message(self):
        if self.state != "idle":
            return
        if self.stake > self.balance:
            self.set_message(f"Total bet ${self.stake} is more than your ${self.balance} balance", RED)
        else:
            self.set_message(f"Betting ${self.bet} on {self.lines} line{'s' if self.lines > 1 else ''}"
                             f"  ->  ${self.stake} total", CREAM)

    def _clear_win(self):
        """Drop the last result's celebration once the player touches the bet."""
        self.winnings = 0
        self.winning_lines = []
        self.win_shown = 0.0
        self.glow = 0.0

    def set_message(self, text, colour=CREAM):
        self.message = text
        self.message_colour = colour

    # -- the spin ---------------------------------------------------------

    def spin(self):
        """Same sequence as the console spin(): take the stake, roll the
        columns, work out the winnings -- only now it happens on screen."""
        if not self.can_spin:
            if self.balance < MIN_BET:
                self.set_message("Out of funds. Cash out to leave the machine.", RED)
            else:
                self.set_message(f"Not enough money for a ${self.stake} bet "
                                 f"(balance ${self.balance})", RED)
            return

        self.total_bet = self.stake
        self.balance -= self.total_bet
        self.columns = get_slot_machine_spin(ROWS, COLS, symbol_count)
        self.winnings, self.winning_lines = check_winnings(
            self.columns, self.lines, self.bet, symbol_value)

        self.state = "spinning"
        self.spin_time = 0.0
        self.stopped = 0
        self.win_shown = 0.0
        self.glow = 0.0
        self.lever = 1.0
        self.stop_times = [0.75, 1.15, 1.55]
        if self._teasing():
            # First two columns already match on a line you paid for: let the
            # last reel hang for a moment, the way a real machine taunts you.
            self.stop_times[2] += 1.0
        for reel in self.reels:
            reel.start()
        self.sounds.play("lever")
        self.sounds.play("whir", loops=-1)
        self.set_message("Good luck...", GOLD)

    def _teasing(self):
        return any(self.columns[0][line] == self.columns[1][line] for line in range(self.lines))

    def _finish_spin(self):
        self.sounds.stop("whir")
        self.balance += self.winnings
        self.state = "idle"
        if self.winnings:
            lines = ", ".join(str(line) for line in self.winning_lines)
            plural = "s" if len(self.winning_lines) > 1 else ""
            self.set_message(f"WIN  ${self.winnings}   on line{plural} {lines}", GOLD)
            self.sounds.play("win")
            for _ in range(26):
                self.coins.append(Coin(random.uniform(GLASS.x, GLASS.right), GLASS.bottom - 40))
        else:
            self.set_message("No win this time -- spin again", GREY)
            self.sounds.play("lose")

    def cash_out(self):
        self.sounds.stop("whir")
        self.state = "cashout"
        self.set_message(f"You left with ${self.balance}", GOLD)

    # -- input ------------------------------------------------------------

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            return self._handle_key(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_click(event.pos)
        return True

    def _handle_key(self, event):
        if self.state == "deposit":
            if event.unicode.isdigit() and len(self.deposit_text) < 7:
                self.deposit_text += event.unicode
                self.sounds.play("click")
            elif event.key == pygame.K_BACKSPACE:
                self.deposit_text = self.deposit_text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._confirm_deposit()
            elif event.key == pygame.K_ESCAPE:
                return False
            return True

        if self.state == "cashout":
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.state = "deposit"
                self.deposit_text = ""
                self.balance = 0
                self.set_message("Insert coins to play")
            elif event.key in (pygame.K_ESCAPE, pygame.K_q):
                return False
            return True

        if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.buttons["spin"].push()
            self.spin()
        elif event.key in (pygame.K_q, pygame.K_ESCAPE) and self.state == "idle":
            self.cash_out()
        elif event.key == pygame.K_m:
            self.set_message("Sound muted" if self.sounds.toggle_mute() else "Sound on")
        elif self.state == "idle":
            step = 10 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1
            if event.key == pygame.K_LEFT:
                self.buttons["bet_down"].push()
                self.adjust_bet(-step)
            elif event.key == pygame.K_RIGHT:
                self.buttons["bet_up"].push()
                self.adjust_bet(step)
            elif event.key == pygame.K_UP:
                self.buttons["lines_up"].push()
                self.adjust_lines(1)
            elif event.key == pygame.K_DOWN:
                self.buttons["lines_down"].push()
                self.adjust_lines(-1)
        return True

    def _handle_click(self, pos):
        if self.state == "deposit":
            return
        if self.state == "cashout":
            return
        for name, button in self.buttons.items():
            if button.hit(pos):
                button.push()
                if name == "spin":
                    self.spin()
                elif name == "cash_out":
                    self.cash_out()
                elif name == "bet_up":
                    self.adjust_bet(1)
                elif name == "bet_down":
                    self.adjust_bet(-1)
                elif name == "lines_up":
                    self.adjust_lines(1)
                elif name == "lines_down":
                    self.adjust_lines(-1)
                return
        # The lever works too, of course.
        knob = pygame.Vector2(LEVER_X, LEVER_TOP + self.lever * LEVER_TRAVEL)
        if knob.distance_to(pos) <= 34:
            self.spin()

    def _confirm_deposit(self):
        """Mirrors deposit() from the console game: digits only, above zero."""
        if not self.deposit_text.isdigit():
            self.set_message("Please enter a number", RED)
            return
        amount = int(self.deposit_text)
        if amount <= 0:
            self.set_message("Amount must be greater than 0", RED)
            return
        self.balance = amount
        self.bet = max(MIN_BET, min(MAX_BET, min(self.bet, amount)))
        self.lines = min(MAX_LINES, self.lines)
        self.state = "idle"
        self.sounds.play("coin")
        self._refresh_stake_message()

    # -- update -----------------------------------------------------------

    def update(self, dt, mouse_pos):
        self.bulb_phase += dt * (7.0 if self.winning_lines and self.state == "idle" else 2.6)
        self.lever = max(0.0, self.lever - dt * 1.3)

        if self.state == "spinning":
            self.spin_time += dt
            while self.stopped < COLS and self.spin_time >= self.stop_times[self.stopped]:
                self.reels[self.stopped].stop_at(self.columns[self.stopped])
                self.stopped += 1
            for reel in self.reels:
                if reel.update(dt):
                    self.sounds.play("stop")
            if self.stopped == COLS and not any(reel.spinning for reel in self.reels):
                self._finish_spin()
        else:
            for reel in self.reels:
                reel.update(dt)

        if self.winning_lines and self.state == "idle":
            self.glow += dt
            self.win_shown = min(self.winnings, self.win_shown + self.winnings * dt * 2.2)

        self.coins = [coin for coin in self.coins if coin.update(dt) and coin.y < HEIGHT + 60]

        for name, button in self.buttons.items():
            button.enabled = self.can_spin if name == "spin" else self.state == "idle"
            button.update(dt, mouse_pos)

    # -- drawing ----------------------------------------------------------

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        self._draw_cabinet(surface)
        self._draw_marquee(surface)
        self._draw_glass(surface)
        self._draw_payline_lamps(surface)
        self._draw_paytable(surface)
        self._draw_ribbon(surface)
        self._draw_panel(surface)
        self._draw_lever(surface)
        for coin in self.coins:
            coin.draw(surface)
        if self.state == "deposit":
            self._draw_overlay(surface, "INSERT COINS", deposit=True)
        elif self.state == "cashout":
            self._draw_overlay(surface, "CASHED OUT", deposit=False)

    @staticmethod
    def _perimeter_points(rect, spacing):
        points = []
        for x in range(rect.left, rect.right, spacing):
            points.append((x, rect.top))
        for y in range(rect.top, rect.bottom, spacing):
            points.append((rect.right, y))
        for x in range(rect.right, rect.left, -spacing):
            points.append((x, rect.bottom))
        for y in range(rect.bottom, rect.top, -spacing):
            points.append((rect.left, y))
        return points

    def _draw_cabinet(self, surface):
        # Soft shadow on the floor so the cabinet does not look pasted on.
        shadow = pygame.Surface((CAB.w + 180, 70), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 120), shadow.get_rect())
        surface.blit(shadow, (CAB.x - 90, CAB.bottom - 26))

        gradient_rect(surface, CAB, CAB_LIGHT, CAB_DARK, radius=30)
        pygame.draw.rect(surface, GOLD, CAB, 6, border_radius=30)
        pygame.draw.rect(surface, CAB_EDGE, CAB.inflate(-12, -12), 2, border_radius=26)

        # The dark faceplate everything else is mounted on.
        face = pygame.Rect(CAB.x + 16, MARQUEE.bottom + 10, CAB.w - 32, CAB.bottom - MARQUEE.bottom - 26)
        gradient_rect(surface, face, (66, 12, 28), (36, 6, 16), radius=22)
        pygame.draw.rect(surface, GOLD_DARK, face, 2, border_radius=22)

        for corner in ((CAB.x + 26, CAB.y + 26), (CAB.right - 26, CAB.y + 26),
                       (CAB.x + 26, CAB.bottom - 26), (CAB.right - 26, CAB.bottom - 26)):
            pygame.draw.circle(surface, GOLD_DARK, corner, 7)
            pygame.draw.circle(surface, GOLD_LIGHT, corner, 7, 2)

    def _draw_marquee(self, surface):
        gradient_rect(surface, MARQUEE, (104, 16, 40), (44, 6, 20), radius=16)
        pygame.draw.rect(surface, GOLD, MARQUEE, 3, border_radius=16)

        # Chasing bulbs around the sign.
        for index, point in enumerate(self._perimeter_points(MARQUEE.inflate(-18, -18), 36)):
            brightness = 0.5 + 0.5 * math.sin(self.bulb_phase * 3 - index * 0.55)
            colour = lerp_color((116, 62, 22), GOLD_LIGHT, brightness)
            if brightness > 0.75:
                glow = pygame.Surface((26, 26), pygame.SRCALPHA)
                pygame.draw.circle(glow, (255, 220, 130, 70), (13, 13), 13)
                surface.blit(glow, (point[0] - 13, point[1] - 13))
            pygame.draw.circle(surface, colour, point, 6)

        draw_text(surface, "LUCKY SEVENS", self.font_marquee, GOLD,
                  center=(MARQUEE.centerx, MARQUEE.centery - 9), shadow=(40, 4, 12))
        draw_text(surface, "MATCH 3 ACROSS   -   UP TO 3 LINES", self.font_tiny,
                  lerp_color(CREAM, CAB_DARK, 0.25), center=(MARQUEE.centerx, MARQUEE.centery + 26))

    def _draw_glass(self, surface):
        frame = GLASS.inflate(16, 16)
        gradient_rect(surface, frame, GOLD, GOLD_DARK, radius=20)
        pygame.draw.rect(surface, (90, 60, 10), frame, 2, border_radius=20)
        gradient_rect(surface, GLASS, GLASS_LIGHT, GLASS_DARK, radius=10)

        # Reels are clipped to the window so half-tiles get cut off by the frame.
        previous_clip = surface.get_clip()
        surface.set_clip(GLASS.inflate(-4, -4))
        for reel in self.reels:
            reel.draw(surface)

        # Dim the rows that did not win so the paying line stands out.
        if self.winning_lines and self.state == "idle":
            dim = pygame.Surface((GLASS.w - 8, TILE + TILE_GAP), pygame.SRCALPHA)
            dim.fill((6, 4, 14, 120))
            for row in range(ROWS):
                if row + 1 not in self.winning_lines:
                    surface.blit(dim, (GLASS.x + 4, GLASS.y + GLASS_PAD + row * PITCH - TILE_GAP // 2))

        surface.blit(self.fade_top, (GLASS.x + 3, GLASS.y + 3))
        surface.blit(self.fade_bottom, (GLASS.x + 3, GLASS.bottom - 49))
        surface.set_clip(previous_clip)

        # A slanted reflection across the glass.
        shine = pygame.Surface(GLASS.size, pygame.SRCALPHA)
        pygame.draw.polygon(shine, (255, 255, 255, 16),
                            [(0, GLASS.h * 0.62), (GLASS.w * 0.55, 0),
                             (GLASS.w * 0.80, 0), (0, GLASS.h * 0.92)])
        surface.blit(shine, GLASS.topleft)

        if self.winning_lines and self.state == "idle":
            pulse = 0.5 + 0.5 * math.sin(self.glow * 7)
            for line in self.winning_lines:
                row = pygame.Rect(GLASS.x + GLASS_PAD - 7,
                                  GLASS.y + GLASS_PAD + (line - 1) * PITCH - 7,
                                  COLS * TILE + (COLS - 1) * TILE_GAP + 14, TILE + 14)
                halo = pygame.Surface(row.size, pygame.SRCALPHA)
                pygame.draw.rect(halo, (255, 214, 120, int(40 + 50 * pulse)),
                                 halo.get_rect(), border_radius=18)
                surface.blit(halo, row.topleft)
                pygame.draw.rect(surface, lerp_color(GOLD, GOLD_LIGHT, pulse), row,
                                 5, border_radius=18)

        pygame.draw.rect(surface, (10, 6, 18), GLASS, 3, border_radius=10)

    def _draw_payline_lamps(self, surface):
        for row in range(ROWS):
            centre_y = GLASS.y + GLASS_PAD + row * PITCH + TILE // 2
            active = row < self.lines
            winning = (row + 1) in self.winning_lines and self.state == "idle"
            if winning:
                pulse = 0.5 + 0.5 * math.sin(self.glow * 7)
                colour = lerp_color(GOLD, GOLD_LIGHT, pulse)
            elif active:
                colour = GOLD
            else:
                colour = (86, 62, 58)

            pygame.draw.circle(surface, colour, ((CAB.x + GLASS.x) // 2, centre_y), 15)
            pygame.draw.circle(surface, (40, 8, 18), ((CAB.x + GLASS.x) // 2, centre_y), 15, 2)
            draw_text(surface, str(row + 1), self.font_small,
                      INK if (active or winning) else (140, 120, 118),
                      center=((CAB.x + GLASS.x) // 2, centre_y))
            pygame.draw.circle(surface, colour, ((GLASS.right + PAYTABLE.x) // 2, centre_y), 9)
            pygame.draw.circle(surface, (40, 8, 18), ((GLASS.right + PAYTABLE.x) // 2, centre_y), 9, 2)

    def _draw_paytable(self, surface):
        gradient_rect(surface, PAYTABLE, (52, 10, 26), (26, 6, 14), radius=16)
        pygame.draw.rect(surface, GOLD_DARK, PAYTABLE, 2, border_radius=16)
        draw_text(surface, "PAYTABLE", self.font_med, GOLD,
                  center=(PAYTABLE.centerx, PAYTABLE.y + 28))
        pygame.draw.line(surface, GOLD_DARK, (PAYTABLE.x + 18, PAYTABLE.y + 48),
                         (PAYTABLE.right - 18, PAYTABLE.y + 48), 2)

        winning_symbols = set()
        if self.winning_lines and self.state == "idle":
            winning_symbols = {self.columns[0][line - 1] for line in self.winning_lines}

        # Ordered by how much they pay, best first.
        for index, letter in enumerate(sorted(symbol_value, key=symbol_value.get, reverse=True)):
            row = pygame.Rect(PAYTABLE.x + 10, PAYTABLE.y + 60 + index * 72, PAYTABLE.w - 20, 66)
            if letter in winning_symbols:
                pulse = 0.5 + 0.5 * math.sin(self.glow * 7)
                highlight = pygame.Surface(row.size, pygame.SRCALPHA)
                highlight.fill((255, 214, 120, int(30 + 40 * pulse)))
                surface.blit(highlight, row.topleft)
                pygame.draw.rect(surface, GOLD, row, 2, border_radius=10)
            icon = symbol_art(letter, 52)
            surface.blit(icon, icon.get_rect(center=(row.x + 36, row.centery)))
            draw_text(surface, SYMBOL_NAMES[letter], self.font_small, CREAM,
                      midleft=(row.x + 74, row.centery - 10))
            draw_text(surface, f"x{symbol_count[letter]} per reel", self.font_tiny, GREY,
                      midleft=(row.x + 74, row.centery + 12))
            draw_text(surface, f"x{symbol_value[letter]}", self.font_big, GOLD,
                      center=(row.right - 34, row.centery))

        footer = PAYTABLE.y + 60 + 4 * 72 + 12
        draw_text(surface, "3 OF A KIND ON AN ACTIVE LINE", self.font_tiny, lerp_color(CREAM, GREY, 0.4),
                  center=(PAYTABLE.centerx, footer))
        draw_text(surface, "PAYS  MULTIPLIER x BET PER LINE", self.font_tiny, lerp_color(CREAM, GREY, 0.4),
                  center=(PAYTABLE.centerx, footer + 22))
        draw_text(surface, f"TOP LINE PAYS  ${symbol_value['A'] * self.bet}", self.font_small, TEAL,
                  center=(PAYTABLE.centerx, footer + 52))

    def _draw_ribbon(self, surface):
        gradient_rect(surface, RIBBON, (24, 14, 34), (14, 8, 20), radius=12)
        pygame.draw.rect(surface, GOLD_DARK, RIBBON, 2, border_radius=12)

        if self.state == "idle" and self.winning_lines:
            plural = "s" if len(self.winning_lines) > 1 else ""
            lines = ", ".join(str(line) for line in self.winning_lines)
            text = f"WIN  ${int(self.win_shown)}   ON LINE{plural.upper()} {lines}"
            colour = lerp_color(GOLD, GOLD_LIGHT, 0.5 + 0.5 * math.sin(self.glow * 7))
            draw_text(surface, text, self.font_win, colour, center=RIBBON.center, shadow=(0, 0, 0))
        else:
            draw_text(surface, self.message, self.font_med, self.message_colour,
                      center=RIBBON.center)

    def _draw_panel(self, surface):
        gradient_rect(surface, PANEL, (78, 72, 90), (38, 34, 48), radius=16)
        pygame.draw.rect(surface, GOLD_DARK, PANEL, 2, border_radius=16)

        readouts = [
            ("BALANCE", f"${self.balance}", GREEN if self.balance else GREY),
            ("BET / LINE", f"${self.bet}", CREAM),
            ("LINES", f"{self.lines} of {MAX_LINES}", CREAM),
            ("TOTAL BET", f"${self.stake}", RED if self.stake > self.balance else GOLD),
        ]
        for index, (label, value, colour) in enumerate(readouts):
            box = pygame.Rect(78 + index * 192, 688, 178, 44)
            gradient_rect(surface, box, (18, 12, 24), (32, 24, 42), radius=9)
            pygame.draw.rect(surface, GOLD_DARK, box, 2, border_radius=9)
            draw_text(surface, label, self.font_tiny, GREY, midleft=(box.x + 12, box.centery))
            draw_text(surface, value, self.font_med, colour, midright=(box.right - 12, box.centery))

        for button in self.buttons.values():
            button.draw(surface, self.font_small, self.font_tiny)

    def _draw_lever(self, surface):
        knob_y = LEVER_TOP + self.lever * LEVER_TRAVEL
        housing = pygame.Rect(LEVER_X - 22, LEVER_BASE - 8, 44, 78)
        gradient_rect(surface, housing, (150, 148, 160), (58, 56, 68), radius=12)
        pygame.draw.rect(surface, (30, 28, 36), housing, 2, border_radius=12)

        pygame.draw.line(surface, (40, 38, 48), (LEVER_X, LEVER_BASE), (LEVER_X, knob_y), 18)
        pygame.draw.line(surface, (196, 198, 210), (LEVER_X, LEVER_BASE), (LEVER_X, knob_y), 11)
        pygame.draw.line(surface, (250, 250, 255), (LEVER_X - 3, LEVER_BASE), (LEVER_X - 3, knob_y), 3)

        pygame.draw.circle(surface, (120, 12, 30), (LEVER_X, knob_y), 27)
        pygame.draw.circle(surface, RED, (LEVER_X, knob_y), 24)
        pygame.draw.circle(surface, GOLD, (LEVER_X, knob_y), 27, 3)
        pygame.draw.ellipse(surface, (255, 150, 165),
                            pygame.Rect(LEVER_X - 14, knob_y - 16, 15, 11))
        draw_text(surface, "PULL", self.font_tiny, GOLD_LIGHT,
                  center=(LEVER_X, housing.bottom + 16))

    def _draw_overlay(self, surface, title, deposit):
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((6, 2, 12, 185))
        surface.blit(veil, (0, 0))

        panel = pygame.Rect(0, 0, 520, 260)
        panel.center = (WIDTH // 2, HEIGHT // 2 - 40)
        gradient_rect(surface, panel, (86, 14, 34), (34, 6, 16), radius=22)
        pygame.draw.rect(surface, GOLD, panel, 4, border_radius=22)
        for index, point in enumerate(self._perimeter_points(panel.inflate(-22, -22), 40)):
            brightness = 0.5 + 0.5 * math.sin(self.bulb_phase * 3 - index * 0.5)
            pygame.draw.circle(surface, lerp_color((116, 62, 22), GOLD_LIGHT, brightness), point, 5)

        draw_text(surface, title, self.font_big, GOLD,
                  center=(panel.centerx, panel.y + 52), shadow=(30, 4, 12))

        if deposit:
            draw_text(surface, "What would you like to deposit?", self.font_small, CREAM,
                      center=(panel.centerx, panel.y + 92))
            field = pygame.Rect(0, 0, 300, 60)
            field.center = (panel.centerx, panel.y + 142)
            gradient_rect(surface, field, (16, 10, 22), (30, 22, 40), radius=10)
            pygame.draw.rect(surface, GOLD_DARK, field, 2, border_radius=10)
            caret = "|" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
            draw_text(surface, f"${self.deposit_text}{caret}", self.font_win, CREAM, center=field.center)
            draw_text(surface, "ENTER to play    -    ESC to quit", self.font_tiny, GREY,
                      center=(panel.centerx, panel.bottom - 28))
        else:
            draw_text(surface, f"You left with ${self.balance}", self.font_win, CREAM,
                      center=(panel.centerx, panel.y + 132))
            draw_text(surface, "ENTER to play again    -    ESC to quit", self.font_tiny, GREY,
                      center=(panel.centerx, panel.bottom - 28))

        if self.message_colour == RED:
            draw_text(surface, self.message, self.font_small, RED,
                      center=(WIDTH // 2, panel.bottom + 40))


def main():
    # Ask for a small mixer buffer before pygame.init() so the clicks are snappy.
    try:
        pygame.mixer.pre_init(22050, -16, 1, 256)
    except pygame.error:
        pass
    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Lucky Sevens - Slot Machine")
    pygame.display.set_icon(symbol_tile("A", 64))
    clock = pygame.time.Clock()

    machine = SlotMachine(SoundBank())

    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)   # cap dt so a stall cannot skip a spin
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif not machine.handle_event(event):
                running = False
        machine.update(dt, pygame.mouse.get_pos())
        machine.draw(screen)
        pygame.display.flip()

    pygame.quit()
    # Same parting line the console version prints.
    print(f"You left with ${machine.balance}")


if __name__ == "__main__":
    main()
