# Main GUI entry point

"""
COA Simulator Pro - configurable-width ALU + multi-format IEEE-754 FPU with live circuit view
==============================================================================================
Requires : pip install customtkinter matplotlib      (matplotlib only for the usage graph)
Run      : python coa_simulator.py
Note     : fully self-contained. alu_core.py is OPTIONAL - if present, 32-bit results are
           cross-checked against it. fpu_core.py is no longer needed.

What's new
  * Word size selector for the integer ALU: 4 / 8 / 16 / 32 / 64 bits
  * FPU formats: FP8 (1-4-3), FP16 (half), BF16 (bfloat16), FP32 (single), FP64 (double)
  * 21 ALU ops : ADD SUB INC DEC NEG CMP | AND OR XOR NOT NAND NOR XNOR |
                 SHL SHR SAR ROL ROR | MUL DIV MOD
  * 7 FPU ops  : FADD FSUB FMUL FDIV FNEG FABS FCMP  (exact rational arithmetic, round-to-nearest-even)
  * Flags: ALU  ZERO CARRY SIGN OVERFLOW      FPU  ZERO SIGN INVALID DIV/0 OVERFLOW INEXACT
  * "Working" panel: textbook-style binary working, carries, per-stage shifts, exact vs stored
    float value and rounding error
  * Live preview, gate-level circuit view, animation, click-to-toggle bits, examples menu,
    swap A<->B, RESULT->A chaining, history, CSV export, usage graph, reference-model check
"""

import csv
import math
import random
import struct
import tkinter as tk
from decimal import Decimal, localcontext
from fractions import Fraction
from tkinter import Canvas, filedialog

import customtkinter as ctk

try:                                   # optional legacy cross-check (32-bit only)
    from alu_core import execute as legacy_alu
except Exception:                      # pragma: no cover
    legacy_alu = None


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ----------------------------------------------------------------------
# Theme
# ----------------------------------------------------------------------

BG = "#0B1220"
PANEL = "#121B30"
CARD = "#1A2540"
BORDER = "#2A3858"

TEXT = "#E2E8F0"
MUTED = "#8A99B5"

BLUE = "#3B82F6"
BLUE_L = "#60A5FA"
GREEN = "#22C55E"
AMBER = "#F59E0B"
RED = "#EF4444"
PURPLE = "#A855F7"
CYAN = "#06B6D4"
ORANGE = "#F97316"
YELLOW = "#FDE047"
PINK = "#EC4899"

OFF = "#1E2A47"
WIRE = "#4A5B82"
DIM = "#2C3A5C"
NODE = "#16223D"
ACTIVE_FILL = "#24335C"
SCOPE = "#0B1324"

UI = "Segoe UI"
MONO = "Consolas"

# ----------------------------------------------------------------------
# Operation tables
# ----------------------------------------------------------------------

ADDER_OPS = ("ADD", "SUB", "INC", "DEC", "NEG", "CMP")
LOGIC = ("AND", "OR", "XOR", "NOT", "NAND", "NOR", "XNOR")
SHIFTS = ("SHL", "SHR", "SAR", "ROL", "ROR")
ARITH = ("MUL", "DIV", "MOD")
UNARY = ("NOT", "INC", "DEC", "NEG", "FNEG", "FABS")

ALU_OPS = {
    "ADD": ORANGE, "SUB": ORANGE, "INC": ORANGE, "DEC": ORANGE, "NEG": ORANGE, "CMP": ORANGE,
    "AND": CYAN, "OR": CYAN, "XOR": CYAN, "NOT": CYAN, "NAND": CYAN, "NOR": CYAN, "XNOR": CYAN,
    "SHL": PURPLE, "SHR": PURPLE, "SAR": PURPLE, "ROL": PURPLE, "ROR": PURPLE,
    "MUL": PINK, "DIV": PINK, "MOD": PINK,
}

FPU_OPS = {
    "FADD": ORANGE, "FSUB": ORANGE, "FMUL": PURPLE, "FDIV": RED,
    "FNEG": CYAN, "FABS": CYAN, "FCMP": YELLOW,
}

WIDTHS = (4, 8, 16, 32, 64)

# name -> (exponent bits, mantissa bits, description)
FP_FORMATS = {
    "FP8": (4, 3, "FP8 minifloat 1-4-3"),
    "FP16": (5, 10, "IEEE half 1-5-10"),
    "BF16": (8, 7, "bfloat16 1-8-7"),
    "FP32": (8, 23, "IEEE single 1-8-23"),
    "FP64": (11, 52, "IEEE double 1-11-52"),
}

ALU_FLAGS = [
    ("zero", "ZERO", GREEN, "Result is zero"),
    ("carry", "CARRY", AMBER, "Adder carry-out (SUB/CMP: 1 means no borrow) / bit shifted out / MUL high half non-zero"),
    ("sign", "SIGN", RED, "Most significant bit of the result is set"),
    ("overflow", "OVERFLOW", PURPLE, "Signed overflow (result does not fit in two's complement)"),
]

FPU_FLAGS = [
    ("zero", "ZERO", GREEN, "Result is +0.0 or -0.0"),
    ("sign", "SIGN", RED, "Sign bit of the result"),
    ("invalid", "INVALID", PURPLE, "Invalid operation (0/0, inf-inf, 0*inf, NaN operand in compare...)"),
    ("divide_by_zero", "DIV/0", AMBER, "Finite non-zero value divided by zero"),
    ("overflow", "OVERFLOW", ORANGE, "Rounded result too large: became infinity"),
    ("inexact", "INEXACT", CYAN, "Result had to be rounded"),
]


def circuit_info(op, n):
    text = {
        "ADD": f"{n}-bit ripple-carry adder: A + B, the carry propagates through {n} full adders",
        "SUB": "A + NOT(B) + 1 : two's-complement subtraction on the same adder",
        "INC": "A + 1 : adder with B tied to constant 1",
        "DEC": "A - 1 : A + NOT(1) + 1 on the same adder",
        "NEG": "0 - A : two's complement negation (invert and add 1)",
        "CMP": "A - B with the result discarded: only the flags matter (used for branches)",
        "AND": f"Bitwise AND gate array ({n} gates in parallel)",
        "OR": f"Bitwise OR gate array ({n} gates in parallel)",
        "XOR": f"Bitwise XOR gate array ({n} gates in parallel)",
        "NOT": f"Bitwise NOT inverter array ({n} inverters in parallel)",
        "NAND": f"Bitwise NAND gate array ({n} gates in parallel)",
        "NOR": f"Bitwise NOR gate array ({n} gates in parallel)",
        "XNOR": f"Bitwise XNOR gate array ({n} gates in parallel)",
        "SHL": f"Barrel shifter: {max(1, n.bit_length() - 1)} mux stages, logical left shift, zero fill",
        "SHR": f"Barrel shifter: {max(1, n.bit_length() - 1)} mux stages, logical right shift, zero fill",
        "SAR": f"Barrel shifter: {max(1, n.bit_length() - 1)} mux stages, arithmetic right shift, sign fill",
        "ROL": f"Barrel shifter: {max(1, n.bit_length() - 1)} mux stages, rotate left (bits wrap around)",
        "ROR": f"Barrel shifter: {max(1, n.bit_length() - 1)} mux stages, rotate right (bits wrap around)",
        "MUL": f"Shift-and-add multiplier: {n}x{n} -> {2 * n}-bit product, low {n} bits kept",
        "DIV": f"Restoring divider: {n} compare/subtract steps, unsigned quotient",
        "MOD": f"Restoring divider: {n} compare/subtract steps, remainder output",
        "FADD": "Float adder: exponent alignment, mantissa add, normalize, round",
        "FSUB": "Float subtractor: sign handling, mantissa subtract, normalize, round",
        "FMUL": "Float multiplier: exponents add, mantissas multiply, normalize, round",
        "FDIV": "Float divider: exponents subtract, mantissas divide, normalize, round",
        "FNEG": "Sign-bit inverter",
        "FABS": "Sign-bit clear circuit",
        "FCMP": "Float comparator: sign, then exponent, then mantissa (result -1 / 0 / +1)",
    }
    return text.get(op, "")


# ----------------------------------------------------------------------
# Pure integer helpers
# ----------------------------------------------------------------------

def mask_of(n):
    return (1 << n) - 1


def to_signed(v, n):
    return v - (1 << n) if (v >> (n - 1)) & 1 else v


def hexw(v, n):
    return f"0x{v:0{(n + 3) // 4}X}"


def group_bin(v, n):
    s = f"{v:0{n}b}"
    return " ".join(s[i:i + 4] for i in range(0, n, 4))


def short_hex(v, digits, maxd=8):
    s = f"{v:0{digits}X}"
    if len(s) <= maxd:
        return "0x" + s
    half = maxd // 2
    return "0x" + s[:half] + ".." + s[-half:]


def ripple(a, b, subtract, n):
    """Trace of an n-bit ripple-carry adder. carries[i] = carry INTO bit i."""
    mask = mask_of(n)
    bb = (~b) & mask if subtract else b & mask
    carry = 1 if subtract else 0
    carries, sums = [carry], []
    for i in range(n):
        ai, bi = (a >> i) & 1, (bb >> i) & 1
        sums.append(ai ^ bi ^ carry)
        carry = (ai & bi) | (carry & (ai ^ bi))
        carries.append(carry)
    return bb, carries, sums


def adder_inputs(op, a, b):
    """Return (x, y, subtract) that is fed to the adder for this op."""
    return {
        "ADD": (a, b, False), "SUB": (a, b, True), "CMP": (a, b, True),
        "INC": (a, 1, False), "DEC": (a, 1, True), "NEG": (0, a, True),
    }[op]


def adder_labels(op):
    if op == "INC":
        return "REGISTER A", "CONSTANT 1"
    if op == "DEC":
        return "REGISTER A", "CONSTANT 1"
    if op == "NEG":
        return "CONSTANT 0", "REGISTER A"
    return "REGISTER A", "REGISTER B"


def shift_step(op, v, k, n):
    """One barrel-shifter stage (shift by 2^k) applied to v."""
    amt = 1 << k
    mask = mask_of(n)
    if op == "SHL":
        return (v << amt) & mask
    if op == "SHR":
        return v >> amt
    if op == "SAR":
        out = v >> amt
        if (v >> (n - 1)) & 1:
            out |= (((1 << amt) - 1) << (n - amt)) & mask
        return out
    if op == "ROL":
        return ((v << amt) | (v >> (n - amt))) & mask
    return ((v >> amt) | (v << (n - amt))) & mask  # ROR


def reference_alu(op, a, b, n):
    """Independent software model (plain Python ints) used to cross-check the gate model."""
    mask = mask_of(n)
    amt = b % n
    table = {
        "ADD": lambda: (a + b) & mask, "SUB": lambda: (a - b) & mask, "CMP": lambda: (a - b) & mask,
        "INC": lambda: (a + 1) & mask, "DEC": lambda: (a - 1) & mask, "NEG": lambda: (-a) & mask,
        "AND": lambda: a & b, "OR": lambda: a | b, "XOR": lambda: a ^ b, "NOT": lambda: (~a) & mask,
        "NAND": lambda: (~(a & b)) & mask, "NOR": lambda: (~(a | b)) & mask,
        "XNOR": lambda: (~(a ^ b)) & mask,
        "SHL": lambda: (a << amt) & mask, "SHR": lambda: a >> amt,
        "SAR": lambda: (to_signed(a, n) >> amt) & mask,
        "ROL": lambda: ((a << amt) | (a >> (n - amt))) & mask if amt else a,
        "ROR": lambda: ((a >> amt) | (a << (n - amt))) & mask if amt else a,
        "MUL": lambda: (a * b) & mask,
        "DIV": lambda: a // b if b else None, "MOD": lambda: a % b if b else None,
    }
    return table[op]()


# ----------------------------------------------------------------------
# ALU engine
# ----------------------------------------------------------------------

