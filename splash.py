# Splash screen and launcher for COA Simulator Pro

"""
COA Simulator Pro launcher

The splash is a Toplevel on the real simulator window. It does not create
its own Tk root, so closing the splash cannot kill the main window.

Leave the original simulator file, which contains class ALUApp, unchanged.
"""

import importlib
import math
import os
import random
import sys
import time
import tkinter as tk
import traceback
from collections import Counter


APP_NAME = "COA Simulator Pro"
APP_TAGLINE = "Variable-width ALU  •  FP8-FP64 FPU  •  Gate-level circuit view"

DEFAULT_MAKERS = [
    ("Achyutanand Dixit", "Lead Developer"),
    ("Payal Gupta", "Testing & Documentation"),
]

GRAPH_VIEWS = ("Dashboard", "Radar & Rose", "Heatmaps", "Timeline")

core = None
ProApp = None
HAVE_MPL = False
np = Figure = LinearSegmentedColormap = MaxNLocator = HEAT = None


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_makers():
    path = os.path.join(app_dir(), "makers.txt")
    makers = []

    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                name, _, role = line.partition("|")
                if name.strip():
                    makers.append((name.strip(), role.strip()))

    except OSError:
        pass

    return makers or list(DEFAULT_MAKERS)


def _rgb(color):
    color = color.lstrip("#")
    return (
        int(color[0:2], 16),
        int(color[2:4], 16),
        int(color[4:6], 16),
    )


def blend(color1, color2, amount):
    amount = max(0.0, min(1.0, amount))
    a = _rgb(color1)
    b = _rgb(color2)

    mixed = tuple(int(a[i] + (b[i] - a[i]) * amount) for i in range(3))
    return "#%02X%02X%02X" % mixed


def _point_along(points, position):
    segments = []
    total_length = 0.0

    for i in range(0, len(points) - 2, 2):
        x0, y0 = points[i], points[i + 1]
        x1, y1 = points[i + 2], points[i + 3]

        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        segments.append((x0, y0, x1, y1, length))
        total_length += length

    if total_length <= 0 or not points:
        return 0, 0

    distance = (position % 1.0) * total_length

    for x0, y0, x1, y1, length in segments:
        if distance <= length or length == 0:
            ratio = 0 if length == 0 else distance / length
            return (
                x0 + (x1 - x0) * ratio,
                y0 + (y1 - y0) * ratio,
            )

        distance -= length

    return points[-2], points[-1]


def _show_error(text):
    root = tk.Tk()
    root.withdraw()

    try:
        from tkinter import messagebox
        messagebox.showerror(APP_NAME, text[-2000:])
    finally:
        root.destroy()


