# FPU core logic

import math
import struct

MASK = 0xFFFFFFFF
FLOAT32_MAX = 3.4028234663852886e38


def float_to_bits(value):
    """Convert a Python float to IEEE-754 single-precision raw bits."""
    try:
        return struct.unpack(">I", struct.pack(">f", float(value)))[0]
    except OverflowError:
        return 0xFF800000 if value < 0 else 0x7F800000


def bits_to_float(bits):
    """Convert IEEE-754 single-precision raw bits to a Python float."""
    return struct.unpack(">f", struct.pack(">I", bits & MASK))[0]


def classify(bits):
    bits &= MASK
    exponent = (bits >> 23) & 0xFF
    fraction = bits & 0x7FFFFF

    if exponent == 0xFF:
        return "NaN" if fraction else "Infinity"

    if exponent == 0:
        return "Zero" if fraction == 0 else "Subnormal"

    return "Normal"


def fields(bits):
    bits &= MASK

    return {
        "sign": (bits >> 31) & 1,
        "exponent_raw": (bits >> 23) & 0xFF,
        "fraction": bits & 0x7FFFFF,
        "class": classify(bits),
    }


def execute(op, a, b=0.0):
    """
    Supported operations:
    FADD, FSUB, FMUL, FDIV, FNEG, FABS, FCMP

    Returns:
    result_bits, flags, result_float
    """
    op = op.upper()
    a = float(a)
    b = float(b)

    invalid = False
    divide_by_zero = False
    overflow = False
    underflow = False

    if op == "FADD":
        raw_result = a + b

    elif op == "FSUB":
        raw_result = a - b

    elif op == "FMUL":
        raw_result = a * b

    elif op == "FDIV":
        if math.isnan(a) or math.isnan(b):
            raw_result = float("nan")
            invalid = True

        elif b == 0.0:
            if a == 0.0:
                raw_result = float("nan")
                invalid = True
            else:
                raw_result = math.copysign(float("inf"), a)
                divide_by_zero = True

        else:
            raw_result = a / b

    elif op == "FNEG":
        raw_result = -a

    elif op == "FABS":
        raw_result = abs(a)

    elif op == "FCMP":
        if math.isnan(a) or math.isnan(b):
            raw_result = float("nan")
            invalid = True
        elif a < b:
            raw_result = -1.0
        elif a > b:
            raw_result = 1.0
        else:
            raw_result = 0.0

    else:
        raise ValueError(f"Unsupported FPU operation: {op}")

    if math.isfinite(raw_result) and abs(raw_result) > FLOAT32_MAX:
        overflow = True
        result_bits = 0xFF800000 if raw_result < 0 else 0x7F800000
        result_float = bits_to_float(result_bits)
    else:
        result_bits = float_to_bits(raw_result)
        result_float = bits_to_float(result_bits)

    result_class = classify(result_bits)

    if (
        math.isfinite(raw_result)
        and raw_result != 0.0
        and result_class in ("Zero", "Subnormal")
    ):
        underflow = True

    inexact = (
        math.isfinite(raw_result)
        and math.isfinite(result_float)
        and raw_result != result_float
    )

    info = fields(result_bits)

    flags = {
        "zero": int(info["class"] == "Zero"),
        "sign": int(info["sign"]),
        "invalid": int(invalid),
        "divide_by_zero": int(divide_by_zero),
        "overflow": int(overflow),
        "underflow": int(underflow),
        "inexact": int(inexact),
    }

    return result_bits, flags, result_float