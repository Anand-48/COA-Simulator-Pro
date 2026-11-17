from docx import Document
from docx.shared import Pt, RGBColor

doc = Document()

# Set default font
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(11)

# Title & Metadata
title = doc.add_heading("Project Report: COA Simulator Pro", level=0)
meta = doc.add_paragraph()
meta.add_run("Course: ").bold = True
meta.add_run("Master of Computer Applications (MCA) — Computer Organization & Architecture\n")
meta.add_run("Repository: ").bold = True
meta.add_run("https://github.com/Anand-48/Mca-COA-mini-projects-\n")
meta.add_run("Submitted By:\n").bold = True
meta.add_run("  • Achyutanand Dixit — Lead Developer\n")
meta.add_run("  • Payal Gupta — Testing & Documentation")

# Section 1
doc.add_heading("1. Abstract", level=1)
doc.add_paragraph(
    "COA Simulator Pro is an interactive desktop application built in Python (CustomTkinter) "
    "that visualizes the internal execution of digital arithmetic and logic operations inside a "
    "Central Processing Unit (CPU). Unlike standard calculators that display only final outputs, "
    "the simulator exposes bit-level data flow, gate-level hardware architecture, carry propagation, "
    "barrel shifting stages, IEEE-754 floating-point encoding/rounding, and processor status flags in real time."
)

# Section 2
doc.add_heading("2. Problem Statement & Motivation", level=1)
doc.add_paragraph(
    "In Computer Organization & Architecture (COA) coursework, students frequently struggle to connect "
    "theoretical concepts—such as two's complement overflow, restoring division, barrel shifters, and "
    "IEEE-754 round-to-nearest-even behavior—with actual hardware execution. Static textbook diagrams "
    "fail to demonstrate how changing a single bit alters carry chains or precision errors (such as why "
    "0.1 + 0.2 ≠ 0.3 in binary floating-point). COA Simulator Pro bridges this gap by pairing "
    "cycle-by-cycle hardware animations with textbook-style step-by-step derivations."
)

# Section 3 (with real Word Table)
doc.add_heading("3. System Architecture", level=1)
doc.add_paragraph("The application follows a modular, decoupled architecture separated into four primary layers:")

table = doc.add_table(rows=1, cols=3)
table.style = "Table Grid"
hdr_cells = table.rows[0].cells
hdr_cells[0].text = "Module"
hdr_cells[1].text = "File"
hdr_cells[2].text = "Responsibility"
for cell in hdr_cells:
    cell.paragraphs[0].runs[0].bold = True

rows_data = [
    ("Application Launcher & Analytics", "splash.py", "Displays the animated startup screen, manages session analytics (Dashboard, Radar/Rose charts, Heatmaps, Timeline), and initializes the main GUI."),
    ("Core Simulation & UI Engine", "main.py", "Houses the Control Unit switcher, Integer ALU engine, Floating-Point FPU engine, interactive bit strips, live circuit canvas, and step-by-step working panel."),
    ("Standalone Reference ALU", "alu_core.py", "Independent 32-bit ALU module used for automated cross-verification of integer instructions."),
    ("Data & Logging Layer", "data/", "Stores persistent execution history and supports CSV export for lab reporting."),
]
for mod, fname, resp in rows_data:
    row_cells = table.add_row().cells
    row_cells[0].text = mod
    row_cells[1].text = fname
    row_cells[2].text = resp

# Section 4
doc.add_heading("4. Hardware & Algorithmic Implementation", level=1)

doc.add_heading("4.1 Integer Arithmetic Logic Unit (ALU)", level=2)
doc.add_paragraph("The Integer ALU supports selectable word widths of 4, 8, 16, 32, and 64 bits, enforcing strict fixed-width wrap-around semantics:")
alu_bullets = [
    ("Adder / Subtractor (ADD, SUB, INC, DEC, NEG, CMP): ", "Implemented via a bit-by-bit ripple-carry adder trace. Subtraction computes A + NOT(B) + 1 using two's complement arithmetic. Signed overflow is detected via V = Cin ⊕ Cout at the Most Significant Bit (MSB)."),
    ("Logic Unit (AND, OR, XOR, NOT, NAND, NOR, XNOR): ", "Models parallel bitwise gate arrays across all n bits."),
    ("Barrel Shifter (SHL, SHR, SAR, ROL, ROR): ", "Decomposes the shift amount into log₂(n) multiplexer stages (1, 2, 4, 8… bit shifts) and records intermediate register states after each stage."),
    ("Multiplier & Divider (MUL, DIV, MOD): ", "Uses shift-and-add accumulation to produce a full 2n-bit product (retaining the lower n bits and setting CARRY if the upper half is non-zero) and restoring division for quotient/remainder extraction with zero-division trapping."),
]
for lead, body in alu_bullets:
    p = doc.add_paragraph(style="List Bullet")
    p.add_run(lead).bold = True
    p.add_run(body)

doc.add_heading("4.2 IEEE-754 Floating-Point Unit (FPU)", level=2)
doc.add_paragraph("Rather than relying on host-machine floating-point hardware, the FPU implements five formats from scratch—FP8 (1-4-3), FP16 (1-5-10), BF16 (1-8-7), FP32 (1-8-23), and FP64 (1-11-52)—supporting FADD, FSUB, FMUL, FDIV, FNEG, FABS, and FCMP:")
fpu_steps = [
    ("Decoding & Classification: ", "Extracts sign, biased exponent, and significand bits, classifying operands into Normal, Subnormal, Zero, Infinity, or NaN."),
    ("Exact Rational Arithmetic: ", "Computes intermediate results using Python's arbitrary-precision Fraction type to eliminate double-rounding artifacts."),
    ("Single IEEE-754 Rounding: ", "Applies round-to-nearest, ties-to-even once to fit the target bit layout, reporting the exact value, stored binary value, and absolute rounding error."),
    ("Exception Handling: ", "Sets standard status flags (ZERO, SIGN, INVALID, DIV/0, OVERFLOW, INEXACT) for edge cases such as 1/0 = ∞, 0/0 = NaN, and ∞ − ∞ = NaN."),
]
for lead, body in fpu_steps:
    p = doc.add_paragraph(style="List Number")
    p.add_run(lead).bold = True
    p.add_run(body)

# Section 5
doc.add_heading("5. Interactive Features & Verification", level=1)
feat_bullets = [
    ("Gate-Level Circuit Canvas: ", "Renders dynamic circuit schematics for the selected instruction with adjustable signal-flow animation and component inspection on hover/click."),
    ("Interactive Bit Manipulation: ", "Users can input operands in decimal, hexadecimal (0x), or binary (0b), or click individual bits directly (colour-coded by sign, exponent, and mantissa in FPU mode)."),
    ("Dual-Model Self-Checking: ", "Every instruction trace is automatically verified against an independent reference model (and cross-checked against alu_core.py for 32-bit operations) to guarantee 100% computational accuracy."),
]
for lead, body in feat_bullets:
    p = doc.add_paragraph(style="List Bullet")
    p.add_run(lead).bold = True
    p.add_run(body)

# Section 6
doc.add_heading("6. Conclusion & Future Scope", level=1)
doc.add_paragraph(
    "COA Simulator Pro successfully demonstrates the internal micro-operations of integer and floating-point "
    "execution units in an intuitive visual environment. Future enhancements include adding a multi-stage "
    "instruction pipeline simulator (IF, ID, EX, MEM, WB) with hazard detection, cache memory mapping "
    "visualizations, and Booth's signed multiplication algorithm."
)

doc.save("COA_Simulator_Pro_Report.docx")
print("Saved clean COA_Simulator_Pro_Report.docx!")