class Splash:
    W, H = 760, 440
    BG1, BG2 = "#0A1020", "#15264A"
    PANEL = "#0E1832"
    BORDER = "#2A3858"
    TEXT, MUTED = "#E2E8F0", "#8A99B5"
    BLUE, BLUE_L, AMBER = "#3B82F6", "#60A5FA", "#F59E0B"
    DOTS = ("#F97316", "#06B6D4", "#A855F7", "#22C55E", "#EC4899", "#FDE047")
    FONT = "Segoe UI"

    SYMBOLS = (
        "0", "1", "+", "−", "×", "÷",
        "&", "|", "^", "«", "»", "∑", "π", "ƒ",
    )

    def __init__(self, master, makers, on_done, min_ms=10000):
        self.on_done = on_done
        self.min_ms = min_ms
        self.skip = False
        self.done = False
        self.signals = []
        self.orbit_items = []
        self.float_items = []
        self.t0 = time.time()

        self.top = tk.Toplevel(master)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)

        sw, sh = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
        self.top.geometry(
            f"{self.W}x{self.H}+{(sw - self.W) // 2}+{(sh - self.H) // 3}"
        )

        self.cv = tk.Canvas(
            self.top,
            width=self.W,
            height=self.H,
            highlightthickness=0,
            bg=self.BG1,
        )
        self.cv.pack()

        self.top.bind("<Button-1>", lambda e: setattr(self, "skip", True))
        self.top.bind("<Escape>", lambda e: setattr(self, "skip", True))

        self._draw(makers)
        self.top.after(30, self._anim)

    def _draw(self, makers):
        cv, W, H = self.cv, self.W, self.H

        # Original background gradient
        for y in range(0, H, 2):
            cv.create_line(
                0, y, W, y,
                fill=blend(self.BG1, self.BG2, y / H),
            )

        # Original circuit background
        rng = random.Random(11)

        for n in range(26):
            x, y = rng.randrange(0, W, 20), rng.randrange(0, H, 20)
            points = [x, y]

            for _ in range(rng.randint(2, 4)):
                if rng.random() < 0.5:
                    x += rng.choice((-1, 1)) * rng.randrange(40, 160, 20)
                else:
                    y += rng.choice((-1, 1)) * rng.randrange(40, 160, 20)

                x = max(8, min(W - 8, x))
                y = max(8, min(H - 8, y))
                points += [x, y]

            cv.create_line(*points, fill="#1D2F58", width=2)
            cv.create_oval(
                x - 4, y - 4, x + 4, y + 4,
                outline="#2A437A",
                width=2,
            )

            if n % 2 == 0 and len(points) >= 4:
                color = self.DOTS[n % len(self.DOTS)]
                dot = cv.create_oval(0, 0, 0, 0, fill=color, outline="")
                self.signals.append(
                    (dot, points, n * 0.11, 0.18 + (n % 5) * 0.04)
                )

        # Original main panel
        cv.create_rectangle(
            30, 30, W - 30, H - 30,
            fill=self.PANEL,
            outline=self.BORDER,
            width=2,
        )

        self.accent = cv.create_rectangle(
            30, 30, W - 30, 34,
            fill=self.BLUE,
            outline="",
        )

        # Original ALU chip
        cx, cy = 62, 62
        self.chip_cx = cx + 32
        self.chip_cy = cy + 32

        for k in range(4):
            offset = 12 + k * 14

            cv.create_line(
                cx + offset, cy - 10,
                cx + offset, cy,
                fill=self.BLUE_L,
                width=2,
            )

            cv.create_line(
                cx + offset, cy + 64,
                cx + offset, cy + 74,
                fill=self.BLUE_L,
                width=2,
            )

            cv.create_line(
                cx - 10, cy + offset,
                cx, cy + offset,
                fill=self.BLUE_L,
                width=2,
            )

            cv.create_line(
                cx + 64, cy + offset,
                cx + 74, cy + offset,
                fill=self.BLUE_L,
                width=2,
            )

        self.pulse = cv.create_oval(
            cx - 10, cy - 10, cx + 74, cy + 74,
            outline=self.BLUE_L,
            width=2,
        )

        cv.create_rectangle(
            cx, cy, cx + 64, cy + 64,
            fill="#13213F",
            outline=self.BLUE,
            width=3,
        )

        self.chip_label = cv.create_text(
            cx + 32, cy + 32,
            text="ALU",
            fill=self.BLUE_L,
            font=(self.FONT, 16, "bold"),
        )

        # New: subtle orbiting symbols around the ALU chip
        orbit_symbols = ("∑", "ƒ", "π", "01", "&", "|")

        for index, symbol in enumerate(orbit_symbols):
            item = cv.create_text(
                self.chip_cx, self.chip_cy,
                text=symbol,
                fill=self.DOTS[index % len(self.DOTS)],
                font=(self.FONT, 10, "bold"),
            )

            angle = index * (2 * math.pi / len(orbit_symbols))
            self.orbit_items.append((item, angle))

        # Original title and tagline
        cv.create_text(
            160, 78,
            text=APP_NAME,
            anchor="w",
            fill=self.TEXT,
            font=(self.FONT, 30, "bold"),
        )

        cv.create_text(
            162, 114,
            text=APP_TAGLINE,
            anchor="w",
            fill=self.MUTED,
            font=(self.FONT, 11),
        )

        cv.create_line(
            60, 158, W - 60, 158,
            fill=self.BORDER,
        )

        cv.create_text(
            60, 182,
            text="D E V E L O P E D   B Y",
            anchor="w",
            fill=self.AMBER,
            font=(self.FONT, 10, "bold"),
        )

        # Original developer names
        count = max(1, len(makers))
        rows = count if count <= 4 else -(-count // 2)
        spacing = min(54, 150 // rows)

        self.name_items = []

        for index, (name, role) in enumerate(makers):
            if count > 4:
                column, row = divmod(index, rows)
            else:
                column, row = 0, index

            x, y = 78 + column * 330, 214 + row * spacing

            dot = cv.create_oval(
                x - 18, y - 6, x - 6, y + 6,
                fill=self.PANEL,
                outline="",
            )

            name_text = cv.create_text(
                x, y,
                text=name,
                anchor="w",
                fill=self.PANEL,
                font=(self.FONT, 17, "bold"),
            )

            role_text = cv.create_text(
                x, y + 20,
                text=role,
                anchor="w",
                fill=self.PANEL,
                font=(self.FONT, 10),
            )

            color = self.DOTS[index % len(self.DOTS)]
            self.name_items.append((dot, name_text, role_text, color))

        # New: subtle floating technical symbols
        rng = random.Random(42)

        for index in range(14):
            symbol = self.SYMBOLS[index % len(self.SYMBOLS)]
            x = rng.randrange(430, W - 75)
            y = rng.randrange(180, H - 90)
            size = rng.choice((9, 10, 11, 12))
            color = self.DOTS[index % len(self.DOTS)]

            item = cv.create_text(
                x, y,
                text=symbol,
                fill=color,
                font=(self.FONT, size, "bold"),
            )

            self.float_items.append(
                {
                    "item": item,
                    "x": x,
                    "y": y,
                    "speed": rng.uniform(0.18, 0.45),
                    "phase": rng.uniform(0, 2 * math.pi),
                    "color": color,
                }
            )

        # Original progress bar
        cv.create_rectangle(
            60, 392, W - 60, 398,
            fill="#1B2A4D",
            outline="",
        )

        self.bar = cv.create_rectangle(
            60, 392, 60, 398,
            fill=self.BLUE,
            outline="",
        )

        cv.create_text(
            60, 378,
            text="Opening simulator...",
            anchor="sw",
            fill=self.MUTED,
            font=(self.FONT, 10),
        )

        cv.create_text(
            W - 60, 378,
            text="Computer Organization & Architecture",
            anchor="se",
            fill=self.MUTED,
            font=(self.FONT, 10),
        )

        # Keep animated items above background
        for item, _angle in self.orbit_items:
            cv.tag_raise(item)

        for info in self.float_items:
            cv.tag_raise(info["item"])

        for dot, *_rest in self.signals:
            cv.tag_raise(dot)

    def _finish(self):
        if self.done:
            return

        self.done = True

        try:
            self.top.destroy()
        except tk.TclError:
            pass

        self.on_done()

    def _anim(self):
        if self.done:
            return

        try:
            elapsed = (time.time() - self.t0) * 1000
            seconds = elapsed / 1000.0

            # Original progress-bar animation
            shown = min(1.0, elapsed / self.min_ms)

            self.cv.coords(
                self.bar,
                60, 392,
                60 + (self.W - 120) * shown,
                398,
            )

            # Original moving circuit signals
            for dot, points, phase, speed in self.signals:
                x, y = _point_along(points, seconds * speed + phase)
                self.cv.coords(dot, x - 3, y - 3, x + 3, y + 3)

            # Original ALU pulse
            pulse = 0.5 + 0.5 * abs((seconds * 1.4) % 2 - 1)
            grow = 6 + pulse * 10

            self.cv.coords(
                self.pulse,
                62 - grow, 62 - grow,
                126 + grow, 126 + grow,
            )

            self.cv.itemconfigure(
                self.pulse,
                outline=blend(
                    self.PANEL,
                    self.BLUE_L,
                    0.35 + 0.65 * pulse,
                ),
            )

            self.cv.itemconfigure(
                self.accent,
                fill=blend(self.BLUE, "#22D3EE", pulse),
            )

            self.cv.itemconfigure(
                self.chip_label,
                fill=blend(self.BLUE, "#E0F2FE", pulse),
            )

            # New: orbiting symbols around ALU
            for item, base_angle in self.orbit_items:
                angle = base_angle + seconds * 0.55
                radius = 58 + 6 * math.sin(seconds * 1.2 + base_angle)

                x = self.chip_cx + radius * math.cos(angle)
                y = self.chip_cy + radius * math.sin(angle)

                self.cv.coords(item, x, y)

            # New: gentle floating symbols
            for info in self.float_items:
                y = info["y"] - (seconds * info["speed"] * 16) % 240
                x = info["x"] + 5 * math.sin(seconds * 0.7 + info["phase"])

                brightness = 0.25 + 0.30 * abs(
                    math.sin(seconds + info["phase"])
                )

                self.cv.coords(info["item"], x, y)
                self.cv.itemconfigure(
                    info["item"],
                    fill=blend(
                        self.PANEL,
                        info["color"],
                        brightness,
                    ),
                )

            # Original developer-name fade-in
            for index, (dot, name_text, role_text, color) in enumerate(self.name_items):
                fade = (elapsed - 400 - index * 700) / 600
                fade = max(0.0, min(1.0, fade))

                self.cv.itemconfigure(
                    dot,
                    fill=blend(self.PANEL, color, fade),
                )

                self.cv.itemconfigure(
                    name_text,
                    fill=blend(self.PANEL, self.TEXT, fade),
                )

                self.cv.itemconfigure(
                    role_text,
                    fill=blend(self.PANEL, self.MUTED, fade),
                )

            if elapsed >= self.min_ms or self.skip:
                self._finish()
                return

            self.top.after(30, self._anim)

        except tk.TclError:
            self._finish()


def _this_file():
    try:
        return os.path.abspath(__file__)
    except NameError:
        return ""


def _load_core():
    global core

    launcher_file = _this_file()
    last_error = None

    for module_name in ("main", "coa_simulator"):
        try:
            module = importlib.import_module(module_name)
        except ImportError as error:
            last_error = error
            continue

        module_file = os.path.abspath(
            getattr(module, "__file__", "") or ""
        )

        if launcher_file and module_file:
            if os.path.normcase(module_file) == os.path.normcase(launcher_file):
                continue

        if hasattr(module, "ALUApp"):
            core = module
            return

    raise ImportError(
        "Could not find class ALUApp. "
        "Keep the original simulator file beside this launcher."
    ) from last_error


def _load_mpl():
    global HAVE_MPL
    global np, Figure, LinearSegmentedColormap, MaxNLocator, HEAT

    try:
        import numpy as numpy_module
        from matplotlib.figure import Figure as figure_class
        from matplotlib.colors import LinearSegmentedColormap as colormap_class
        from matplotlib.ticker import MaxNLocator as locator_class

    except ImportError:
        HAVE_MPL = False
        return

    np = numpy_module
    Figure = figure_class
    LinearSegmentedColormap = colormap_class
    MaxNLocator = locator_class

    HEAT = LinearSegmentedColormap.from_list(
        "coa",
        [
            "#0B1224",
            "#6D28D9",
            "#2563EB",
            "#06B6D4",
            "#22C55E",
            "#FACC15",
            "#FB923C",
            "#F43F5E",
        ],
    )

    HAVE_MPL = True


def _build_classes():
    global ProApp
    ProApp = make_pro_app(core)


CATEGORIES = {
    "Arithmetic": ("ADD", "SUB", "INC", "DEC", "NEG", "CMP"),
    "Logic": ("AND", "OR", "XOR", "NOT", "NAND", "NOR", "XNOR"),
    "Shift/Rotate": ("SHL", "SHR", "SAR", "ROL", "ROR"),
    "Mul/Div": ("MUL", "DIV", "MOD"),
    "Float arith": ("FADD", "FSUB", "FMUL", "FDIV"),
    "Float misc": ("FNEG", "FABS", "FCMP"),
}

FLAG_ORDER = (
    "zero",
    "sign",
    "carry",
    "overflow",
    "invalid",
    "divide_by_zero",
    "inexact",
)

FLAG_LABEL = {
    "zero": "ZERO",
    "sign": "SIGN",
    "carry": "CARRY",
    "overflow": "OVERFLOW",
    "invalid": "INVALID",
    "divide_by_zero": "DIV/0",
    "inexact": "INEXACT",
}

UNIT_FLAGS = {
    "ALU": ("zero", "carry", "sign", "overflow"),
    "FPU": (
        "zero",
        "sign",
        "invalid",
        "divide_by_zero",
        "overflow",
        "inexact",
    ),
}

CHART_CAT = {
    "Arithmetic": "#FF6B35",
    "Logic": "#00E5FF",
    "Shift/Rotate": "#B388FF",
    "Mul/Div": "#FF4D8D",
    "Float arith": "#4DA3FF",
    "Float misc": "#FFE14D",
}

OP_PALETTE = (
    "#FF6B35", "#00E5FF", "#B388FF", "#FF4D8D",
    "#4DA3FF", "#FFE14D", "#2EE59D", "#FF8A65",
    "#7C4DFF", "#18FFFF", "#FF4081", "#69F0AE",
    "#FFD740", "#40C4FF", "#EA80FC", "#FFAB40",
    "#64FFDA", "#82B1FF", "#FF5252", "#B2FF59",
    "#E040FB", "#00B8D4", "#FF80AB", "#A7FFEB",
)

FLAG_PALETTE = {
    "zero": "#69F0AE",
    "sign": "#FFD740",
    "carry": "#40C4FF",
    "overflow": "#FF5252",
    "invalid": "#FF6E40",
    "divide_by_zero": "#EA80FC",
    "inexact": "#B388FF",
}


def cat_color(name):
    return CHART_CAT[name]


def op_color(operation):
    operations = all_ops()

    try:
        index = operations.index(operation)
    except ValueError:
        index = 0

    return OP_PALETTE[index % len(OP_PALETTE)]


def flag_color(key):
    return FLAG_PALETTE.get(key, "#4DA3FF")


def all_ops():
    return list(core.ALU_OPS) + list(core.FPU_OPS)


def size_key(tag):
    tag = str(tag)

    if tag.startswith("ALU"):
        return (0, int(tag[3:]))

    return (1, list(core.FP_FORMATS).index(tag))


class Stats:
    def __init__(self, log):
        self.log = log
        self.total = len(log)

        self.cat_of = {
            operation: category
            for category, operations in CATEGORIES.items()
            for operation in operations
        }

        self.op_counts = Counter(entry["op"] for entry in log)
        self.cat_counts = Counter(
            self.cat_of.get(entry["op"], "Arithmetic")
            for entry in log
        )

        self.sizes = sorted(
            {entry["size"] for entry in log},
            key=size_key,
        )

        self.size_op = Counter(
            (entry["op"], entry["size"])
            for entry in log
        )

        self.flag_op = Counter()
        self.flag_unit = Counter()

        for entry in log:
            flags = entry.get("flags") or {}

            for key, value in flags.items():
                if value:
                    self.flag_op[(entry["op"], key)] += 1
                    self.flag_unit[(entry["mode"], key)] += 1

    def used_ops(self):
        return [
            operation
            for operation in all_ops()
            if self.op_counts[operation]
        ]

    def top_ops(self, count):
        return [
            operation
            for operation, _count in self.op_counts.most_common(count)
        ]


def style_axis(axis, title=None):
    axis.set_facecolor(core.PANEL)

    for spine in axis.spines.values():
        spine.set_color(core.BORDER)

    axis.tick_params(colors=core.MUTED, labelsize=8)

    if title:
        axis.set_title(
            title,
            color=core.TEXT,
            fontsize=11,
            fontweight="bold",
            pad=10,
        )


def plot_donut(axis, stats):
    style_axis(axis, "Operation mix")

    categories = [
        category
        for category in CATEGORIES
        if stats.cat_counts[category]
    ]

    values = [stats.cat_counts[category] for category in categories]

    if not values:
        return

    axis.pie(
        values,
        colors=[cat_color(category) for category in categories],
        startangle=90,
        counterclock=False,
        labels=[
            f"{category}\n{value}"
            for category, value in zip(categories, values)
        ],
        labeldistance=1.14,
        wedgeprops={
            "width": 0.42,
            "edgecolor": core.PANEL,
            "linewidth": 2.5,
        },
        textprops={
            "color": core.MUTED,
            "fontsize": 8,
        },
    )

    axis.text(
        0, 0,
        f"{stats.total}\nruns",
        ha="center",
        va="center",
        color=core.TEXT,
        fontsize=17,
        fontweight="bold",
    )

    axis.set_aspect("equal")


def plot_radar(axis, stats, count=8):
    style_axis(axis, "Operation radar")

    operations = stats.top_ops(count)

    for operation in all_ops():
        if len(operations) >= 3:
            break

        if operation not in operations:
            operations.append(operation)

    if len(operations) < 3:
        operations = (operations + ["ADD", "AND", "SHL"])[:3]

    values = [stats.op_counts[operation] for operation in operations]
    angles = np.linspace(0, 2 * np.pi, len(operations), endpoint=False)

    closed_angles = np.append(angles, angles[0])
    closed_values = np.append(values, values[0])

    axis.plot(
        closed_angles,
        closed_values,
        color="#22D3EE",
        linewidth=2.4,
    )

    axis.fill(
        closed_angles,
        closed_values,
        color="#A78BFA",
        alpha=0.28,
    )

    axis.scatter(
        angles,
        values,
        c=[op_color(operation) for operation in operations],
        s=70,
        edgecolors="white",
        linewidths=0.8,
        zorder=4,
    )

    axis.set_xticks(angles)
    axis.set_xticklabels(
        operations,
        color=core.TEXT,
        fontsize=8,
        fontweight="bold",
    )

    axis.yaxis.set_major_locator(
        MaxNLocator(integer=True, nbins=4)
    )

    axis.set_ylim(0, max(values + [1]) * 1.15 + 0.3)
    axis.grid(color=core.BORDER, alpha=0.8)
    axis.spines["polar"].set_color(core.BORDER)


def plot_rose(axis, stats):
    style_axis(axis, "Category rose")

    categories = [
        category
        for category in CATEGORIES
        if stats.cat_counts[category]
    ] or list(CATEGORIES)[:1]

    values = [stats.cat_counts[category] for category in categories]
    angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False)

    axis.bar(
        angles,
        values,
        width=2 * np.pi / len(categories) * 0.82,
        color=[cat_color(category) for category in categories],
        edgecolor=core.PANEL,
        linewidth=2,
        alpha=0.92,
    )

    maximum = max(values + [1])

    for angle, value in zip(angles, values):
        axis.text(
            angle,
            value + maximum * 0.08,
            str(value),
            ha="center",
            va="center",
            color=core.TEXT,
            fontsize=9,
            fontweight="bold",
        )

    axis.set_xticks(angles)
    axis.set_xticklabels(
        categories,
        color=core.TEXT,
        fontsize=8,
        fontweight="bold",
    )

    axis.set_ylim(0, maximum * 1.25 + 0.3)
    axis.grid(color=core.BORDER, alpha=0.8)
    axis.spines["polar"].set_color(core.BORDER)


def plot_area(axis, stats):
    style_axis(axis, "Cumulative executions by category")

    total = stats.total
    x_values = np.arange(0, total + 1)

    categories = [
        category
        for category in CATEGORIES
        if stats.cat_counts[category]
    ]

    if categories:
        series = []

        for category in categories:
            values = [0]

            for entry in stats.log:
                if stats.cat_of.get(entry["op"]) == category:
                    values.append(1)
                else:
                    values.append(0)

            series.append(np.cumsum(values))

        axis.stackplot(
            x_values,
            series,
            colors=[cat_color(category) for category in categories],
            labels=categories,
            alpha=0.92,
        )

        axis.legend(
            loc="upper left",
            fontsize=7,
            frameon=False,
            labelcolor=core.MUTED,
        )

    axis.set_xlim(0, max(total, 1))
    axis.set_ylim(0, max(total, 1))
    axis.set_xlabel(
        "execution #",
        color=core.MUTED,
        fontsize=8,
    )


def plot_lollipop(axis, stats, count=8):
    style_axis(axis, f"Top {count} operations")

    operations = stats.top_ops(count)[::-1]

    if not operations:
        return

    values = [stats.op_counts[operation] for operation in operations]
    y_values = np.arange(len(operations))
    colors = [op_color(operation) for operation in operations]

    axis.hlines(
        y_values,
        0,
        values,
        colors=colors,
        linewidth=3.5,
    )

    axis.scatter(
        values,
        y_values,
        s=170,
        c=colors,
        edgecolors="white",
        linewidths=1.2,
        zorder=3,
    )

    maximum = max(values + [1])

    for y_value, value in zip(y_values, values):
        axis.text(
            value + maximum * 0.07,
            y_value,
            str(value),
            va="center",
            color=core.TEXT,
            fontsize=9,
            fontweight="bold",
        )

    axis.set_yticks(y_values)
    axis.set_yticklabels(
        operations,
        color=core.TEXT,
        fontsize=9,
        fontweight="bold",
    )

    axis.set_xlim(0, maximum * 1.25 + 0.5)


def draw_heatmap(
    figure,
    axis,
    matrix,
    rows,
    columns,
    title,
    colorbar=True,
    x_rotation=0,
):
    style_axis(axis, title)

    if not rows or not columns:
        return

    matrix = np.array(matrix, dtype=float)
    maximum = max(1.0, float(matrix.max()) if matrix.size else 1.0)

    image = axis.imshow(
        matrix,
        cmap=HEAT,
        aspect="auto",
        vmin=0,
        vmax=maximum,
    )

    axis.set_xticks(range(len(columns)))
    axis.set_xticklabels(
        columns,
        rotation=x_rotation,
        color=core.TEXT,
        fontsize=8,
        fontweight="bold",
    )

    axis.set_yticks(range(len(rows)))
    axis.set_yticklabels(
        rows,
        color=core.TEXT,
        fontsize=8,
        fontweight="bold",
    )

    for row in range(len(rows)):
        for column in range(len(columns)):
            value = matrix[row, column]

            if value > 0:
                axis.text(
                    column,
                    row,
                    str(int(value)),
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color=(
                        "white"
                        if value < 0.6 * maximum
                        else "#0B1220"
                    ),
                )

    if colorbar:
        bar = figure.colorbar(
            image,
            ax=axis,
            fraction=0.04,
            pad=0.03,
        )

        bar.outline.set_edgecolor(core.BORDER)


def plot_size_heatmap(figure, axis, stats, operation_limit=None, colorbar=True):
    operations = [
        operation
        for operation in all_ops()
        if stats.op_counts[operation]
    ]

    if operation_limit and len(operations) > operation_limit:
        retained = set(stats.top_ops(operation_limit))
        operations = [
            operation
            for operation in operations
            if operation in retained
        ]

    matrix = [
        [stats.size_op[(operation, size)] for size in stats.sizes]
        for operation in operations
    ]

    draw_heatmap(
        figure,
        axis,
        matrix,
        operations,
        stats.sizes,
        "Operation x word size / format",
        colorbar,
    )


def plot_flag_heatmap(figure, axis, stats, colorbar=True):
    operations = [
        operation
        for operation in all_ops()
        if stats.op_counts[operation]
    ]

    columns = [
        key
        for key in FLAG_ORDER
        if any(stats.flag_op[(operation, key)] for operation in operations)
    ] or ["zero"]

    matrix = [
        [stats.flag_op[(operation, key)] for key in columns]
        for operation in operations
    ]

    labels = [FLAG_LABEL[key] for key in columns]

    draw_heatmap(
        figure,
        axis,
        matrix,
        operations,
        labels,
        "Which operations raise which flags",
        colorbar,
        25,
    )


def plot_flag_bubbles(axis, stats):
    style_axis(
        axis,
        "Flag activity  (bubble size = times raised)",
    )

    units = {
        "FPU": 0,
        "ALU": 1,
    }

    maximum = max(
        [
            stats.flag_unit[(unit, flag)]
            for unit in units
            for flag in UNIT_FLAGS[unit]
        ] + [1]
    )

    for unit, y_position in units.items():
        for flag in UNIT_FLAGS[unit]:
            x_position = FLAG_ORDER.index(flag)
            count = stats.flag_unit[(unit, flag)]

            if count:
                axis.scatter(
                    x_position,
                    y_position,
                    s=260 + 1900 * count / maximum,
                    color=flag_color(flag),
                    alpha=0.85,
                    edgecolors="white",
                    linewidths=1.2,
                    zorder=3,
                )

                axis.text(
                    x_position,
                    y_position,
                    str(count),
                    ha="center",
                    va="center",
                    color="white",
                    fontsize=10,
                    fontweight="bold",
                )

            else:
                axis.scatter(
                    x_position,
                    y_position,
                    s=40,
                    color=core.BORDER,
                )

    axis.set_xticks(range(len(FLAG_ORDER)))
    axis.set_xticklabels(
        [FLAG_LABEL[key] for key in FLAG_ORDER],
        rotation=30,
        color=core.TEXT,
        fontsize=8,
    )

    axis.set_yticks([0, 1])
    axis.set_yticklabels(
        ["FPU", "ALU"],
        color=core.TEXT,
        fontsize=9,
        fontweight="bold",
    )

    axis.set_xlim(-0.7, len(FLAG_ORDER) - 0.3)
    axis.set_ylim(-0.7, 1.7)


def plot_trace(axis, stats):
    style_axis(
        axis,
        "Execution trace  (one dot per instruction)",
    )

    operations = stats.used_ops()

    if not operations:
        return

    lanes = {
        operation: index
        for index, operation in enumerate(operations)
    }

    x_values = list(range(1, stats.total + 1))
    y_values = [lanes[entry["op"]] for entry in stats.log]

    axis.plot(
        x_values,
        y_values,
        color=core.BORDER,
        linewidth=1.2,
    )

    axis.scatter(
        x_values,
        y_values,
        c=[op_color(entry["op"]) for entry in stats.log],
        s=110,
        edgecolors="white",
        linewidths=0.8,
        zorder=3,
    )

    axis.set_yticks(range(len(operations)))
    axis.set_yticklabels(
        operations,
        color=core.TEXT,
        fontsize=8,
        fontweight="bold",
    )

    axis.set_xlabel(
        "execution #",
        color=core.MUTED,
        fontsize=8,
    )


def view_dashboard(figure, stats):
    grid = figure.add_gridspec(2, 3)

    plot_donut(
        figure.add_subplot(grid[0, 0]),
        stats,
    )

    plot_radar(
        figure.add_subplot(grid[0, 1], projection="polar"),
        stats,
    )

    plot_area(
        figure.add_subplot(grid[0, 2]),
        stats,
    )

    plot_lollipop(
        figure.add_subplot(grid[1, 0]),
        stats,
    )

    plot_size_heatmap(
        figure,
        figure.add_subplot(grid[1, 1]),
        stats,
        operation_limit=8,
        colorbar=False,
    )

    plot_flag_bubbles(
        figure.add_subplot(grid[1, 2]),
        stats,
    )


def view_radar(figure, stats):
    grid = figure.add_gridspec(
        1, 2,
        width_ratios=[1.25, 1],
    )

    plot_radar(
        figure.add_subplot(grid[0, 0], projection="polar"),
        stats,
        count=12,
    )

    plot_rose(
        figure.add_subplot(grid[0, 1], projection="polar"),
        stats,
    )


def view_heatmaps(figure, stats):
    grid = figure.add_gridspec(1, 2)

    plot_size_heatmap(
        figure,
        figure.add_subplot(grid[0, 0]),
        stats,
    )

    plot_flag_heatmap(
        figure,
        figure.add_subplot(grid[0, 1]),
        stats,
    )


def view_timeline(figure, stats):
    grid = figure.add_gridspec(
        2, 1,
        height_ratios=[1, 1.35],
    )

    plot_area(
        figure.add_subplot(grid[0, 0]),
        stats,
    )

    plot_trace(
        figure.add_subplot(grid[1, 0]),
        stats,
    )


def render_view(figure, view, log):
    figure.clear()
    figure.set_facecolor(core.BG)

    stats = Stats(log)

    if stats.total == 0:
        figure.text(
            0.5, 0.5,
            "No executions yet - run some instructions first",
            ha="center",
            va="center",
            color=core.MUTED,
            fontsize=14,
        )

        return stats

    most_used = stats.top_ops(1)[0]

    figure.suptitle(
        f"COA SIMULATOR ANALYTICS   |   {stats.total} executions"
        f"   |   most used: {most_used}",
        color=core.TEXT,
        fontsize=15,
        fontweight="bold",
    )

    views = {
        "Dashboard": view_dashboard,
        "Radar & Rose": view_radar,
        "Heatmaps": view_heatmaps,
        "Timeline": view_timeline,
    }

    views[view](figure, stats)
    return stats


def make_figure():
    try:
        return Figure(
            figsize=(12.4, 6.6),
            dpi=100,
            facecolor=core.BG,
            layout="constrained",
        )

    except TypeError:
        return Figure(
            figsize=(12.4, 6.6),
            dpi=100,
            facecolor=core.BG,
        )


def make_pro_app(simulator):
    custom_tk = simulator.ctk

    from tkinter import filedialog

    class ProSimulatorApp(simulator.ALUApp):
        full_log = None

        def __init__(self, makers):
            super().__init__()
            self.makers = makers
            self.graph_view = GRAPH_VIEWS[0]

            try:
                self.title(
                    f"{APP_NAME} | Variable-width ALU"
                    f" + Multi-format FPU"
                )
            except Exception:
                pass

            names = "   •   ".join(
                name for name, _role in makers
            )

            try:
                if names and getattr(self, "status", None) is not None:
                    custom_tk.CTkLabel(
                        self.status.master,
                        text=f"Made by  {names}",
                        font=(simulator.UI, 11, "bold"),
                        text_color=simulator.BLUE_L,
                    ).pack(side="right", padx=14)

            except Exception:
                pass

        def add_history(self, entry):
            if self.full_log is None:
                self.full_log = []

            trace = getattr(self, "trace", None) or {}

            self.full_log.append(
                {
                    "op": entry["op"],
                    "size": entry["size"],
                    "mode": entry["mode"],
                    "flags": dict(trace.get("flags", {})),
                }
            )

            super().add_history(entry)

        def show_usage_graph(self):
            if not self.full_log:
                self.set_status(
                    "No operations executed yet. Press Execute first.",
                    simulator.AMBER,
                )
                return

            if not HAVE_MPL:
                self.set_status(
                    "matplotlib is not installed:  pip install matplotlib",
                    simulator.RED,
                )
                return

            from matplotlib.backends.backend_tkagg import (
                FigureCanvasTkAgg,
            )

            graph_exists = (
                self.graph_win is not None
                and self.graph_win.winfo_exists()
            )

            if not graph_exists:
                window = custom_tk.CTkToplevel(self)
                window.title(f"{APP_NAME} | Analytics")
                window.geometry("1260x780")
                window.configure(fg_color=simulator.BG)

                toolbar = custom_tk.CTkFrame(
                    window,
                    fg_color="transparent",
                )

                toolbar.pack(
                    fill="x",
                    padx=12,
                    pady=(10, 0),
                )

                self.graph_segment = custom_tk.CTkSegmentedButton(
                    toolbar,
                    values=list(GRAPH_VIEWS),
                    command=self.on_graph_view,
                    font=(simulator.UI, 12, "bold"),
                )

                self.graph_segment.set(self.graph_view)
                self.graph_segment.pack(side="left")

                custom_tk.CTkButton(
                    toolbar,
                    text="Reset stats",
                    width=100,
                    fg_color=simulator.CARD,
                    hover_color=simulator.BORDER,
                    command=self.reset_stats,
                ).pack(side="right", padx=(6, 0))

                custom_tk.CTkButton(
                    toolbar,
                    text="Save PNG",
                    width=100,
                    fg_color=simulator.BLUE,
                    command=self.save_graph,
                ).pack(side="right")

                self.graph_figure = make_figure()

                self.graph_canvas = FigureCanvasTkAgg(
                    self.graph_figure,
                    master=window,
                )

                self.graph_canvas.get_tk_widget().pack(
                    fill="both",
                    expand=True,
                    padx=10,
                    pady=10,
                )

                self.graph_win = window

            self.draw_graph()
            self.graph_win.lift()
            self.graph_win.focus()

        def on_graph_view(self, value):
            self.graph_view = value
            self.draw_graph()

        def draw_graph(self):
            if self.graph_figure is None:
                return

            render_view(
                self.graph_figure,
                self.graph_view,
                self.full_log or [],
            )

            self.graph_canvas.draw()

        def save_graph(self):
            path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG image", "*.png")],
                initialfile=(
                    "coa_analytics_"
                    + self.graph_view.split()[0].lower()
                    + ".png"
                ),
            )

            if path:
                self.graph_figure.savefig(
                    path,
                    dpi=160,
                    facecolor=self.graph_figure.get_facecolor(),
                )

                self.set_status(
                    f"Saved chart to {path}",
                    simulator.GREEN,
                )

        def reset_stats(self):
            self.full_log = []
            self.usage_counts = {
                key: 0 for key in self.usage_counts
            }

            self.update_usage_label()

            graph_exists = (
                self.graph_win is not None
                and self.graph_win.winfo_exists()
            )

            if graph_exists:
                self.graph_win.destroy()

            self.graph_win = None
            self.set_status(
                "Statistics reset.",
                simulator.MUTED,
            )

    return ProSimulatorApp


def reveal_application(application):
    try:
        application.deiconify()
        application.lift()
        application.focus_force()
        application.attributes("-topmost", True)

        application.after(
            400,
            lambda: application.attributes("-topmost", False),
        )

    except Exception:
        pass


def main():
    makers = load_makers()

    try:
        _load_core()
        _load_mpl()
        _build_classes()

        application = ProApp(makers)

    except Exception:
        _show_error(traceback.format_exc())
        return

    try:
        application.withdraw()
    except Exception:
        pass

    def open_main_window():
        reveal_application(application)

    try:
        Splash(
            application,
            makers,
            open_main_window,
            min_ms=10000,
        )

    except Exception:
        reveal_application(application)

    application.mainloop()


if __name__ == "__main__":
    main()