def alu_trace(op, a, b, n):
    mask = mask_of(n)
    msb = n - 1
    lx, ly = adder_labels(op) if op in ADDER_OPS else ("REGISTER A", "REGISTER B")
    tr = {"mode": "ALU", "op": op, "n": n, "a": a, "b": b, "x": a, "y": b,
          "lx": lx, "ly": ly, "flag_defs": ALU_FLAGS, "extra": None, "lines": [], "note": ""}
    flags = {"zero": 0, "carry": 0, "sign": 0, "overflow": 0}

    if op in ADDER_OPS:
        x, y, sub = adder_inputs(op, a, b)
        bb, carries, sums = ripple(x, y, sub, n)
        result = sum(s << i for i, s in enumerate(sums))
        flags["carry"] = carries[n]
        flags["overflow"] = carries[n] ^ carries[msb]
        tr.update(x=x, y=y, sub=sub, bb=bb, carries=carries, sums=sums)
        if op == "CMP":
            sa, sb_ = to_signed(a, n), to_signed(b, n)
            rel_u = "<" if a < b else (">" if a > b else "==")
            rel_s = "<" if sa < sb_ else (">" if sa > sb_ else "==")
            tr["extra"] = ("COMPARE", f"u: A{rel_u}B   s: A{rel_s}B")

    elif op in LOGIC:
        result = {
            "AND": a & b, "OR": a | b, "XOR": a ^ b, "NOT": (~a) & mask,
            "NAND": (~(a & b)) & mask, "NOR": (~(a | b)) & mask, "XNOR": (~(a ^ b)) & mask,
        }[op]

    elif op in SHIFTS:
        stages = n.bit_length() - 1
        amt = b & (n - 1)
        v, steps = a, []
        for k in range(stages):
            on = (amt >> k) & 1
            if on:
                v = shift_step(op, v, k, n)
            steps.append((on, v))
        result = v
        if amt:
            if op == "SHL":
                flags["carry"] = (a >> (n - amt)) & 1
            elif op in ("SHR", "SAR"):
                flags["carry"] = (a >> (amt - 1)) & 1
            elif op == "ROL":
                flags["carry"] = result & 1
            else:
                flags["carry"] = (result >> msb) & 1
        tr.update(amt=amt, steps=steps, stages=stages)

    elif op == "MUL":
        full = a * b
        result = full & mask
        high = full >> n
        sfull = to_signed(a, n) * to_signed(b, n)
        flags["carry"] = int(high != 0)
        flags["overflow"] = int(not (-(1 << msb) <= sfull < (1 << msb)))
        tr["extra"] = (f"FULL {2 * n}-BIT PRODUCT", f"0x{full:0{max(1, n // 2)}X}")
        acc, lines = 0, [f"{'bit':<4}{'B[i]':<6}{'action':<14}accumulator"]
        shown = min(n, 9)
        for i in range(shown):
            bit = (b >> i) & 1
            if bit:
                acc += a << i
            lines.append(f"{i:<4}{bit:<6}{('acc += A<<' + str(i)) if bit else 'skip':<14}0x{acc:X}")
        if n > shown:
            lines.append(f"... {n - shown} more steps ...  final product = 0x{full:X}")
        tr["lines"] = lines
        tr["note"] = f"A x B = {a} x {b} = {full}   (high half = {high}, kept low half = {result})"

    else:  # DIV / MOD
        if b == 0:
            raise ValueError("Division by zero (B must be non-zero for DIV / MOD).")
        q, r = a // b, a % b
        result = q if op == "DIV" else r
        tr["extra"] = ("REMAINDER", str(r)) if op == "DIV" else ("QUOTIENT", str(q))
        rem, rows = 0, []
        for i in range(n - 1, -1, -1):
            rem = (rem << 1) | ((a >> i) & 1)
            qbit = 1 if rem >= b else 0
            if qbit:
                rem -= b
            rows.append((i, rem, qbit))
        lines = [f"{'bit':<4}{'rem after':<16}q bit"]
        shown = rows[-9:]
        if n > 9:
            lines.append(f"(showing the last 9 of {n} steps)")
        for i, rem_after, qbit in shown:
            lines.append(f"{i:<4}{rem_after:<16}{qbit}")
        tr["lines"] = lines
        tr["note"] = f"A = Q x B + R  ->  {a} = {q} x {b} + {r}"

    flags["zero"] = int(result == 0)
    flags["sign"] = (result >> msb) & 1
    tr["result"] = result
    tr["flags"] = flags

    ref = reference_alu(op, a, b, n)
    tr["verified"] = (ref == result)
    tr["legacy"] = None
    if (n == 32 and legacy_alu is not None and op in ("ADD", "SUB", "AND", "OR", "XOR", "NOT", "SHL", "SHR")
            and not (op in SHIFTS and b > 31)):
        try:
            old, _ = legacy_alu(op, a, b)
            tr["legacy"] = ((old & mask) == result)
        except Exception:
            tr["legacy"] = None
    tr["working"] = working_alu(tr)
    return tr


