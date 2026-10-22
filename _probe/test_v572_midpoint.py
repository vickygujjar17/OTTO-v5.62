"""
v5.72 static verification probe - DEFAULT ENTRY STYLE IS THE BLOCK MIDPOINT.

v5.72 flips ONE input default, ENTRY_FRONT_EDGE -> ENTRY_MIDPOINT, plus the prose
that described the old geometry. Like v5.71 that is exactly the class of edit that
slips: it compiles identically either way, no formula changes, and nothing in the
tree can notice that the documentation still claims a near-edge pullback.

WHY THE FLIP IS NOT COSMETIC. The two styles are not two flavours of the same
trade -- they are inverse premises about what a zone is for:

  * FRONT_EDGE (v5.64-v5.71) bought a BREAKOUT. The entry sat a full 1.0*ATR
    BEYOND the far edge, so the market still had to run to reach it, and the
    trigger was a STOP-style cross fired from the virtual engine.
  * MIDPOINT (v5.72) buys a PULLBACK to the centre. The entry sits INSIDE the
    zone, i.e. BEHIND the market once price has closed clear of the near edge,
    so it is a genuine resting LIMIT (ROUTE A) that the router can place.

WHAT IS DELIBERATELY UNCHANGED, and why that is the interesting part:

  * CalcSLDistance stays blockHeight + 0.5*ATR. Coupling it to the new entry
    would silently change position size, which is the one number that must be
    independent of entry geometry.
  * The stop is still `entry -/+ slDist`. Because only the anchor moved, risk
    per unit is bit-for-bit what v5.71 risked.
  * The crossing guard keeps its `!= ENTRY_MIDPOINT` scope. Un-scoping it would
    retire EVERY midpoint setup, since a centre-behind-market entry trips the
    cross test on the first healthy tick.
  * The far-edge ProjectedTarget anchor stays. It is the one style-independent
    anchor, so journal rows remain comparable across the switch.

THE NEGATIVE ASSERTIONS ARE THE POINT. Each is invisible to the compiler:

  * the front-edge branch being DELETED instead of merely un-defaulted, which
    would be a silent, irreversible loss of a working style;
  * CalcSLDistance acquiring an entry dependency, which would re-couple sizing
    to geometry;
  * the guard losing its midpoint exemption, which would make the new default
    trade NOTHING while every existing probe still passed;
  * the journal label staying hardcoded to the near-edge formula, so every
    armed record would print a formula the order did not use.

WHAT IT CANNOT PROVE. That ROUTE A actually fills at the broker -- it is
dormant since v5.64 by the code's own admission, and only a Strategy Tester run
exercises order placement and pending-fill resolution. This is static analysis
of the shipped sources; no MT5 required.
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SHIPPED = ["otto.mq5", "COttoOrderManager.mqh", "COttoTradeManager.mqh",
           "COttoRiskManager.mqh", "COttoBlockManager.mqh", "COttoJournal.mqh",
           "CHighTableAuditor.mqh", "COttoMarketStructure.mqh",
           "OttoDefines.mqh"]

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def read(p):
    return io.open(p, encoding="utf-8", errors="replace",
                   newline="").read().replace("\r\n", "\n")


def strip_comments(code):
    """Drop // comments, respecting string literals.

    Load-bearing here for the same reason as in test_v571: the v5.72 rationale
    block in OttoDefines.mqh names ENTRY_FRONT_EDGE (the retired default) and
    spells out the old arithmetic in prose. A raw substring scan would report
    the documentation of the change as a violation of it.
    """
    out = []
    for line in code.split("\n"):
        idx = line.find("//")
        if idx < 0:
            out.append(line)
            continue
        out.append(line if line[:idx].count('"') % 2 else line[:idx])
    return "\n".join(out)


SRC = dict((f, read(os.path.join(ROOT, f))) for f in SHIPPED)
LIVE = dict((f, strip_comments(t)) for f, t in SRC.items())
DEFS_T = SRC["OttoDefines.mqh"]
DEFS_C = LIVE["OttoDefines.mqh"]
BM_RAW = SRC["COttoBlockManager.mqh"]
BM_C = LIVE["COttoBlockManager.mqh"]
OM_RAW = SRC["COttoOrderManager.mqh"]
OM_C = LIVE["COttoOrderManager.mqh"]
JRN_RAW = SRC["COttoJournal.mqh"]

_STAMP = re.search(r'#property\s+version\s+"([0-9.]+)"', DEFS_T)
RELEASE = _STAMP.group(1) if _STAMP else "?"


def body_of(code, header):
    """Extract a function/method body by its signature prefix."""
    i = code.find(header)
    if i < 0:
        return ""
    depth = 0
    started = False
    for j in range(i, len(code)):
        if code[j] == "{":
            depth += 1
            started = True
        elif code[j] == "}":
            depth -= 1
            if started and depth == 0:
                return code[i:j + 1]
    return ""


BEP = body_of(BM_C, "BlockEntryPrice")
CALC = body_of(OM_C, "CalcEntryPrice")
SLD = body_of(OM_C, "CalcSLDistance")


# ----------------------------------------------------------------------
# 1. The default is exactly ENTRY_MIDPOINT, and the old style survives.
# ----------------------------------------------------------------------
print("\n-- 1. InpEntryStyle defaults to ENTRY_MIDPOINT --")

check("InpEntryStyle defaults to ENTRY_MIDPOINT",
      re.search(r"InpEntryStyle\s*=\s*ENTRY_MIDPOINT\s*;", DEFS_C) is not None,
      [l for l in DEFS_C.split("\n") if "InpEntryStyle" in l][:2])
check("InpEntryStyle no longer defaults to ENTRY_FRONT_EDGE",
      re.search(r"InpEntryStyle\s*=\s*ENTRY_FRONT_EDGE\s*;", DEFS_C) is None)
check("InpEntryStyle is still typed ENUM_ENTRY_STYLE",
      re.search(r"input\s+ENUM_ENTRY_STYLE\s+InpEntryStyle", DEFS_C) is not None)

# The front-edge branch must be RETAINED, not deleted. Un-defaulting a style and
# deleting it look identical from the default's point of view, but only one of
# them is reversible.
check("ENTRY_FRONT_EDGE is still declared as a selectable style",
      re.search(r"ENTRY_FRONT_EDGE\s*=\s*1", DEFS_C) is not None)
check("ENTRY_MIDPOINT is declared with value 0 (.set files stay valid)",
      re.search(r"ENTRY_MIDPOINT\s*=\s*0", DEFS_C) is not None)
check("the enum documents midpoint as the v5.72 default",
      "v5.72 DEFAULT" in DEFS_T)


# ----------------------------------------------------------------------
# 2. The midpoint entry is the exact centre -- (top+bottom)/2.0
# ----------------------------------------------------------------------
print("\n-- 2. Entry = block midpoint --")

check("BlockEntryPrice located", len(BEP) > 100, len(BEP))
check("CalcEntryPrice located", len(CALC) > 100, len(CALC))
check("BlockEntryPrice returns b.midpoint for the midpoint style",
      "if(InpEntryStyle == ENTRY_MIDPOINT) return b.midpoint;" in BEP, BEP[:90])
check("CalcEntryPrice returns block.midpoint for the midpoint style",
      "if(InpEntryStyle == ENTRY_MIDPOINT)" in CALC and
      "return block.midpoint;" in CALC, CALC[:90])

# The midpoint branch must not consult direction or ATR: the centre of a zone is
# one number. A direction branch here would be a real bug -- it would return the
# same value twice and imply a symmetry that does not need expressing.
_mid = BEP[BEP.find("ENTRY_MIDPOINT"):BEP.find("ENTRY_MIDPOINT") + 80]
check("the midpoint branch is direction-independent (no DIR_ in it)",
      "DIR_" not in _mid, _mid[:70])

# midpoint must actually BE (top+bottom)/2 wherever it is written. All four
# creation sites in COttoBlockManager spell the same expression; the identity is
# the only thing standing between "midpoint entry" and an arbitrary offset.
# Scanned on LIVE (comment-stripped) text: the v5.72 header block in
# COttoBlockManager *documents* the same expression, and a raw scan counts that
# prose as a fifth assignment.
mid_defs = re.findall(r"\.midpoint\s*=\s*([^;]+);", " ".join(LIVE.values()))
_norm = [re.sub(r"\s+", "", m) for m in mid_defs]
check("midpoint is assigned as (top + bottom) / 2.0 at every creation site",
      len(_norm) == 4 and all(n == "(zoneTop+zoneBot)/2.0" for n in _norm),
      mid_defs)


# ----------------------------------------------------------------------
# 3. The stop still anchors off entry, and slDist is NOT coupled to it
# ----------------------------------------------------------------------
print("\n-- 3. Stop = entry -/+ slDist, slDist unchanged --")

check("CalcSLDistance located", len(SLD) > 80, len(SLD))
check("CalcSLDistance is still blockHeight + 0.5*ATR",
      re.search(r"return\s+block\.blockHeight\s*\+\s*\(0\.5\s*\*\s*atr\)\s*;",
                SLD) is not None, SLD[:120])
# The sizing contract: slDist must not learn about the entry. If it gains an
# entry/midpoint reference, position size silently starts tracking entry geometry
# and the whole "risk per unit is unchanged" claim collapses.
check("CalcSLDistance does NOT consume the entry price or the midpoint",
      "midpoint" not in SLD and "entry" not in SLD.lower(), SLD[:140])
check("no entry-style branch was introduced into CalcSLDistance",
      "ENTRY_MIDPOINT" not in SLD and "InpEntryStyle" not in SLD)
check("the stop is still entry -/+ slDist",
      re.search(r"isLong\s*\?\s*entryPrice\s*-\s*slDist\s*:\s*entryPrice\s*\+\s*slDist",
                OM_C) is not None)


# ----------------------------------------------------------------------
# 4. The crossing guard keeps its midpoint exemption
# ----------------------------------------------------------------------
print("\n-- 4. Crossing guard scoped away from MIDPOINT --")

# THE HIGHEST-VALUE ASSERTION IN THIS FILE. A midpoint entry sits behind the
# market, so IsEntryCrossed() is TRUE on the very first healthy tick. Un-scoping
# the guard would therefore retire every midpoint setup -- and every other probe
# in the suite would still pass, because they all describe front-edge geometry.
check("the guard is still scoped `InpEntryStyle != ENTRY_MIDPOINT`",
      re.search(r"if\s*\(\s*InpEntryStyle\s*!=\s*ENTRY_MIDPOINT\s*&&\s*"
                r"IsEntryCrossed\(", OM_C) is not None,
      "an unscoped guard would retire every midpoint setup")
check("IsEntryCrossed is still defined and callable",
      re.search(r"bool\s+IsEntryCrossed\s*\(", OM_C) is not None)
check("the router still returns a LIMIT order type (midpoint rests physically)",
      "ORDER_TYPE_BUY_LIMIT" in body_of(OM_C, "GetOrderTypeForBlock"))


# ----------------------------------------------------------------------
# 5. Journal prose follows the input instead of asserting one geometry
# ----------------------------------------------------------------------
print("\n-- 5. Journal labels are style-aware --")

check("the armed record selects its entry formula from InpEntryStyle",
      "InpEntryStyle == ENTRY_MIDPOINT" in JRN_RAW)
check("the journal prints the midpoint formula",
      "(top + bottom) / 2.0" in JRN_RAW)
check("the journal carries the 'Midpoint Pullback' wording",
      "Midpoint Pullback" in JRN_RAW)
check("the front-edge wording is RETAINED for the selectable style",
      "Near-Edge Pullback entry: near edge +/- (blockHeight + 1.0*ATR)" in JRN_RAW)
check("the journal does not hardcode ONE formula for both styles",
      "string entryFormula" in JRN_RAW)
check("the projected target keeps its style-independent far-edge anchor",
      "v5.72 -- STILL the far-edge anchor" in JRN_RAW)


# ----------------------------------------------------------------------
# 6. Documentation records the flip
# ----------------------------------------------------------------------
print("\n-- 6. README + release stamps --")

README = read(os.path.join(ROOT, "README.md"))
check("README documents the v5.72 midpoint default",
      "v5.72" in README and "midpoint" in README.lower())
check("README carries the Current base line for this release",
      ("**Current base: v%s**" % RELEASE) in README,
      RELEASE)

stale = []
for f in SHIPPED:
    m = re.search(r'#property\s+version\s+"([0-9.]+)"', SRC[f])
    if not m or m.group(1) != RELEASE:
        stale.append((f, m.group(1) if m else None))
check("all %d shipped files stamp v%s" % (len(SHIPPED), RELEASE), not stale, stale)


def main():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("=" * 74)
    print("v5.72 DEFAULT ENTRY STYLE = BLOCK MIDPOINT -- STATIC PROBE")
    print("=" * 74)
    for name, ok, detail in RESULTS:
        line = "  [%s] %s" % ("PASS" if ok else "FAIL", name)
        if not ok and detail != "":
            line += "  <%s>" % (detail,)
        print(line)
    print("-" * 74)
    print("%d / %d checks passed" % (passed, total))
    if passed != total:
        print("*** PROBE FAILED ***")
        return 1
    print("*** ALL CHECKS PASSED ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())


