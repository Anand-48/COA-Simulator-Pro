# alu_core.py

MASK = 0xFFFFFFFF
SIGN_BIT = 0x80000000


def to_signed(value):
    value &= MASK
    return value - (1 << 32) if value & SIGN_BIT else value


def execute(op, a, b=0):
    op = op.upper()
    a_u = a & MASK
    b_u = b & MASK

    carry = 0
    overflow = 0

    if op == "ADD":
        total = a_u + b_u
        result = total & MASK
        carry = int(total > MASK)

        a_s = to_signed(a_u)
        b_s = to_signed(b_u)
        r_s = to_signed(result)

        overflow = int(
            (a_s >= 0 and b_s >= 0 and r_s < 0)
            or (a_s < 0 and b_s < 0 and r_s >= 0)
        )

    elif op == "SUB":
        result = (a_u - b_u) & MASK
        carry = int(a_u >= b_u)

        a_s = to_signed(a_u)
        b_s = to_signed(b_u)
        r_s = to_signed(result)

        overflow = int(
            (a_s >= 0 and b_s < 0 and r_s < 0)
            or (a_s < 0 and b_s >= 0 and r_s >= 0)
        )

    elif op == "AND":
        result = a_u & b_u

    elif op == "OR":
        result = a_u | b_u

    elif op == "XOR":
        result = a_u ^ b_u

    elif op == "NOT":
        result = (~a_u) & MASK

    elif op == "SHL":
        if not 0 <= b <= 31:
            raise ValueError("Shift amount must be between 0 and 31.")

        result = (a_u << b) & MASK
        carry = ((a_u >> (32 - b)) & 1) if b > 0 else 0

        if b > 0:
            overflow = int(((a_u >> 31) & 1) != ((result >> 31) & 1))

    elif op == "SHR":
        if not 0 <= b <= 31:
            raise ValueError("Shift amount must be between 0 and 31.")

        result = a_u >> b
        carry = ((a_u >> (b - 1)) & 1) if b > 0 else 0

    else:
        raise ValueError(f"Unsupported ALU operation: {op}")

    flags = {
        "zero": int(result == 0),
        "carry": int(carry),
        "sign": int((result & SIGN_BIT) != 0),
        "overflow": int(overflow),
    }

    return result, flags