def working_alu(tr):
    n, op, a, b, r = tr["n"], tr["op"], tr["a"], tr["b"], tr["result"]
    G = lambda v: group_bin(v, n)
    L = []

    def row(label, val):
        L.append(f"{label:>16} : {G(val)}")

    if op in ADDER_OPS:
        carries = tr["carries"]
        cin = sum(carries[i] << i for i in range(n))
        yl = {"SUB": "~B (+1)", "CMP": "~B (+1)", "DEC": "~1 (+1)", "NEG": "~A (+1)"}.get(op, "B" if op == "ADD" else "1")
        xl = "0" if op == "NEG" else "A"
        row("carry into bit", cin)
        row(xl, tr["x"])
        row("+ " + yl, tr["bb"])
        L.append(" " * 19 + "-" * (n + (n // 4 - 1)))
        row("sum", r)
        L.append("")
        L.append(f"Unsigned view : A = {a}, B = {b}  ->  result = {r}")
        L.append(f"Signed view   : A = {to_signed(a, n)}, B = {to_signed(b, n)}  ->  result = {to_signed(r, n)}")
        L.append(f"CARRY    = {carries[n]}   carry-out of the MSB adder"
                 + ("   (SUB/CMP: 1 means A >= B unsigned, i.e. no borrow)" if tr["sub"] else ""))
        L.append(f"OVERFLOW = {carries[n] ^ carries[n - 1]}   carry into MSB = {carries[n - 1]}, carry out = {carries[n]}"
                 "  (overflow when they differ)")
        if tr["extra"]:
            L.append(f"{tr['extra'][0]} : {tr['extra'][1]}")
        L.append(f"Hardware      : {n} full adders (~{5 * n} gates), worst-case carry path ~{2 * n} gate delays")
    elif op in LOGIC:
        sym = {"AND": "&", "OR": "|", "XOR": "^", "NOT": "~", "NAND": "~&", "NOR": "~|", "XNOR": "~^"}[op]
        row("A", a)
        if op != "NOT":
            row(f"{sym} B", b)
        L.append(" " * 19 + "-" * (n + (n // 4 - 1)))
        row("result", r)
        L.append("")
        L.append(f"Hardware      : {n} parallel {op} gates, 1 gate delay (no carry chain)")
    elif op in SHIFTS:
        L.append(f"Shift amount  : {b} -> using B mod {n} = {tr['amt']}  ({tr['amt']:0{tr['stages']}b} in binary)")
        row("start A", a)
        for k, (on, val) in enumerate(tr["steps"]):
            tag = f"{'ACTIVE' if on else 'bypass'} by {1 << k}"
            row(f"stage {k} {tag}", val)
        L.append("")
        L.append(f"Hardware      : {tr['stages']} mux stages x {n} muxes instead of {n - 1} sequential shifts")
        L.append(f"CARRY         : {tr['flags']['carry']}   (last bit shifted out / wrapped)")
    elif op == "MUL":
        L.append(tr["note"])
        L.append(f"Signed view   : {to_signed(a, n)} x {to_signed(b, n)} = {to_signed(a, n) * to_signed(b, n)}")
        L.append(f"CARRY = {tr['flags']['carry']} (unsigned: high half non-zero)   "
                 f"OVERFLOW = {tr['flags']['overflow']} (signed product does not fit)")
    else:
        L.append(tr["note"])
        L.append(f"Check         : {a // b} x {b} + {a % b} = {(a // b) * b + a % b}")
    L.append("")
    L.append(f"Result in bases : dec {r}  |  signed {to_signed(r, n)}  |  hex {hexw(r, n)}  |  oct 0o{r:o}")
    return "\n".join(L)


# ----------------------------------------------------------------------
# Floating-point engine (generic sign / exponent / mantissa format)
# ----------------------------------------------------------------------

def fp_params(E, M):
    return 1 + E + M, (1 << (E - 1)) - 1, (1 << E) - 1


def fp_split(bits, E, M):
    return bits >> (E + M), (bits >> M) & ((1 << E) - 1), bits & ((1 << M) - 1)


def fp_class(bits, E, M):
    s, e, m = fp_split(bits, E, M)
    if e == (1 << E) - 1:
        return "NaN" if m else "Infinity"
    if e == 0:
        return "Zero" if m == 0 else "Subnormal"
    return "Normal"


def fp_sig(bits, E, M):
    s, e, m = fp_split(bits, E, M)
    return m | ((1 << M) if e else 0)


def fp_exact(bits, E, M):
    """Exact value as Fraction, or None for NaN / Infinity."""
    n, bias, emax = fp_params(E, M)
    s, e, m = fp_split(bits, E, M)
    if e == emax:
        return None
    if e == 0:
        val = Fraction(m) * Fraction(2) ** (1 - bias - M)
    else:
        val = Fraction((1 << M) + m) * Fraction(2) ** (e - bias - M)
    return -val if s else val


def fp_inf(sign, E, M):
    return (sign << (E + M)) | (((1 << E) - 1) << M)


def fp_qnan(E, M):
    return (((1 << E) - 1) << M) | (1 << (M - 1))


def fp_round(x, E, M, zero_sign=0):
    """Round an exact Fraction to the format (nearest-even). Returns (bits, inexact, overflow)."""
    n, bias, emax = fp_params(E, M)
    if x == 0:
        return zero_sign << (E + M), False, False
    sign = 1 if x < 0 else 0
    ax = -x if sign else x
    e = ax.numerator.bit_length() - ax.denominator.bit_length()
    if Fraction(2) ** e > ax:
        e -= 1
    elif Fraction(2) ** (e + 1) <= ax:
        e += 1
    emin = 1 - bias
    ee = max(e, emin)
    scaled = ax / Fraction(2) ** (ee - M)
    q, r = divmod(scaled.numerator, scaled.denominator)
    twice = 2 * r
    if twice > scaled.denominator or (twice == scaled.denominator and (q & 1)):
        q += 1
    inexact = r != 0
    if q >= (1 << (M + 1)):
        q >>= 1
        ee += 1
    if q >= (1 << M):
        biased, mant = ee + bias, q - (1 << M)
    else:
        biased, mant = 0, q
    if biased >= emax:
        return fp_inf(sign, E, M), True, True
    return (sign << (E + M)) | (biased << M) | mant, inexact, False


def fp_str(bits, E, M):
    cls = fp_class(bits, E, M)
    s = bits >> (E + M)
    if cls == "NaN":
        return "NaN"
    if cls == "Infinity":
        return "-Infinity" if s else "Infinity"
    v = fp_exact(bits, E, M)
    if v == 0:
        return "-0.0" if s else "0.0"
    digits = min(17, math.ceil(M * 0.30103) + 2)
    return f"{float(v):.{digits}g}"


def fp_parse(text, E, M):
    """Text -> bit pattern. Accepts decimal, inf, nan, 0xBITS, 0bBITS."""
    n = 1 + E + M
    t = text.strip().lower().replace("_", "")
    if not t:
        raise ValueError("Value is required.")
    if t.startswith(("0x", "0b")):
        try:
            v = int(t, 0)
        except ValueError:
            raise ValueError("Invalid bit pattern.")
        if not 0 <= v < (1 << n):
            raise ValueError(f"Bit pattern must fit in {n} bits.")
        return v
    sign = 1 if t.startswith("-") else 0
    body = t.lstrip("+-")
    if body in ("inf", "infinity"):
        return fp_inf(sign, E, M)
    if body == "nan":
        return fp_qnan(E, M)
    try:
        f = float(t)
    except ValueError:
        raise ValueError("Invalid number (decimal, inf, nan, 0xBITS).")
    if math.isinf(f):
        return fp_inf(1 if f < 0 else 0, E, M)
    if f == 0.0:
        return sign << (E + M)
    exact = Fraction(t) if len(t) < 60 else Fraction(f)
    bits, _, _ = fp_round(exact, E, M)
    return bits


def fp_exec(op, a, b, E, M):
    n, bias, emax = fp_params(E, M)
    SIGN = 1 << (n - 1)
    fl = {"zero": 0, "sign": 0, "invalid": 0, "divide_by_zero": 0, "overflow": 0, "inexact": 0}
    exact, note = None, ""
    qnan = fp_qnan(E, M)
    ca, cb = fp_class(a, E, M), fp_class(b, E, M)
    sa, sb = a >> (n - 1), b >> (n - 1)
    xa, xb = fp_exact(a, E, M), fp_exact(b, E, M)

    def is_snan(bits):
        return fp_class(bits, E, M) == "NaN" and not (bits >> (M - 1)) & 1

    if op == "FNEG":
        res = a ^ SIGN
        note = "Sign bit flipped; exponent and mantissa untouched."
    elif op == "FABS":
        res = a & ~SIGN & mask_of(n)
        note = "Sign bit cleared; exponent and mantissa untouched."
    elif op == "FCMP":
        if ca == "NaN" or cb == "NaN":
            res, fl["invalid"] = qnan, 1
            note = "Unordered: at least one operand is NaN (result NaN, INVALID set)."
        else:
            va = math.inf * (-1 if sa else 1) if xa is None else xa
            vb = math.inf * (-1 if sb else 1) if xb is None else xb
            c = -1 if va < vb else (1 if va > vb else 0)
            res, _, _ = fp_round(Fraction(c), E, M)
            note = f"Compare: A {'<' if c < 0 else ('>' if c > 0 else '==')} B  ->  result {c:+d}"
    else:
        if op == "FSUB":
            b ^= SIGN
            sb ^= 1
            xb = -xb if xb is not None else None
        ra = ca if op != "FSUB" else ca
        if ca == "NaN" or cb == "NaN":
            res = qnan
            fl["invalid"] = int(is_snan(a) or is_snan(b))
            note = "NaN operand: result is NaN."
        elif op in ("FADD", "FSUB"):
            if ca == "Infinity" and cb == "Infinity":
                if sa != sb:
                    res, fl["invalid"], note = qnan, 1, "inf - inf is undefined: INVALID, result NaN."
                else:
                    res = fp_inf(sa, E, M)
            elif ca == "Infinity":
                res = fp_inf(sa, E, M)
            elif cb == "Infinity":
                res = fp_inf(sb, E, M)
            else:
                exact = xa + xb
                zs = (sa & sb) if (xa == 0 and xb == 0) else 0
                res, ix, ov = fp_round(exact, E, M, zs)
                fl["inexact"], fl["overflow"] = int(ix or ov), int(ov)
                ea, eb = fp_split(a, E, M)[1], fp_split(b, E, M)[1]
                note = f"Exponent difference = {abs(ea - eb)}: the smaller operand is shifted right before the mantissa add."
        elif op == "FMUL":
            if (ca == "Infinity" and xb == 0) or (cb == "Infinity" and xa == 0):
                res, fl["invalid"], note = qnan, 1, "0 x inf is undefined: INVALID, result NaN."
            elif ca == "Infinity" or cb == "Infinity":
                res = fp_inf(sa ^ sb, E, M)
            else:
                exact = xa * xb
                res, ix, ov = fp_round(exact, E, M, sa ^ sb)
                fl["inexact"], fl["overflow"] = int(ix or ov), int(ov)
                note = "Exponents add (minus bias); mantissas multiply; result normalized and rounded."
        else:  # FDIV
            if ca == "Infinity" and cb == "Infinity":
                res, fl["invalid"], note = qnan, 1, "inf / inf is undefined: INVALID, result NaN."
            elif ca == "Infinity":
                res = fp_inf(sa ^ sb, E, M)
            elif cb == "Infinity":
                res = (sa ^ sb) << (n - 1)
            elif xb == 0:
                if xa == 0:
                    res, fl["invalid"], note = qnan, 1, "0 / 0 is undefined: INVALID, result NaN."
                else:
                    res, fl["divide_by_zero"] = fp_inf(sa ^ sb, E, M), 1
                    note = "Finite / 0 gives infinity and sets DIV/0."
            else:
                exact = xa / xb
                res, ix, ov = fp_round(exact, E, M, sa ^ sb)
                fl["inexact"], fl["overflow"] = int(ix or ov), int(ov)
                note = "Exponents subtract (plus bias); mantissas divide; result normalized and rounded."
    fl["zero"] = int((res & ~SIGN & mask_of(n)) == 0)
    fl["sign"] = res >> (n - 1)
    return res, fl, exact, note


_STRUCT = {(8, 23): "<f", (11, 52): "<d", (5, 10): "<e"}


def fp_reference(op, a, b, E, M):
    """Independent check using Python/struct hardware floats. None = not checkable."""
    code = _STRUCT.get((E, M))
    if code is None or op not in ("FADD", "FSUB", "FMUL", "FDIV"):
        return None
    n = 1 + E + M
    try:
        fa = struct.unpack(code, a.to_bytes(n // 8, "little"))[0]
        fb = struct.unpack(code, b.to_bytes(n // 8, "little"))[0]
        v = {"FADD": fa + fb, "FSUB": fa - fb, "FMUL": fa * fb, "FDIV": (fa / fb) if fb else None}[op]
        if v is None:
            return None
        if math.isnan(v):
            return "nan"
        try:
            return int.from_bytes(struct.pack(code, v), "little")
        except OverflowError:
            return int.from_bytes(struct.pack(code, math.copysign(math.inf, v)), "little")
    except Exception:
        return None


def dec(fr, sig=25):
    if fr == 0:
        return "0"
    with localcontext() as ctx:
        ctx.prec = sig + 10
        d = Decimal(fr.numerator) / Decimal(fr.denominator)
    return f"{d:.{sig}g}"


def decode_str(bits, name, E, M):
    n, bias, emax = fp_params(E, M)
    s, e, m = fp_split(bits, E, M)
    cls = fp_class(bits, E, M)
    sign = "-" if s else "+"
    if cls == "NaN":
        return f"{name} = NaN  (exp all ones, mantissa != 0)"
    if cls == "Infinity":
        return f"{name} = {sign}Infinity  (exp all ones, mantissa = 0)"
    if cls == "Zero":
        return f"{name} = {sign}0"
    if cls == "Subnormal":
        return f"{name} = (-1)^{s} x {m / 2 ** M:.6g} x 2^{1 - bias}  (subnormal, no hidden 1)"
    return f"{name} = (-1)^{s} x {1 + m / 2 ** M:.6f} x 2^{e - bias}"


def fp_trace(op, a, b, E, M):
    n, bias, emax = fp_params(E, M)
    res, fl, exact, note = fp_exec(op, a, b, E, M)
    ref = fp_reference(op, a, b, E, M)
    verified = None
    if ref is not None:
        verified = (fp_class(res, E, M) == "NaN") if ref == "nan" else (ref == res)
    tr = {"mode": "FPU", "op": op, "n": n, "E": E, "M": M, "a": a, "b": b,
          "abits": a, "bbits": b, "result": res, "flags": fl, "flag_defs": FPU_FLAGS,
          "astr": fp_str(a, E, M), "bstr": fp_str(b, E, M), "rstr": fp_str(res, E, M),
          "exact": exact, "note": note, "verified": verified, "extra": None}
    tr["working"] = working_fpu(tr)
    return tr


def working_fpu(tr):
    E, M, n, op = tr["E"], tr["M"], tr["n"], tr["op"]
    bias = (1 << (E - 1)) - 1
    a, b, r = tr["abits"], tr["bbits"], tr["result"]

    def fields(bits):
        s, e, m = fp_split(bits, E, M)
        return f"{s} | {e:0{E}b} | {m:0{M}b}"

    L = [f"Format         : {n}-bit   sign(1) | exponent({E}, bias {bias}) | mantissa({M}, hidden leading 1)",
         f"A  bits        : {fields(a)}",
         f"                 {decode_str(a, 'A', E, M)}      value = {tr['astr']}"]
    if op not in UNARY:
        L += [f"B  bits        : {fields(b)}",
              f"                 {decode_str(b, 'B', E, M)}      value = {tr['bstr']}"]
    L += [f"R  bits        : {fields(r)}",
          f"                 {decode_str(r, 'R', E, M)}      value = {tr['rstr']}", ""]
    if tr["exact"] is not None:
        L.append(f"Exact result   : {dec(tr['exact'])}")
        stored = fp_exact(r, E, M)
        if stored is not None:
            L.append(f"Stored result  : {dec(stored)}")
            err = stored - tr["exact"]
            L.append("Rounding error : " + (dec(err, 12) if err != 0 else "0  (result is exactly representable)"))
        else:
            L.append("Stored result  : overflowed to infinity")
    if tr["note"]:
        L.append(tr["note"])
    L.append("")
    L.append(f"Hex {hexw(r, n)}   Bin {r:0{n}b}")
    return "\n".join(L)


# ----------------------------------------------------------------------
# Animation plan
# ----------------------------------------------------------------------

def stage_plan(mode, op, n):
    """Return (messages, result_stage, flag_stage, durations_ms)."""
    if mode == "ALU":
        if op in ADDER_OPS:
            msgs = [
                "Loading operand A into the adder input register",
                "Loading operand B" + (" and inverting it (A + ~B + 1)" if op in ("SUB", "CMP", "DEC", "NEG") else ""),
                "Carry ripples through the full adders, LSB to MSB",
                "Sum bits written into the result register" if op != "CMP" else "Difference computed (CMP keeps only the flags)",
                "Flag logic updates ZERO / CARRY / SIGN / OVERFLOW",
            ]
            return msgs, 3, 4, [650, 650, max(900, 75 * n), 800, 800]
        if op in LOGIC:
            msgs = [
                "Loading operand A into register A",
                "Loading operand B" if op != "NOT" else "Operand B is not used by NOT",
                f"All {n} {op} gates evaluate in parallel",
                "Gate outputs written into the result register",
                "Flag logic updates ZERO / CARRY / SIGN / OVERFLOW",
            ]
            return msgs, 3, 4, [650, 650, 1400, 800, 800]
        if op in SHIFTS:
            S = n.bit_length() - 1
            verb = {"SHL": "shift left", "SHR": "shift right", "SAR": "arithmetic shift right",
                    "ROL": "rotate left", "ROR": "rotate right"}[op]
            msgs = ["Loading operand A into register A",
                    f"Loading shift amount (B mod {n}) into the control register"]
            msgs += [f"Mux stage {k}: {verb} by {1 << k} if select bit {k} is 1" for k in range(S)]
            msgs += ["Shifted value written into the result register",
                     "Flag logic updates ZERO / CARRY / SIGN / OVERFLOW"]
            return msgs, 2 + S, 3 + S, [600, 600] + [750] * S + [800, 800]
        what = "Shift-and-add multiplier running" if op == "MUL" else "Restoring divider running"
        msgs = ["Loading operand A into register A", "Loading operand B into register B", what,
                "Result written into the result register", "Flag logic updates ZERO / CARRY / SIGN / OVERFLOW"]
        return msgs, 3, 4, [650, 650, 2200, 800, 800]
    msgs = [
        "Loading Float A into register A",
        "Loading Float B into register B",
        "Unpacking sign, exponent and mantissa fields",
        "Exponent logic working",
        "Mantissa datapath working",
        "Normalizing and rounding the result",
        "Writing result into the result register",
        "Updating FPU status flags",
    ]
    return msgs, 6, 7, [600, 600, 900, 1000, 1000, 900, 800, 800]


# ----------------------------------------------------------------------
# Bit strip widget
# ----------------------------------------------------------------------

class BitStrip(Canvas):
    def __init__(self, parent, color, on_toggle=None, hint=None):
        super().__init__(parent, height=50, bg=PANEL, highlightthickness=0)
        self.color = color
        self.on_toggle = on_toggle
        self.hint = hint
        self.value = None
        self.n = 32
        self.fmt = None            # (E, M) for float layouts
        self.cells = []
        self.hover = None

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)

    def set(self, value):
        self.value = value
        self.redraw()

    def set_layout(self, n, fmt=None):
        self.n, self.fmt = n, fmt
        self.hover = None
        self.redraw()

    def hit(self, x):
        for x0, x1, bit in self.cells:
            if x0 <= x <= x1:
                return bit
        return None

    def field_of(self, bit):
        if self.fmt is None:
            return None
        E, M = self.fmt
        return "sign" if bit == self.n - 1 else ("exponent" if bit >= M else "mantissa")

    def on_motion(self, event):
        bit = self.hit(event.x)
        if bit != self.hover:
            self.hover = bit
            self.redraw()
        self.configure(cursor="hand2" if (bit is not None and self.on_toggle) else "")
        if bit is not None and self.hint:
            field = self.field_of(bit)
            weight = f"  weight 2^{bit}" if self.fmt is None else ""
            self.hint(f"Bit {bit}" + (f" ({field})" if field else weight) +
                      ("  |  click to toggle" if self.on_toggle else ""))

    def on_leave(self, event):
        self.hover = None
        self.configure(cursor="")
        self.redraw()

    def on_click(self, event):
        bit = self.hit(event.x)
        if bit is not None and self.on_toggle:
            self.on_toggle(bit)

    def bit_color(self, bit):
        if self.fmt is not None:
            E, M = self.fmt
            if bit == self.n - 1:
                return RED
            if bit >= M:
                return AMBER
        return self.color

    def redraw(self):
        self.delete("all")
        self.cells = []
        n = self.n
        gap = 6
        groups = (n + 3) // 4
        width = max(self.winfo_width(), 300)
        cw = min((width - 2 - (groups - 1) * gap) / n, 30)
        total = n * cw + (groups - 1) * gap
        x_off = max(1, (width - total) / 2)

        def bit_x(bit):
            idx = n - 1 - bit
            return x_off + idx * cw + (idx // 4) * gap

        if self.fmt is not None:
            E, M = self.fmt

            def span(hi, lo):
                return bit_x(hi), bit_x(lo) + cw - 2

            for (hi, lo), text_long, text_short, color in (
                    ((n - 1, n - 1), "S", "S", RED),
                    ((n - 2, M), f"EXPONENT ({E})", f"E({E})", AMBER),
                    ((M - 1, 0), f"MANTISSA ({M})", f"M({M})", BLUE_L)):
                x0, x1 = span(hi, lo)
                self.create_text((x0 + x1) / 2, 7, text=text_long if x1 - x0 > 90 else text_short,
                                 fill=color, font=(UI, 8, "bold"))

        fsize = 10 if cw >= 18 else (8 if cw >= 12 else 7)
        for index in range(n):
            bit = n - 1 - index
            x = bit_x(bit)
            on = self.value is not None and ((self.value >> bit) & 1)
            self.create_rectangle(x, 17, x + cw - 2, 45,
                                  fill=self.bit_color(bit) if on else OFF,
                                  outline="white" if bit == self.hover else "", width=2)
            self.create_text(x + (cw - 2) / 2, 31, text="1" if on else "0",
                             fill="white" if on else MUTED, font=(MONO, fsize, "bold"))
            if self.fmt is None and (n <= 16 or bit % 8 in (0, 7)):
                self.create_text(x + (cw - 2) / 2, 8, text=str(bit), fill=MUTED, font=(UI, 7))
            self.cells.append((x, x + cw - 2, bit))


# ----------------------------------------------------------------------
# Circuit view
# ----------------------------------------------------------------------

class CircuitView(Canvas):
    W = 1000
    H = 360

    def __init__(self, parent, app):
        super().__init__(parent, height=self.H, bg=SCOPE,
                         highlightthickness=1, highlightbackground=BORDER)
        self.app = app
        self.mode = "ALU"
        self.op = "ADD"
        self.n = 32
        self.fmt = (8, 23)
        self.trace = None
        self.stage = None
        self.t = 0.0
        self.base = 0
        self.ox = 0
        self.k = 1.0
        self.hot = []
        self._tip = None

        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Button-1>", self.on_click)
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", lambda e: self.configure(cursor=""))

    # ---- state ------------------------------------------------------

    def set_scene(self, mode, op, n, fmt=None):
        self.mode, self.op, self.n = mode, op, n
        if fmt:
            self.fmt = fmt
        self.base = 0

    def set_trace(self, trace):
        self.trace = trace

    def set_animation(self, stage, t):
        self.stage, self.t = stage, t

    def state(self, stage):
        if self.trace is None:
            return "idle"
        if self.stage is None or stage < self.stage:
            return "done"
        return "active" if stage == self.stage else "idle"

    @staticmethod
    def tone(color, state):
        return color if state == "done" else (YELLOW if state == "active" else DIM)

    def resolved(self, bit):
        s = self.state(2)
        if s == "done":
            return True
        return s == "active" and bit < int(self.t * (self.n + 1))

    def gates_ready(self):
        s = self.state(2)
        return s == "done" or (s == "active" and self.t > 0.3)

    def pick(self, bit):
        self.base = bit
        self.draw()

    # ---- interaction ------------------------------------------------

    def find_hot(self, event):
        x, y = (event.x - self.ox) / self.k, event.y / self.k
        for hx, hy, hw, hh, tip, cb in self.hot:
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                return tip, cb
        return None, None

    def on_motion(self, event):
        tip, cb = self.find_hot(event)
        self.configure(cursor="hand2" if cb else "")
        if tip and tip != self._tip and self.stage is None:
            self._tip = tip
            self.app.set_status(tip, MUTED)

    def on_click(self, event):
        tip, cb = self.find_hot(event)
        if cb:
            cb()

    # ---- drawing primitives -------------------------------------------

    def rect(self, x, y, w, h, fill=NODE, outline=WIRE, width=2):
        k = self.k
        self.create_rectangle(self.ox + x * k, y * k, self.ox + (x + w) * k, (y + h) * k,
                              fill=fill, outline=outline, width=width)

    def label(self, x, y, text, fill=TEXT, font=None, anchor="center"):
        f = font or (UI, 9, "bold")
        f = (f[0], max(6, int(round(f[1] * self.k)))) + tuple(f[2:])
        self.create_text(self.ox + x * self.k, y * self.k, text=text, fill=fill,
                         font=f, anchor=anchor, justify="center")

    def polyline(self, pts, color, width=2, arrow=False):
        flat = []
        for px, py in pts:
            flat += [self.ox + px * self.k, py * self.k]
        self.create_line(*flat, fill=color, width=width,
                         arrow="last" if arrow else "none", joinstyle="round")

    def shape(self, pts, fill, outline):
        flat = []
        for px, py in pts:
            flat += [self.ox + px * self.k, py * self.k]
        self.create_polygon(*flat, fill=fill, outline=outline, width=2)

    def packet(self, pts, f, color):
        segs, total = [], 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            length = math.hypot(x1 - x0, y1 - y0)
            segs.append((x0, y0, x1, y1, length))
            total += length
        if total == 0:
            return
        d = min(max(f, 0.0), 1.0) * total
        for x0, y0, x1, y1, length in segs:
            if d <= length:
                k = d / length if length else 0
                px, py = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
                r = 5 * self.k
                cx, cy = self.ox + px * self.k, py * self.k
                self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="white", width=1)
                return
            d -= length

    def wire(self, stage, pts, color, level=1, arrow=True, packet=True, on=None):
        s = self.state(stage)
        if on is False or s == "idle":
            c = DIM
        elif not level:
            c = WIRE
        else:
            c = color
        self.polyline(pts, c, 2, arrow)
        if packet and s == "active" and self.stage is not None:
            self.packet(pts, self.t, YELLOW)

    def block(self, stage, x, y, w, h, title, body, color, tip="", fs=10):
        s = self.state(stage)
        self.rect(x, y, w, h, fill=ACTIVE_FILL if s == "active" else NODE,
                  outline=self.tone(color, s), width=3 if s == "active" else 2)
        self.label(x + w / 2, y + 13, title, fill=color if s != "idle" else MUTED, font=(UI, 8, "bold"))
        if body is not None:
            shown = body if (s != "idle" and body != "") else "..."
            self.label(x + w / 2, y + h / 2 + 8, shown,
                       fill=TEXT if s != "idle" else MUTED, font=(MONO, fs, "bold"))
        if tip:
            self.hot.append((x, y, w, h, tip, None))

    def chip(self, x, y, w, h, name, val, color, known=True, text=None):
        if known:
            fill = color if val else OFF
            txt = text if text is not None else f"{name}={val}"
            fg = "white" if val else MUTED
        else:
            fill, fg = OFF, MUTED
            txt = f"{name}=?"
        self.rect(x, y, w, h, fill=fill, outline=BORDER, width=1)
        self.label(x + w / 2, y + h / 2, txt, fill=fg, font=(MONO, 8, "bold"))

    def gate(self, kind, x, y, w, h, color, state, text=None):
        c = self.tone(color, state)
        fill = ACTIVE_FILL if state == "active" else NODE
        base = {"NAND": "AND", "NOR": "OR", "XNOR": "XOR"}.get(kind, kind)
        bubble = kind in ("NOT", "NAND", "NOR", "XNOR")
        if base == "NOT":
            self.shape([(x, y), (x + w - 8, y + h / 2), (x, y + h)], fill, c)
            bx = x + w - 4
        else:
            if base in ("OR", "XOR"):
                self.shape([(x, y), (x + w * .5, y), (x + w, y + h / 2),
                            (x + w * .5, y + h), (x, y + h), (x + w * .2, y + h / 2)], fill, c)
                if base == "XOR":
                    self.polyline([(x - 5, y), (x + w * .2 - 5, y + h / 2), (x - 5, y + h)], c, 2)
            else:
                self.shape([(x, y), (x + w * .55, y), (x + w, y + h * .3),
                            (x + w, y + h * .7), (x + w * .55, y + h), (x, y + h)], fill, c)
            bx = x + w + 3
        if bubble:
            r = 4 * self.k
            cx, cy = self.ox + bx * self.k, (y + h / 2) * self.k
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline=c, width=2)
        self.label(x + w * .45, y + h / 2, text or kind,
                   fill="white" if state != "idle" else MUTED, font=(UI, 7, "bold"))

    def flag_block(self, stage, x, y, w, h):
        s = self.state(stage)
        tr = self.trace
        defs = tr["flag_defs"] if tr else (ALU_FLAGS if self.mode == "ALU" else FPU_FLAGS)
        self.rect(x, y, w, h, fill=ACTIVE_FILL if s == "active" else NODE,
                  outline=self.tone(RED, s), width=3 if s == "active" else 2)
        self.label(x + w / 2, y + 13, "FLAG LOGIC", fill=RED if s != "idle" else MUTED, font=(UI, 8, "bold"))
        rows = (len(defs) + 1) // 2
        step = min(38, (h - 34) / rows)
        ch = min(30, step - 6)
        cw = (w - 24) / 2
        for i, (key, name, color, tip) in enumerate(defs):
            cx = x + 8 + (i % 2) * (cw + 8)
            cy = y + 30 + (i // 2) * step
            known = s != "idle"
            val = int(tr["flags"].get(key, 0)) if (tr and known) else 0
            self.chip(cx, cy, cw, ch, name, val, color, known)
            self.hot.append((cx, cy, cw, ch, tip, None))

    def strip(self, title, getter, ready, color, span, cur=None):
        n = self.n
        span = min(span, n)
        self.label(500, 298, title, fill=MUTED, font=(UI, 8))
        cw = min(29, 930 / n)
        x0 = (1000 - n * cw) / 2
        fsz = 9 if cw >= 20 else 7
        for k in range(n):
            bi = n - 1 - k
            x = x0 + k * cw
            known = ready(bi)
            v = getter(bi) if known else 0
            fill = color if (known and v) else OFF
            if cur is not None and bi == cur:
                fill = YELLOW
            self.rect(x, 310, cw - 3, 26, fill=fill, outline=BORDER, width=1)
            self.label(x + (cw - 3) / 2, 323, str(v) if known else ".",
                       fill="white" if (known and v) else MUTED, font=(MONO, fsz, "bold"))
            if bi % 4 == 0 or n <= 8:
                self.label(x + (cw - 3) / 2, 346, str(bi), fill=MUTED, font=(UI, 7))
            self.hot.append((x, 310, cw - 3, 26, f"Bit {bi}: click to inspect this slice",
                             lambda b=bi: self.pick(b)))
        base = (self.base // span) * span
        k0 = n - 1 - (base + span - 1)
        kk = self.k
        self.create_rectangle(self.ox + (x0 + k0 * cw - 2) * kk, 306 * kk,
                              self.ox + (x0 + (k0 + span) * cw - 1) * kk, 340 * kk,
                              outline=BLUE_L, width=2)

    # ---- main draw ----------------------------------------------------

    def draw(self):
        self.delete("all")
        self.hot = []
        width = self.winfo_width()
        if width < 50:
            width = self.W
        self.k = min(max(width / self.W, 0.5), 1.6)
        self.ox = max(0, (width - self.W * self.k) / 2)
        target_h = int(self.H * self.k)
        if int(float(self.cget("height"))) != target_h:
            self.configure(height=target_h)

        size = f"{self.n}-bit" if self.mode == "ALU" else FP_FORMATS_BY_BITS.get(self.fmt, "")
        self.label(500, 16, f"CIRCUIT: {self.op}   ({size})", font=(UI, 14, "bold"))
        self.label(500, 36, circuit_info(self.op, self.n), fill=MUTED, font=(UI, 10))

        if self.mode == "ALU":
            if self.op in ADDER_OPS:
                self.scene_adder()
            elif self.op in LOGIC:
                self.scene_logic()
            elif self.op in SHIFTS:
                self.scene_shifter()
            else:
                self.scene_arith()
        else:
            self.scene_fpu()

    def alu_sides(self, xv, yv, lx, ly, unary_b=False, sub=False, bb=0):
        tr = self.trace
        n = self.n
        fs = 9 if n <= 32 else 7
        self.block(0, 10, 50, 115, 64, lx, hexw(xv, n) if tr else "", BLUE, f"{lx.title()} holds this operand", fs)
        self.block(1, 10, 140, 115, 64, ly,
                   ("unused" if unary_b else hexw(yv, n)) if tr else "", BLUE, f"{ly.title()} holds this operand", fs)
        self.wire(0, [(125, 82), (200, 82)], BLUE)
        self.wire(1, [(125, 172), (200, 172)], RED if sub else BLUE)
        if sub:
            self.polyline([(67, 204), (67, 230)], self.tone(RED, self.state(1)), 2, True)
            self.block(1, 10, 230, 115, 54, "NOT B  (+1)", hexw(bb, n) if tr else "", RED,
                       "Operand is inverted and carry-in is forced to 1", fs)

    def alu_right(self, result_stage, flag_stage):
        tr = self.trace
        n = self.n
        r = tr["result"] if tr else 0
        self.block(result_stage, 785, 48, 205, 76, "RESULT REGISTER",
                   hexw(r, n) if tr else "", GREEN, "Result register", 11 if n <= 32 else 9)
        self.wire(result_stage, [(770, 86), (785, 86)], GREEN)
        self.flag_block(flag_stage, 785, 150, 205, 134)
        self.wire(flag_stage, [(887, 124), (887, 150)], RED)

    # ---- ADD / SUB / INC / DEC / NEG / CMP --------------------------------

    def scene_adder(self):
        tr = self.trace
        n = self.n
        op = self.op
        sub = op in ("SUB", "CMP", "DEC", "NEG")
        x = tr["x"] if tr else 0
        y = tr["y"] if tr else 0
        bb = tr["bb"] if tr else 0
        carries = tr["carries"] if tr else [0] * (n + 1)
        sums = tr["sums"] if tr else [0] * n
        lx, ly = adder_labels(op)

        self.alu_sides(x, y, lx, ly, sub=sub, bb=bb)
        if not sub:
            self.label(67, 250, "carry-in = 0", fill=MUTED, font=(UI, 8))
        self.alu_right(3, 4)

        base = (self.base // 4) * 4
        self.rect(200, 48, 570, 240, fill="#0E1730", outline=BORDER, width=1)
        self.label(485, 60, f"RIPPLE-CARRY ADDER   bits {base + 3} .. {base}",
                   fill=ORANGE if self.state(2) != "idle" else MUTED, font=(UI, 9, "bold"))

        a_known = self.state(0) != "idle"
        b_known = self.state(1) != "idle"
        cur = min(n - 1, int(self.t * (n + 1))) if self.state(2) == "active" else None

        for i in range(4):
            cx = 222 + i * 126
            bi = base + 3 - i
            res = self.resolved(bi)
            is_cur = cur is not None and bi == cur
            a_i, b_i = (x >> bi) & 1, (bb >> bi) & 1
            c_i, s_i, co = carries[bi], sums[bi], carries[bi + 1]
            gstate = "active" if is_cur else ("done" if res else "idle")

            self.rect(cx, 68, 118, 196, fill=NODE,
                      outline=YELLOW if is_cur else (ORANGE if res else DIM),
                      width=3 if is_cur else 2)
            self.label(cx + 59, 79, f"FULL ADDER  BIT {bi}", fill=MUTED, font=(UI, 7, "bold"))

            cin_known = res or (bi == 0 and b_known)
            self.chip(cx + 5, 90, 34, 20, "A", a_i, BLUE, a_known)
            self.chip(cx + 42, 90, 34, 20, "B", b_i, BLUE, b_known)
            self.chip(cx + 79, 90, 34, 20, "C", c_i, AMBER, cin_known)

            inputs = ((cx + 22, a_i), (cx + 59, b_i), (cx + 96, c_i))
            for k_, (px, lvl) in enumerate(inputs):
                self.wire(2, [(px, 110), (cx + 14 + k_ * 17, 132)], ORANGE, lvl, False, False, res)
                self.wire(2, [(px, 110), (cx + 70 + k_ * 17, 132)], AMBER, lvl, False, False, res)

            self.gate("XOR", cx + 8, 132, 46, 30, ORANGE, gstate, "SUM")
            self.gate("AND", cx + 64, 132, 46, 30, AMBER, gstate, "MAJ")

            self.wire(2, [(cx + 31, 162), (cx + 31, 180)], GREEN, s_i, True, False, res)
            self.wire(2, [(cx + 87, 162), (cx + 87, 180)], AMBER, co, True, False, res)
            self.chip(cx + 8, 180, 46, 20, "S", s_i, GREEN, res)
            self.chip(cx + 64, 180, 46, 20, "Co", co, AMBER, res)

            self.label(cx + 59, 220, f"{a_i}+{b_i}+{c_i} = {2 * co + s_i}" if res else "waiting...",
                       fill=AMBER if res else MUTED, font=(MONO, 9, "bold"))

            if i >= 1:
                self.wire(2, [(cx + 87, 200), (cx + 87, 244), (cx - 4, 244),
                              (cx - 4, 100), (cx - 13, 100)], AMBER, co, True, False, res)
            self.hot.append((cx, 68, 118, 196,
                             f"Bit {bi}: A={a_i} B={b_i} Cin={c_i}  ->  Sum={s_i} Cout={co}", None))

        carry_known = self.resolved(base - 1) if base > 0 else b_known
        self.chip(726, 90, 38, 20, "C", carries[base], AMBER, carry_known)
        self.label(745, 122, "carry-in", fill=MUTED, font=(UI, 7))
        self.wire(2, [(726, 100), (713, 100)], AMBER, carries[base], True, False, carry_known)

        self.strip("CARRY CHAIN  (carry-out of each bit)  -  click a bit to inspect its 4-bit slice",
                   lambda bi: carries[bi + 1], self.resolved, AMBER, 4, cur)

    # ---- logic gates ------------------------------------------------------

    def scene_logic(self):
        tr = self.trace
        n = self.n
        op = self.op
        unary = op == "NOT"
        a = tr["a"] if tr else 0
        b = tr["b"] if tr else 0
        r = tr["result"] if tr else 0
        sym = {"AND": "&", "OR": "|", "XOR": "^", "NOT": "~", "NAND": "~&", "NOR": "~|", "XNOR": "~^"}[op]

        self.alu_sides(a, b, "REGISTER A", "REGISTER B", unary_b=unary)
        self.alu_right(3, 4)

        sl = min(8, n)
        base = (self.base // sl) * sl
        self.rect(200, 48, 570, 240, fill="#0E1730", outline=BORDER, width=1)
        self.label(485, 60, f"{op} GATE ARRAY   bits {base + sl - 1} .. {base}",
                   fill=CYAN if self.state(2) != "idle" else MUTED, font=(UI, 9, "bold"))

        a_known = self.state(0) != "idle"
        b_known = self.state(1) != "idle"
        ready = self.gates_ready()

        for idx in range(sl):
            row, col = divmod(idx, 4)
            bi = base + sl - 1 - idx
            cx, cy = 210 + col * 138, 70 + row * 104
            a_i, b_i, y_i = (a >> bi) & 1, (b >> bi) & 1, (r >> bi) & 1
            gstate = ("active" if self.state(2) == "active" else "done") if ready else "idle"

            self.rect(cx, cy, 128, 96, fill=NODE, outline=CYAN if ready else DIM, width=2)
            self.label(cx + 64, cy + 8, f"BIT {bi}", fill=MUTED, font=(UI, 7, "bold"))
            self.chip(cx + 6, cy + 20, 40, 20, "A", a_i, BLUE, a_known)
            if not unary:
                self.chip(cx + 6, cy + 56, 40, 20, "B", b_i, BLUE, b_known)
            self.wire(2, [(cx + 46, cy + 30), (cx + 56, cy + 38)], CYAN, a_i, False, False, ready)
            if not unary:
                self.wire(2, [(cx + 46, cy + 66), (cx + 56, cy + 54)], CYAN, b_i, False, False, ready)
            self.gate(op, cx + 54, cy + 26, 34, 40, CYAN, gstate)
            self.wire(2, [(cx + 92, cy + 46), (cx + 100, cy + 46)], GREEN, y_i, False, False, ready)
            self.chip(cx + 100, cy + 36, 26, 20, "Y", y_i, GREEN, ready)
            expr = f"{sym}{a_i} = {y_i}" if unary else f"{a_i} {sym} {b_i} = {y_i}"
            self.label(cx + 64, cy + 86, expr if ready else "waiting...",
                       fill=CYAN if ready else MUTED, font=(MONO, 9, "bold"))

        self.strip(f"RESULT BITS  -  click a bit to inspect its {sl}-bit slice",
                   lambda bi: (r >> bi) & 1, lambda bi: self.gates_ready(), GREEN, sl)

    # ---- barrel shifter -----------------------------------------------------

    def scene_shifter(self):
        tr = self.trace
        n = self.n
        op = self.op
        S = n.bit_length() - 1
        a = tr["a"] if tr else 0
        amt = tr["amt"] if tr else 0
        digits = (n + 3) // 4
        fs = 9 if n <= 32 else 7

        self.block(0, 10, 60, 115, 64, "REGISTER A", hexw(a, n) if tr else "", BLUE, "Value to shift", fs)
        self.block(1, 10, 160, 115, 70, "SHIFT AMOUNT",
                   f"{amt}\n{amt:0{S}b}" if tr else "", PURPLE, f"Shift amount = B mod {n}", 10)
        self.wire(0, [(125, 92), (140, 92), (140, 145), (155, 145)], BLUE)

        w = min(130, (610 - (S - 1) * 14) / S)
        gap = (610 - S * w) / (S - 1) if S > 1 else 0
        last_center = 155
        for k in range(S):
            x = 155 + k * (w + gap)
            stage = 2 + k
            on = tr["steps"][k][0] if tr else 0
            val = tr["steps"][k][1] if tr else 0
            color = PURPLE if on else "#6B7BA0"
            body = f"{'ACTIVE' if on else 'BYPASS'}\n{short_hex(val, digits, 8)[2:]}" if tr else ""
            self.block(stage, x, 100, w, 90, f"{op} BY {1 << k}", body, color,
                       f"Mux stage {k}: select bit {k} = {on}", 10 if S <= 5 else 9)
            sel_known = self.state(1) != "idle"
            self.chip(x + w / 2 - 25, 205, 50, 20, f"s{k}", on, PURPLE, sel_known)
            self.wire(stage, [(x + w / 2, 250), (x + w / 2, 225)], PURPLE, on, True, False)
            if k < S - 1:
                self.wire(stage, [(x + w, 145), (x + w + gap, 145)], PURPLE if on else WIRE, 1)
            last_center = x + w / 2

        self.wire(1, [(67, 230), (67, 250), (last_center, 250)], PURPLE, 1, False, False)
        r = tr["result"] if tr else 0
        rs, fs_ = 2 + S, 3 + S
        self.wire(rs, [(765, 145), (775, 145), (775, 92), (785, 92)], GREEN)
        self.block(rs, 785, 60, 205, 64, "RESULT REGISTER", hexw(r, n) if tr else "", GREEN, "Result",
                   11 if n <= 32 else 9)
        self.flag_block(fs_, 785, 150, 205, 134)
        self.wire(fs_, [(887, 124), (887, 150)], RED)

        if tr:
            parts = [str(1 << k) for k in range(S) if (amt >> k) & 1]
            note = (f"shift {amt} = {' + '.join(parts) if parts else '0'}   "
                    f"({S} mux stages instead of {n - 1} sequential shifts)")
            if tr["b"] >= n:
                note += f"   |   B >= {n}: B mod {n} used"
            self.label(500, 300, note, fill=MUTED, font=(UI, 9))

    # ---- MUL / DIV / MOD ------------------------------------------------------

    def scene_arith(self):
        tr = self.trace
        op = self.op
        a = tr["a"] if tr else 0
        b = tr["b"] if tr else 0
        self.alu_sides(a, b, "REGISTER A", "REGISTER B")
        self.alu_right(3, 4)

        s = self.state(2)
        self.rect(200, 48, 570, 240, fill="#0E1730", outline=PINK if s != "idle" else BORDER, width=2)
        title = {"MUL": "SHIFT-AND-ADD MULTIPLIER", "DIV": "RESTORING DIVIDER",
                 "MOD": "RESTORING DIVIDER (remainder output)"}[op]
        self.label(485, 62, title, fill=PINK if s != "idle" else MUTED, font=(UI, 9, "bold"))
        lines = tr["lines"] if tr else []
        if s == "idle" or not lines:
            self.label(485, 160, "...", fill=MUTED, font=(MONO, 14, "bold"))
        else:
            cnt = len(lines) if s == "done" else max(1, int(self.t * len(lines)) + 1)
            for i, line in enumerate(lines[:cnt][:11]):
                self.label(215, 84 + i * 17, line, fill=YELLOW if (i == 0) else TEXT,
                           font=(MONO, 9, "bold"), anchor="w")
            if s == "done" and tr["note"]:
                self.label(485, 276, tr["note"], fill=PINK, font=(MONO, 9, "bold"))

    # ---- Float datapath ----------------------------------------------------

    def scene_fpu(self):
        tr = self.trace
        op = self.op
        E, M = (tr["E"], tr["M"]) if tr else self.fmt
        n, bias, emax = fp_params(E, M)
        hd = (M + 3) // 4
        sd = (M + 1 + 3) // 4
        ab = bb = rb = 0
        if tr:
            ab, bb, rb = tr["abits"], tr["bbits"], tr["result"]
            sa, ea, _ = fp_split(ab, E, M)
            sb, eb, _ = fp_split(bb, E, M)
            sr, er, mr_raw = fp_split(rb, E, M)
            ma, mb = fp_sig(ab, E, M), fp_sig(bb, E, M)

        self.block(0, 10, 40, 120, 70, "FLOAT A REGISTER",
                   f"{tr['astr']}\n{short_hex(ab, (n + 3) // 4, 10)}" if tr else "", BLUE, "Operand A", 9)
        self.block(1, 10, 175, 120, 70, "FLOAT B REGISTER",
                   f"{tr['bstr']}\n{short_hex(bb, (n + 3) // 4, 10)}" if tr else "", BLUE, "Operand B", 9)
        self.wire(0, [(130, 75), (160, 75)], BLUE)
        self.wire(1, [(130, 210), (160, 210)], BLUE)

        self.block(2, 160, 40, 210, 205, "UNPACK FIELDS", None, CYAN, "Split into sign | exponent | mantissa")
        known = self.state(2) != "idle"
        for row, (name, bits) in enumerate((("A", ab), ("B", bb))):
            s_, e_, m_ = fp_split(bits, E, M)
            y0 = 62 + row * 90
            self.label(170, y0 + 8, f"Float {name}", fill=TEXT, font=(UI, 9, "bold"), anchor="w")
            self.chip(168, y0 + 22, 30, 22, "S", s_, RED, known)
            self.chip(202, y0 + 22, 56, 22, "E", e_, AMBER, known)
            mtxt = f"M=0x{m_:0{hd}X}" if hd <= 6 else f"0x{m_:0{hd}X}"
            self.chip(262, y0 + 22, 100, 22, "M", m_, BLUE, known, text=mtxt)
            cls = fp_class(bits, E, M) if (known and tr) else "?"
            self.label(170, y0 + 58, f"class: {cls}" +
                       (f"   bias-removed e = {e_ - bias}" if known and tr and cls == "Normal" else ""),
                       fill=MUTED, font=(UI, 8), anchor="w")

        ex_title, ex_body, mt_title, mt_body = "EXPONENT LOGIC", "", "MANTISSA DATAPATH", ""
        if tr:
            sh = lambda v: short_hex(v, sd, 12)
            if op in ("FADD", "FSUB"):
                ex_title = "EXP COMPARE / ALIGN"
                ex_body = f"eA={ea}  eB={eb}\nshift {'B' if ea >= eb else 'A'} right by {abs(ea - eb)}"
                mt_title = "MANTISSA ADD / SUB"
                mt_body = f"A={sh(ma)}\nB={sh(mb)}"
            elif op == "FMUL":
                ex_title = "EXPONENT ADDER"
                ex_body = f"{ea}+{eb}-{bias}\n= {ea + eb - bias}"
                mt_title = "MANTISSA MULTIPLIER"
                mt_body = f"{sh(ma)} x\n{sh(mb)}\n= {short_hex(ma * mb, 2 * sd, 12)}"
            elif op == "FDIV":
                ex_title = "EXPONENT SUBTRACT"
                ex_body = f"{ea}-{eb}+{bias}\n= {ea - eb + bias}"
                mt_title = "MANTISSA DIVIDER"
                mt_body = f"{sh(ma)} /\n{sh(mb)}"
            elif op in ("FNEG", "FABS"):
                ex_title = "SIGN LOGIC"
                ex_body = f"sign: {sa} -> {1 - sa if op == 'FNEG' else 0}\n({'flip' if op == 'FNEG' else 'clear'} MSB)"
                mt_title = "MANTISSA BYPASS"
                mt_body = f"unchanged\n{sh(ma)}"
            else:
                rel = "eA > eB" if ea > eb else ("eA < eB" if ea < eb else "eA = eB")
                ex_title = "EXP COMPARATOR"
                ex_body = f"eA={ea}  eB={eb}\n{rel}"
                mt_title = "MANTISSA COMPARE"
                mt_body = f"mA={sh(ma)}\nmB={sh(mb)}"

        self.block(3, 390, 40, 210, 95, ex_title, ex_body, PURPLE, "Exponent datapath", 9)
        self.block(4, 390, 150, 210, 95, mt_title, mt_body, CYAN, "Mantissa datapath", 9)
        self.wire(2, [(370, 87), (390, 87)], CYAN)
        self.wire(2, [(370, 197), (390, 197)], CYAN)
        self.wire(4, [(495, 135), (495, 150)], PURPLE)

        norm_title = "RESULT SELECT" if op == "FCMP" else "NORMALIZE & ROUND"
        norm_body = f"{fp_class(rb, E, M)}\ne={er}\nm={short_hex(mr_raw, hd, 10)}" if tr else ""
        self.block(5, 620, 40, 170, 205, norm_title, norm_body, AMBER, "Normalize, round to nearest even", 10)
        self.wire(5, [(600, 87), (620, 87)], PURPLE)
        self.wire(5, [(600, 197), (620, 197)], CYAN)

        self.block(6, 820, 40, 170, 70, "RESULT REGISTER",
                   f"{tr['rstr']}\n{short_hex(rb, (n + 3) // 4, 10)}" if tr else "", GREEN, "Result register", 9)
        self.wire(6, [(790, 75), (820, 75)], AMBER)
        self.flag_block(7, 820, 118, 170, 127)
        self.wire(7, [(905, 110), (905, 118)], RED)

        if tr:
            self.label(36, 262, "DECODED VALUES", fill=MUTED, font=(UI, 8, "bold"), anchor="w")
            if self.state(2) != "idle":
                self.label(36, 282, decode_str(ab, "A", E, M), fill=BLUE_L, font=(MONO, 10, "bold"), anchor="w")
                if op not in UNARY:
                    self.label(36, 302, decode_str(bb, "B", E, M), fill=BLUE_L, font=(MONO, 10, "bold"), anchor="w")
            if self.state(6) != "idle":
                self.label(36, 322, decode_str(rb, "R", E, M), fill=GREEN, font=(MONO, 10, "bold"), anchor="w")
        self.label(500, 348, f"{n}-bit float :  sign (1)  |  exponent ({E}, bias {bias})  |  mantissa ({M}, hidden leading 1)",
                   fill=MUTED, font=(UI, 9))


FP_FORMATS_BY_BITS = {(E, M): f"{key}  {desc}" for key, (E, M, desc) in FP_FORMATS.items()}


# ----------------------------------------------------------------------
# Main application
# ----------------------------------------------------------------------

class ALUApp(ctk.CTk):
    TICK = 33

    def __init__(self):
        super().__init__()

        self.title("COA Simulator Pro | Variable-width ALU + Multi-format FPU")
        self.geometry("1480x940")
        self.minsize(1200, 720)
        self.configure(fg_color=BG)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.a_strip = self.b_strip = self.r_strip = None
        self.circuit = None

        self.mode = "ALU"
        self.nbits = 32
        self.fmt_key = "FP32"
        self.operation = "ADD"
        self.previous_operation = None

        self.job = None
        self.plan = None
        self.anim_stage = None
        self.anim_t = 0.0
        self.trace = None
        self._last_snap = None

        self.history = []
        self.usage_counts = {op: 0 for op in list(ALU_OPS) + list(FPU_OPS)}

        self.graph_win = None
        self.graph_fig = self.graph_ax = self.graph_canvas = None

        self.build()
        self.set_mode("ALU")

        self.bind("<Return>", lambda e: self.calculate())
        self.bind("<Control-r>", lambda e: self.randomize())
        self.bind("<Escape>", lambda e: self.clear())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---- helpers ------------------------------------------------------

    @property
    def fmt(self):
        E, M, _ = FP_FORMATS[self.fmt_key]
        return E, M

    @property
    def total_bits(self):
        return self.nbits if self.mode == "ALU" else 1 + sum(self.fmt)

    def size_tag(self):
        return f"ALU{self.nbits}" if self.mode == "ALU" else self.fmt_key

    def set_status(self, text, color=MUTED):
        if hasattr(self, "status") and self.status.winfo_exists():
            self.status.configure(text=str(text), text_color=color)

    def set_entry(self, entry, text):
        disabled = entry.cget("state") == "disabled"
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, str(text))
        if disabled:
            entry.configure(state="disabled")

    def copy_text(self, text):
        if text and text not in ("-", "..."):
            self.clipboard_clear()
            self.clipboard_append(text)
            self.set_status(f"Copied {text} to clipboard", GREEN)

    def snapshot(self):
        return (self.mode, self.nbits, self.fmt_key, self.operation, self.a_entry.get(), self.b_entry.get())

    @staticmethod
    def fit(label, text, base, minimum=12):
        size = max(minimum, min(base, int(base * 14 / max(len(text), 14))))
        label.configure(text=text, font=(MONO, size, "bold"))

    # ---- UI construction ------------------------------------------------

    def build(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=0, padx=16, pady=12, sticky="nsew")
        main.grid_columnconfigure(0, minsize=350)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(header, text="Computer Organization & Architecture Simulator",
                     font=(UI, 23, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(header,
                     text="   4-64 bit ALU | ripple-carry adder | barrel shifter | multiplier/divider | FP8-FP64 FPU",
                     font=(UI, 11), text_color=MUTED).pack(side="left", pady=(8, 0))

        self.build_input_panel(main)
        self.build_output_panel(main)

        bar = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=10)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.status = ctk.CTkLabel(bar, text="Ready", font=(UI, 12), text_color=MUTED)
        self.status.pack(side="left", padx=14, pady=6)
        ctk.CTkLabel(bar, text="Enter: execute   Ctrl+R: random   Esc: clear",
                     font=(UI, 11), text_color=MUTED).pack(side="right", padx=14)

    def build_input_panel(self, parent):
        panel = ctk.CTkScrollableFrame(parent, corner_radius=16, fg_color=PANEL, width=330)
        panel.grid(row=1, column=0, padx=(0, 10), sticky="nsew")

        ctk.CTkLabel(panel, text="CONTROL UNIT", font=(UI, 13, "bold"),
                     text_color=BLUE).pack(anchor="w", padx=10, pady=(6, 0))

        mode_row = ctk.CTkFrame(panel, fg_color="transparent")
        mode_row.pack(fill="x", padx=5, pady=(8, 2))
        mode_row.grid_columnconfigure((0, 1), weight=1)
        self.alu_mode_button = ctk.CTkButton(mode_row, text="INTEGER ALU", height=32, font=(UI, 11, "bold"),
                                             command=lambda: self.set_mode("ALU"))
        self.alu_mode_button.grid(row=0, column=0, padx=2, sticky="ew")
        self.fpu_mode_button = ctk.CTkButton(mode_row, text="FLOAT FPU", height=32, font=(UI, 11, "bold"),
                                             command=lambda: self.set_mode("FPU"))
        self.fpu_mode_button.grid(row=0, column=1, padx=2, sticky="ew")

        self.size_label = ctk.CTkLabel(panel, text="Word size (bits)", font=(UI, 12, "bold"), text_color=MUTED)
        self.size_label.pack(anchor="w", padx=10, pady=(8, 0))
        self.size_row = ctk.CTkFrame(panel, fg_color="transparent")
        self.size_row.pack(fill="x", padx=5, pady=(3, 0))
        self.width_seg = ctk.CTkSegmentedButton(self.size_row, values=[str(w) for w in WIDTHS],
                                                command=self.on_width, font=(UI, 12, "bold"))
        self.fmt_seg = ctk.CTkSegmentedButton(self.size_row, values=list(FP_FORMATS),
                                              command=self.on_format, font=(UI, 11, "bold"))
        self.width_seg.set("32")
        self.fmt_seg.set("FP32")
        self.range_label = ctk.CTkLabel(panel, text="", font=(UI, 10), text_color=MUTED, justify="left")
        self.range_label.pack(anchor="w", padx=10, pady=(2, 0))

        self.a_label, self.a_entry = self.create_operand(panel, "Operand A")
        self.b_label, self.b_entry = self.create_operand(panel, "Operand B")

        ctk.CTkLabel(panel, text="Operation Select", font=(UI, 12, "bold"),
                     text_color=MUTED).pack(anchor="w", padx=10, pady=(10, 0))
        self.operation_grid = ctk.CTkFrame(panel, fg_color="transparent")
        self.operation_grid.pack(fill="x", padx=5, pady=(4, 0))
        self.op_buttons = {}

        self.run_button = ctk.CTkButton(panel, text="EXECUTE INSTRUCTION", height=42, font=(UI, 13, "bold"),
                                        fg_color=BLUE, hover_color="#2563EB", command=self.calculate)
        self.run_button.pack(fill="x", padx=8, pady=(12, 5))

        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(fill="x", padx=5)
        actions.grid_columnconfigure((0, 1, 2), weight=1)
        for col, (text, cmd) in enumerate((("Random", self.randomize), ("Clear", self.clear),
                                           ("Export CSV", self.export_history))):
            ctk.CTkButton(actions, text=text, height=30, fg_color=CARD, hover_color=BORDER,
                          command=cmd).grid(row=0, column=col, padx=2, sticky="ew")

        chain = ctk.CTkFrame(panel, fg_color="transparent")
        chain.pack(fill="x", padx=5, pady=(4, 0))
        chain.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(chain, text="Swap A <-> B", height=30, fg_color=CARD, hover_color=BORDER,
                      command=self.swap_operands).grid(row=0, column=0, padx=2, sticky="ew")
        ctk.CTkButton(chain, text="RESULT -> A", height=30, fg_color=CARD, hover_color=BORDER,
                      command=self.result_to_a).grid(row=0, column=1, padx=2, sticky="ew")

        self.example_menu = ctk.CTkOptionMenu(panel, values=["Examples..."], command=self.load_example,
                                              fg_color=CARD, button_color=BORDER, height=30)
        self.example_menu.pack(fill="x", padx=8, pady=(6, 0))

        ctk.CTkButton(panel, text="SHOW OPERATION USAGE GRAPH", height=34, font=(UI, 11, "bold"),
                      fg_color=PURPLE, hover_color="#7E22CE",
                      command=self.show_usage_graph).pack(fill="x", padx=8, pady=(10, 0))

        self.animate_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(panel, text="Animate circuit signals", variable=self.animate_var,
                      font=(UI, 12)).pack(anchor="w", padx=10, pady=(10, 0))

        speed_row = ctk.CTkFrame(panel, fg_color="transparent")
        speed_row.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(speed_row, text="Speed", font=(UI, 11), text_color=MUTED).pack(side="left")
        self.speed_var = ctk.DoubleVar(value=1.0)
        ctk.CTkSlider(speed_row, from_=0.5, to=3.0, variable=self.speed_var,
                      height=14).pack(side="left", fill="x", expand=True, padx=(10, 0))

        self.usage_label = ctk.CTkLabel(panel, text="Total executions: 0", font=(UI, 12, "bold"),
                                        text_color=MUTED)
        self.usage_label.pack(anchor="w", padx=10, pady=(8, 0))

        ctk.CTkLabel(panel, text="INSTRUCTION HISTORY  (click to reload)", font=(UI, 11, "bold"),
                     text_color=MUTED).pack(anchor="w", padx=10, pady=(10, 4))
        self.history_frame = ctk.CTkScrollableFrame(panel, fg_color=CARD, corner_radius=10, height=170)
        self.history_frame.pack(fill="x", padx=5, pady=(0, 10))
        self.render_history()

    def create_operand(self, parent, label_text):
        label = ctk.CTkLabel(parent, text=label_text, font=(UI, 12, "bold"), text_color=MUTED)
        label.pack(anchor="w", padx=10, pady=(8, 0))
        entry = ctk.CTkEntry(parent, height=38, font=(MONO, 14), fg_color=CARD, border_color=BORDER)
        entry.pack(fill="x", padx=8, pady=(3, 0))
        entry.bind("<KeyRelease>", self.on_key, add="+")
        return label, entry

    def build_output_panel(self, parent):
        panel = ctk.CTkFrame(parent, corner_radius=16, fg_color=PANEL)
        panel.grid(row=1, column=1, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        hero = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        hero.grid(row=0, column=0, padx=8, pady=(8, 6), sticky="ew")
        hero.grid_columnconfigure((0, 1, 2), weight=1, uniform="hero")

        self.hex_value, _ = self.stat(hero, "RESULT (HEX)", 0, 0, 34, GREEN)
        self.value_result, self.value_title = self.stat(hero, "RESULT VALUE", 0, 1, 30, TEXT, colspan=2)
        self.op_value, _ = self.stat(hero, "OPERATION", 1, 0, 18, TEXT, copy=False)
        self.class_result, self.class_title = self.stat(hero, "SIGNED VALUE", 1, 1, 18, TEXT)
        self.extra_value, self.extra_title = self.stat(hero, "EXTRA", 1, 2, 15, AMBER)
        self.bin_value, _ = self.stat(hero, "RESULT (BINARY)", 2, 0, 12, MUTED, colspan=3)

        self.flags_area = ctk.CTkFrame(scroll, fg_color="transparent")
        self.flags_area.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="ew")
        self.flag_ui = {}
        self.build_flags()

        ctk.CTkLabel(scroll, text="HARDWARE CIRCUIT VIEW  (live - hover and click items)",
                     font=(UI, 12, "bold"), text_color=MUTED).grid(row=2, column=0, padx=8, pady=(4, 2), sticky="w")
        self.circuit = CircuitView(scroll, self)
        self.circuit.grid(row=3, column=0, padx=8, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(scroll, text="BIT-LEVEL VIEW  (click a bit in A or B to toggle it)",
                     font=(UI, 12, "bold"), text_color=MUTED).grid(row=4, column=0, padx=8, pady=(4, 2), sticky="w")
        bits = ctk.CTkFrame(scroll, fg_color="transparent")
        bits.grid(row=5, column=0, padx=8, pady=(0, 8), sticky="ew")
        bits.grid_columnconfigure(1, weight=1)

        self.a_strip = BitStrip(bits, BLUE, lambda b: self.toggle_bit("A", b), self.set_status)
        self.b_strip = BitStrip(bits, BLUE, lambda b: self.toggle_bit("B", b), self.set_status)
        self.r_strip = BitStrip(bits, GREEN, None, self.set_status)
        for row, (name, strip) in enumerate((("A", self.a_strip), ("B", self.b_strip), ("RES", self.r_strip))):
            ctk.CTkLabel(bits, text=name, font=(UI, 12, "bold"), text_color=MUTED,
                         width=38).grid(row=row, column=0, pady=(3, 0))
            strip.grid(row=row, column=1, sticky="ew", pady=(3, 0))

        ctk.CTkLabel(scroll, text="WORKING  (step-by-step explanation of this instruction)",
                     font=(UI, 12, "bold"), text_color=MUTED).grid(row=6, column=0, padx=8, pady=(4, 2), sticky="w")
        self.working_box = ctk.CTkTextbox(scroll, height=250, font=(MONO, 11), fg_color=SCOPE,
                                          text_color=TEXT, border_width=1, border_color=BORDER, wrap="none")
        self.working_box.grid(row=7, column=0, padx=8, pady=(0, 12), sticky="ew")
        self.working_box.configure(state="disabled")

    def stat(self, parent, title, row, col, size, color, colspan=1, copy=True):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=col, columnspan=colspan, sticky="ew", padx=14, pady=(10, 8))
        title_label = ctk.CTkLabel(frame, text=title, font=(UI, 10, "bold"), text_color=MUTED)
        title_label.pack(anchor="w")
        value = ctk.CTkLabel(frame, text="-", font=(MONO, size, "bold"), text_color=color,
                             wraplength=900 if colspan == 3 else 560, justify="left")
        value.pack(anchor="w")
        if copy:
            for widget in (frame, title_label, value):
                widget.bind("<Button-1>", lambda e, lab=value: self.copy_text(lab.cget("text")))
            value.configure(cursor="hand2")
        return value, title_label

    def build_flags(self):
        for widget in self.flags_area.winfo_children():
            widget.destroy()
        self.flag_ui = {}
        defs = ALU_FLAGS if self.mode == "ALU" else FPU_FLAGS
        per_row = len(defs) if len(defs) <= 4 else 3

        for index, (key, name, color, tip) in enumerate(defs):
            r, c = divmod(index, per_row)
            self.flags_area.grid_columnconfigure(c, weight=1, uniform="flag")
            frame = ctk.CTkFrame(self.flags_area, fg_color=CARD, corner_radius=10,
                                 border_width=1, border_color=BORDER)
            frame.grid(row=r, column=c, padx=3, pady=2, sticky="ew")
            led = ctk.CTkLabel(frame, text="●", font=(UI, 20), text_color=OFF)
            led.pack(side="left", padx=(12, 6), pady=4)
            ctk.CTkLabel(frame, text=name, font=(UI, 12, "bold")).pack(side="left")
            value = ctk.CTkLabel(frame, text="0", font=(MONO, 16, "bold"), text_color=MUTED)
            value.pack(side="right", padx=12)
            for widget in (frame, led, value):
                widget.bind("<Enter>", lambda e, m=tip: self.set_status(m, MUTED), add="+")
            self.flag_ui[key] = (led, value, color)

    # ---- modes, sizes and operations --------------------------------------

    def set_mode(self, mode):
        self.cancel_animation()
        self.mode = mode
        alu = mode == "ALU"

        self.alu_mode_button.configure(fg_color=BLUE if alu else CARD, text_color="white" if alu else MUTED)
        self.fpu_mode_button.configure(fg_color=PURPLE if not alu else CARD, text_color="white" if not alu else MUTED)

        self.operation = "ADD" if alu else "FADD"
        self.value_title.configure(text="RESULT VALUE (UNSIGNED)" if alu else "RESULT VALUE (FLOAT)")
        self.class_title.configure(text="SIGNED VALUE" if alu else "CLASS")
        self.previous_operation = None

        self.width_seg.pack_forget()
        self.fmt_seg.pack_forget()
        if alu:
            self.size_label.configure(text="Word size (bits)")
            self.width_seg.pack(fill="x")
        else:
            self.size_label.configure(text="Float format")
            self.fmt_seg.pack(fill="x")

        self.build_operation_buttons()
        self.build_flags()
        self.apply_size(redraw=False)
        self.set_operation(self.operation)
        self.clear()

    def on_width(self, value):
        self.nbits = int(value)
        self.apply_size()

    def on_format(self, value):
        self.fmt_key = value
        self.apply_size()

    def apply_size(self, redraw=True):
        """Propagate the current word size / float format to every widget."""
        self.cancel_animation()
        alu = self.mode == "ALU"
        n = self.total_bits
        fmt = None if alu else self.fmt
        for strip in (self.a_strip, self.b_strip, self.r_strip):
            strip.set_layout(n, fmt)

        if alu:
            n_ = self.nbits
            self.range_label.configure(
                text=f"{n_}-bit  |  unsigned 0..{mask_of(n_)}  |  signed {-(1 << (n_ - 1))}..{(1 << (n_ - 1)) - 1}")
            self.a_label.configure(text="Operand A")
            self.b_label.configure(text=f"Shift amount (B mod {n_})" if self.operation in SHIFTS else "Operand B")
            ph = "decimal | -5 | 0xHEX | 0bBIN | 0oOCT"
        else:
            E, M, desc = FP_FORMATS[self.fmt_key]
            self.range_label.configure(text=f"{desc}  |  bias {(1 << (E - 1)) - 1}  |  {n} bits total")
            self.a_label.configure(text=f"Float A  ({self.fmt_key})")
            self.b_label.configure(text=f"Float B  ({self.fmt_key})")
            ph = "3.14 | 1e-5 | inf | nan | 0xBITS"
        self.a_entry.configure(placeholder_text=ph)
        self.b_entry.configure(placeholder_text=ph)

        self.circuit.set_scene(self.mode, self.operation, self.nbits, self.fmt if not alu else None)
        self.update_examples()
        if redraw:
            self.refresh_preview()

    def build_operation_buttons(self):
        for widget in self.operation_grid.winfo_children():
            widget.destroy()
        self.op_buttons = {}
        ops = ALU_OPS if self.mode == "ALU" else FPU_OPS
        for index, op in enumerate(ops):
            self.operation_grid.grid_columnconfigure(index % 4, weight=1)
            button = ctk.CTkButton(self.operation_grid, text=op, height=28, font=(UI, 11, "bold"),
                                   corner_radius=7, border_width=1, border_color=BORDER, hover_color=BORDER,
                                   command=lambda selected=op: self.set_operation(selected))
            button.grid(row=index // 4, column=index % 4, padx=2, pady=2, sticky="ew")
            self.op_buttons[op] = button

    def set_operation(self, op):
        self.operation = op
        ops = ALU_OPS if self.mode == "ALU" else FPU_OPS
        for name, button in self.op_buttons.items():
            selected = name == op
            button.configure(fg_color=ops[name] if selected else CARD,
                             text_color="white" if selected else MUTED)

        if self.mode == "ALU":
            self.b_label.configure(text=f"Shift / rotate amount (B mod {self.nbits})"
                                   if op in SHIFTS else "Operand B")

        if op in UNARY:
            self.b_entry.configure(state="normal")
            self.set_entry(self.b_entry, "0")
            self.b_entry.configure(state="disabled")
        else:
            self.b_entry.configure(state="normal")
            if self.previous_operation in UNARY:
                self.set_entry(self.b_entry, "")

        self.previous_operation = op
        self.circuit.set_scene(self.mode, op, self.nbits, self.fmt if self.mode == "FPU" else None)
        self.refresh_preview()

    # ---- examples -------------------------------------------------------------

    def examples(self):
        if self.mode == "ALU":
            n = self.nbits
            m, smax = mask_of(n), (1 << (n - 1)) - 1
            smin = 1 << (n - 1)
            return [
                ("Signed overflow: MAX + 1", "ADD", hex(smax), "1"),
                ("Carry out: all ones + 1", "ADD", hex(m), "1"),
                ("Borrow: 0 - 1", "SUB", "0", "1"),
                ("Two's complement: NEG 1", "NEG", "1", "0"),
                ("Compare 5 vs -1 (signed/unsigned)", "CMP", "5", "-1"),
                ("Logical vs arithmetic: SHR MIN", "SHR", hex(smin), "1"),
                ("Arithmetic: SAR MIN", "SAR", hex(smin), "1"),
                ("Rotate left", "ROL", hex(smin | 1), "1"),
                ("Multiply overflow", "MUL", hex(m), "2"),
                ("Divide with remainder", "DIV", "13" if n == 4 else "100", "7"),
                ("De Morgan: NAND", "NAND", "0b1100" , "0b1010"),
            ]
        E, M = self.fmt
        mx = fp_exact(((((1 << E) - 2) << M) | ((1 << M) - 1)), E, M)
        return [
            ("0.1 + 0.2 (rounding error)", "FADD", "0.1", "0.2"),
            ("1 / 3 (inexact)", "FDIV", "1", "3"),
            (f"Absorption: 2^{M + 1} + 1", "FADD", str(2 ** (M + 1)), "1"),
            ("Overflow: MAX x 2", "FMUL", f"{float(mx):.17g}", "2"),
            ("Divide by zero: 1 / 0", "FDIV", "1", "0"),
            ("Invalid: 0 / 0", "FDIV", "0", "0"),
            ("Invalid: inf - inf", "FSUB", "inf", "inf"),
            ("Smallest subnormal x 0.5", "FMUL", "0x1", "0.5"),
            ("Compare -0.0 and +0.0", "FCMP", "-0.0", "0.0"),
            ("Negate 2.5", "FNEG", "2.5", "0"),
        ]

    def update_examples(self):
        names = [e[0] for e in self.examples()]
        self.example_menu.configure(values=names)
        self.example_menu.set("Examples...")

    def load_example(self, name):
        self.example_menu.set("Examples...")
        for label, op, a, b in self.examples():
            if label == name:
                self.set_operation(op)
                self.set_entry(self.a_entry, a)
                if op not in UNARY:
                    self.set_entry(self.b_entry, b)
                self.calculate()
                return

    # ---- parsing ---------------------------------------------------------------

    def parse_int(self, text, name, n):
        text = text.strip().replace("_", "")
        if not text:
            raise ValueError(f"{name} is required.")
        try:
            value = int(text, 0)
        except ValueError:
            try:
                value = int(text, 10)
            except ValueError:
                raise ValueError(f"{name} is invalid (use decimal, 0xHEX, 0bBIN or 0oOCT).")
        if not -(1 << (n - 1)) <= value <= mask_of(n):
            raise ValueError(f"{name} must fit in {n} bits ({-(1 << (n - 1))} .. {mask_of(n)}).")
        return value & mask_of(n)

    def parse_value(self, entry, name):
        if self.mode == "ALU":
            return self.parse_int(entry.get(), name, self.nbits)
        E, M = self.fmt
        try:
            return fp_parse(entry.get(), E, M)
        except ValueError as err:
            raise ValueError(f"{name}: {err}")

    # ---- live input handling ----------------------------------------------------

    def on_key(self, event):
        if self.snapshot() != self._last_snap:
            self.refresh_preview()

    def update_strips(self):
        for entry, strip in ((self.a_entry, self.a_strip), (self.b_entry, self.b_strip)):
            text = entry.get().strip()
            value, invalid = None, False
            if text:
                try:
                    value = self.parse_value(entry, "Value")
                except ValueError:
                    invalid = True
            entry.configure(border_color=RED if invalid else BORDER)
            strip.set(value)

    def toggle_bit(self, which, bit):
        entry = self.a_entry if which == "A" else self.b_entry
        if entry.cget("state") == "disabled":
            return
        text = entry.get().strip().lower()
        try:
            value = self.parse_value(entry, "Value") if text else 0
        except ValueError:
            value = 0
        value ^= 1 << bit
        n = self.total_bits
        if self.mode == "FPU":
            output = hexw(value, n)
        elif text.startswith("0x"):
            output = f"0x{value:X}"
        elif text.startswith("0b"):
            output = f"0b{value:b}"
        elif text.startswith("0o"):
            output = f"0o{value:o}"
        else:
            output = str(value)
        self.set_entry(entry, output)
        self.refresh_preview()

    def swap_operands(self):
        if self.b_entry.cget("state") == "disabled":
            self.set_status("This operation does not use operand B.", AMBER)
            return
        a, b = self.a_entry.get(), self.b_entry.get()
        self.set_entry(self.a_entry, b)
        self.set_entry(self.b_entry, a)
        self.refresh_preview()

    def result_to_a(self):
        if not self.trace:
            self.set_status("No valid result yet.", AMBER)
            return
        self.set_entry(self.a_entry, hexw(self.trace["result"], self.total_bits))
        self.refresh_preview()
        self.set_status("Result copied into operand A - pick the next operation to chain.", GREEN)

    # ---- computation ----------------------------------------------------------------

    def compute(self):
        op = self.operation
        if self.mode == "ALU":
            n = self.nbits
            a = self.parse_value(self.a_entry, "Operand A")
            if op in UNARY:
                b = 0
            else:
                b = self.parse_value(self.b_entry, "Shift amount" if op in SHIFTS else "Operand B")
            return alu_trace(op, a, b, n)
        E, M = self.fmt
        a = self.parse_value(self.a_entry, "Float A")
        b = 0 if op in UNARY else self.parse_value(self.b_entry, "Float B")
        return fp_trace(op, a, b, E, M)

    # ---- output panels --------------------------------------------------------------

    def set_working(self, text):
        self.working_box.configure(state="normal")
        self.working_box.delete("1.0", "end")
        self.working_box.insert("1.0", text)
        self.working_box.configure(state="disabled")

    def show_result(self, tr):
        result, n = tr["result"], tr["n"]
        colors = ALU_OPS if tr["mode"] == "ALU" else FPU_OPS
        self.op_value.configure(text=tr["op"], text_color=colors[tr["op"]])
        self.fit(self.hex_value, hexw(result, n), 34)
        if tr["mode"] == "ALU":
            self.fit(self.value_result, str(result), 30)
            self.fit(self.class_result, str(to_signed(result, n)), 18)
            bits_text = group_bin(result, n)
        else:
            E, M = tr["E"], tr["M"]
            self.fit(self.value_result, tr["rstr"], 30)
            self.class_result.configure(text=fp_class(result, E, M))
            s, e, m = fp_split(result, E, M)
            bits_text = f"{s} | {e:0{E}b} | {m:0{M}b}"
        self.bin_value.configure(text=bits_text)
        if tr.get("extra"):
            self.extra_title.configure(text=tr["extra"][0])
            self.fit(self.extra_value, tr["extra"][1], 15, 10)
        else:
            self.extra_title.configure(text="EXTRA")
            self.extra_value.configure(text="-")
        self.r_strip.set(result)
        self.set_working(tr["working"])

    def show_flags(self, tr):
        for key, (led, label, color) in self.flag_ui.items():
            active = int(tr["flags"].get(key, 0))
            led.configure(text_color=color if active else OFF)
            label.configure(text=str(active), text_color=color if active else MUTED)

    def reset_outputs(self):
        for label in (self.op_value, self.hex_value, self.value_result, self.class_result,
                      self.extra_value, self.bin_value):
            label.configure(text="-")
        self.extra_title.configure(text="EXTRA")
        self.op_value.configure(text_color=TEXT)
        for led, value, color in self.flag_ui.values():
            led.configure(text_color=OFF)
            value.configure(text="0", text_color=MUTED)
        self.r_strip.set(None)

    def refresh_preview(self):
        """Compute and show the result without animation or logging."""
        self.cancel_animation()
        self.update_strips()
        self._last_snap = self.snapshot()
        try:
            tr = self.compute()
        except ValueError as error:
            self.no_trace()
            has_text = self.a_entry.get().strip() or (
                self.b_entry.cget("state") == "normal" and self.b_entry.get().strip())
            if has_text:
                self.set_status(str(error), AMBER)
            else:
                self.set_status("Ready - enter operands (decimal, 0xHEX, 0bBIN)" if self.mode == "ALU"
                                else "Ready - enter floats (3.14, 1e-5, inf, nan or 0xBITS)", MUTED)
            return None
        except Exception as error:
            self.no_trace()
            self.set_status(f"Execution error: {error}", RED)
            return None

        self.trace = tr
        self.circuit.set_trace(tr)
        self.circuit.set_animation(None, 0.0)
        self.show_result(tr)
        self.show_flags(tr)
        self.circuit.draw()
        self.set_status(f"Live preview | {tr['op']} = {hexw(tr['result'], tr['n'])}   "
                        "(press Execute to animate and log)", MUTED)
        return tr

    def no_trace(self):
        self.trace = None
        self.circuit.set_trace(None)
        self.circuit.draw()
        self.reset_outputs()
        self.set_working("")

    # ---- execution + animation --------------------------------------------------------

    def calculate(self, animate=True):
        self.cancel_animation()
        self.update_strips()
        try:
            tr = self.compute()
        except ValueError as error:
            self.set_status(str(error), RED)
            return
        except Exception as error:
            self.set_status(f"Execution error: {error}", RED)
            return

        self._last_snap = self.snapshot()
        self.trace = tr
        self.circuit.set_trace(tr)

        flags = " ".join(f"{name[0]}{int(tr['flags'].get(key, 0))}" for key, name, *_ in tr["flag_defs"])
        self.add_history({"mode": self.mode, "size": self.size_tag(), "op": tr["op"],
                          "a": self.a_entry.get().strip(), "b": self.b_entry.get().strip(),
                          "result": tr["result"], "hexr": hexw(tr["result"], tr["n"]), "flags": flags})
        self.usage_counts[tr["op"]] += 1
        self.update_usage_label()
        if self.graph_win is not None and self.graph_win.winfo_exists():
            self.draw_graph()

        if animate and self.animate_var.get():
            self.start_animation(tr)
        else:
            self.circuit.set_animation(None, 0.0)
            self.show_result(tr)
            self.show_flags(tr)
            self.circuit.draw()
            self.report_done(tr)

    def report_done(self, tr):
        if tr.get("verified") is False or tr.get("legacy") is False:
            self.set_status(f"WARNING: {tr['op']} result differs from the reference model", AMBER)
            return
        note = ""
        if tr.get("verified") is True:
            note = "  |  verified against reference model"
            if tr.get("legacy") is True:
                note += " and alu_core"
        self.set_status(f"Instruction completed | {tr['op']} = {hexw(tr['result'], tr['n'])}{note}", GREEN)

    def start_animation(self, tr):
        self.plan = stage_plan(tr["mode"], tr["op"], tr["n"])
        self.anim_stage = 0
        self.anim_t = 0.0
        self.reset_outputs()
        self.circuit.set_animation(0, 0.0)
        self.circuit.draw()
        self.set_status(self.plan[0][0], YELLOW)
        self.job = self.after(self.TICK, self.tick)

    def tick(self):
        self.job = None
        if self.anim_stage is None or self.plan is None:
            return
        msgs, result_stage, flag_stage, durations = self.plan

        speed = max(self.speed_var.get(), 0.25)
        self.anim_t += self.TICK * speed / durations[self.anim_stage]

        if self.anim_t >= 1.0:
            self.anim_stage += 1
            self.anim_t = 0.0
            if self.anim_stage >= len(msgs):
                self.finish_animation()
                return
            self.set_status(msgs[self.anim_stage], YELLOW)
            if self.anim_stage == result_stage:
                self.show_result(self.trace)
            if self.anim_stage == flag_stage:
                self.show_flags(self.trace)

        self.circuit.set_animation(self.anim_stage, self.anim_t)
        self.circuit.draw()
        self.job = self.after(self.TICK, self.tick)

    def finish_animation(self):
        self.anim_stage = None
        self.plan = None
        self.circuit.set_animation(None, 0.0)
        if self.trace:
            self.show_result(self.trace)
            self.show_flags(self.trace)
            self.report_done(self.trace)
        self.circuit.draw()

    def cancel_animation(self):
        if self.job is not None:
            self.after_cancel(self.job)
            self.job = None
        self.anim_stage = None
        self.plan = None
        if self.circuit is not None:
            self.circuit.set_animation(None, 0.0)

    # ---- usage graph -----------------------------------------------------------------

    def update_usage_label(self):
        total = sum(self.usage_counts.values())
        most = max(self.usage_counts, key=self.usage_counts.get) if total else "None"
        self.usage_label.configure(text=f"Total executions: {total} | Most used: {most}")

    def show_usage_graph(self):
        if not any(self.usage_counts.values()):
            self.set_status("No operations executed yet. Press Execute first.", AMBER)
            return
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except ImportError:
            self.set_status("matplotlib is not installed:  pip install matplotlib", RED)
            return

        if self.graph_win is None or not self.graph_win.winfo_exists():
            win = ctk.CTkToplevel(self)
            win.title("COA Operation Usage")
            win.geometry("1100x560")
            win.configure(fg_color=BG)
            self.graph_fig = Figure(figsize=(10.8, 5.4), dpi=100, facecolor=BG)
            self.graph_ax = self.graph_fig.add_subplot(111)
            self.graph_canvas = FigureCanvasTkAgg(self.graph_fig, master=win)
            self.graph_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
            self.graph_win = win

        self.draw_graph()
        self.graph_win.lift()
        self.graph_win.focus()

    def draw_graph(self):
        ax = self.graph_ax
        ax.clear()
        ax.set_facecolor(PANEL)
        ops = list(self.usage_counts)
        counts = [self.usage_counts[o] for o in ops]
        colors = [ALU_OPS.get(o) or FPU_OPS.get(o) for o in ops]
        bars = ax.bar(ops, counts, color=colors, edgecolor=BORDER)
        top = max(counts) if counts else 1
        for bar, count in zip(bars, counts):
            if count:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + top * 0.015, str(count),
                        ha="center", va="bottom", fontsize=9, fontweight="bold", color=TEXT)
        ax.set_title(f"Operation Usage Count  (total {sum(counts)})", color=TEXT, fontsize=15, fontweight="bold")
        ax.set_xlabel("Operation", color=MUTED)
        ax.set_ylabel("Number of executions", color=MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.tick_params(axis="x", labelrotation=60)
        ax.set_ylim(0, top * 1.15 + 0.5)
        ax.grid(axis="y", alpha=0.25, color=MUTED)
        for spine in ax.spines.values():
            spine.set_color(BORDER)
        self.graph_fig.tight_layout()
        self.graph_canvas.draw()

    # ---- history, export, utilities ------------------------------------------------------

    def add_history(self, entry):
        self.history.insert(0, entry)
        del self.history[60:]
        self.render_history()

    def render_history(self):
        for widget in self.history_frame.winfo_children():
            widget.destroy()
        if not self.history:
            ctk.CTkLabel(self.history_frame, text="No instructions executed",
                         text_color=MUTED, font=(UI, 11)).pack(pady=8)
            return
        for entry in self.history:
            op = entry["op"]
            args = entry["a"] if op in UNARY else f"{entry['a']}, {entry['b']}"
            colors = ALU_OPS if entry["mode"] == "ALU" else FPU_OPS
            ctk.CTkButton(self.history_frame, text=f"[{entry['size']}] {op} {args} -> {entry['hexr']}",
                          anchor="w", height=26, font=(MONO, 10), fg_color="transparent",
                          hover_color=BORDER, text_color=colors[op],
                          command=lambda e=entry: self.load_history(e)).pack(fill="x", pady=1)

    def load_history(self, entry):
        mode = entry["mode"]
        if mode != self.mode:
            self.set_mode(mode)
        if mode == "ALU":
            self.nbits = int(entry["size"][3:])
            self.width_seg.set(str(self.nbits))
        else:
            self.fmt_key = entry["size"]
            self.fmt_seg.set(self.fmt_key)
        self.apply_size(redraw=False)
        self.set_operation(entry["op"])
        self.set_entry(self.a_entry, entry["a"])
        if entry["op"] not in UNARY:
            self.set_entry(self.b_entry, entry["b"])
        self.calculate()

    def export_history(self):
        if not self.history:
            self.set_status("Nothing to export yet.", AMBER)
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV file", "*.csv")],
                                            initialfile="coa_instruction_log.csv")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["unit", "size", "operation", "operand_a", "operand_b", "result_hex", "flags"])
                for e in reversed(self.history):
                    writer.writerow([e["mode"], e["size"], e["op"], e["a"], e["b"], e["hexr"], e["flags"]])
            self.set_status(f"Exported {len(self.history)} instructions to {path}", GREEN)
        except OSError as error:
            self.set_status(f"Export failed: {error}", RED)

    def randomize(self):
        op = self.operation
        if self.mode == "ALU":
            n = self.nbits
            a = random.getrandbits(n)
            if op in SHIFTS:
                b = random.randint(0, n - 1)
            elif op in ("DIV", "MOD"):
                b = random.randint(1, mask_of(n))
            else:
                b = random.getrandbits(n)
            self.set_entry(self.a_entry, str(a))
            if op not in UNARY:
                self.set_entry(self.b_entry, str(b))
        else:
            E, M = self.fmt
            n = 1 + E + M
            lim = {8: 100.0, 16: 1000.0}.get(n, 1000.0)
            a = random.uniform(-lim, lim)
            b = random.uniform(-lim, lim)
            if op == "FDIV" and abs(b) < 0.1:
                b = 1.0
            self.set_entry(self.a_entry, f"{a:.5g}")
            if op not in UNARY:
                self.set_entry(self.b_entry, f"{b:.5g}")
        self.calculate()

    def clear(self):
        self.cancel_animation()
        self.set_entry(self.a_entry, "")
        if self.operation not in UNARY:
            self.set_entry(self.b_entry, "")
        self.reset_outputs()
        self.refresh_preview()
        self.set_working("")
        self.set_status("Cleared", MUTED)

    def on_close(self):
        self.cancel_animation()
        if self.graph_win is not None and self.graph_win.winfo_exists():
            self.graph_win.destroy()
        self.destroy()


if __name__ == "__main__":
    app = ALUApp()
    app.mainloop()