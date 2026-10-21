"""
v5.71 static verification probe - DEFAULT PRIMARY TIMEFRAME IS 1 HOUR.

v5.71 changes exactly ONE character-level thing in the shipped sources -- the
default of InpPrimaryTF, M15 -> H1 -- plus the prose that described it. That is
precisely the kind of edit that slips: it compiles identically either way, no
formula changes, and nothing in the tree can notice that the documentation
still claims M15. So this probe pins the value, the contract that makes the
value authoritative, and the blast radius around it.

WHAT THE VALUE ACTUALLY CONTROLS. InpPrimaryTF is not a display default. It is
the period handed to every iTime/iHigh/iLow/iOpen/iClose/iBarShift/Bars call in
COttoBlockManager and COttoMarketStructure, to the iATR handle, and to the
IsNewBar() funnel gate. Changing it retimes the whole engine:

  * the funnel wakes once an HOUR instead of every 15 minutes;
  * InpRightBars=3 confirmation lag goes 45 min -> 3 hours;
  * ATRPeriod=14 spans 14 hours instead of 3.5, so rrUnit = blockHeight +
    0.5*ATR is measured on a wider unit -> WIDER stops, SMALLER lots, with
    RiskPercent itself untouched;
  * MaxBlockDistance=150 / LookbackBars=300 rebase from ~37.5 h / ~3 days to
    ~6.25 / ~12.5 days.

None of that is asserted as "correct" here -- it is a strategy decision, not an
invariant. What IS asserted is that the decision is recorded consistently: the
default, the chart-independence contract that lets a bare input govern
structure, and the consumers still reading it.

THE NEGATIVE ASSERTIONS ARE THE POINT. The dangerous edits around a change like
this are all find-replace accidents, and each is invisible to the compiler:

  * a blind `PERIOD_*` sweep that also retargets PERIOD_D1, silently retiring
    the market-day counter (a CALENDAR concept that must not follow the
    strategy period);
  * a blind sweep that "helpfully" makes the retired InpAnchorTF no-op live
    again -- it is declared `input int = PERIOD_H1`, so after this release it
    LOOKS like the knob that did the work;
  * PERIOD_CURRENT creeping back in, which would silently re-couple the funnel
    to whatever chart the EA happens to sit on and undo the whole
    chart-independence contract from v5.66;
  * the ATR handle quietly keying on the chart period while every price call
    keys on InpPrimaryTF, which would make stops and structure disagree.

WHAT IT CANNOT PROVE. That H1 is the better timeframe, and that the terminal
resolves H1 bars for a symbol with a short history -- both runtime properties.
This is static analysis of the shipped sources; no MT5 required.
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

    Load-bearing here: the v5.71 rationale block in OttoDefines.mqh names
    PERIOD_M15 (the retired default), PERIOD_D1 and the retiming arithmetic in
    prose. A raw substring scan would report the documentation of the change as
    a violation of it, which would push a future maintainer to delete the
    rationale to get a green probe.
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
DEFS_C = LIVE["OttoDefines.mqh"]
MAIN_C = LIVE["otto.mq5"]
BLOCK_C = LIVE["COttoBlockManager.mqh"]
STRUCT_C = LIVE["COttoMarketStructure.mqh"]

_STAMP = re.search(r'#property\s+version\s+"([0-9.]+)"', SRC["OttoDefines.mqh"])
RELEASE = _STAMP.group(1) if _STAMP else "?"


# ----------------------------------------------------------------------
# 1. The default is exactly PERIOD_H1, and still an ENUM_TIMEFRAMES.
# ----------------------------------------------------------------------
print("\n-- 1. InpPrimaryTF defaults to PERIOD_H1 --")

DECL = re.search(
    r"^\s*input\s+ENUM_TIMEFRAMES\s+InpPrimaryTF\s*=\s*([A-Z0-9_]+)\s*;",
    DEFS_C, re.M)
TF = DECL.group(1) if DECL else None

check("InpPrimaryTF is declared as input ENUM_TIMEFRAMES", DECL is not None)
check("InpPrimaryTF defaults to PERIOD_H1", TF == "PERIOD_H1", TF or "not found")
# The retired default must not survive as the LIVE value. If a future edit
# reverts it, this fails instead of silently retiming the whole engine.
check("the live default is no longer PERIOD_M15", TF != "PERIOD_M15",
      TF or "not found")
# Exactly one live default; a second declaration would be a shadowing copy.
N_DECL = len(re.findall(r"^\s*input\s+ENUM_TIMEFRAMES\s+InpPrimaryTF\b",
                        DEFS_C, re.M))
check("InpPrimaryTF is declared exactly once", N_DECL == 1, N_DECL)


# ----------------------------------------------------------------------
# 2. Chart independence -- nothing reads the chart period.
# ----------------------------------------------------------------------
print("\n-- 2. The EA never reads the chart period --")

for token in ("_Period", "Period()"):
    hits = [f for f, body in LIVE.items() if token in body]
    check("no live code reads %s" % token, not hits, hits)

# PERIOD_CURRENT is the other way to re-couple to the chart. v5.66 removed it;
# this pins that it has not crept back in.
hits = [f for f, body in LIVE.items() if "PERIOD_CURRENT" in body]
check("PERIOD_CURRENT has not crept back in", not hits, hits)


# ----------------------------------------------------------------------
# 3. Every consumer still keys on InpPrimaryTF.
# ----------------------------------------------------------------------
print("\n-- 3. Structure, ATR and the bar gate follow InpPrimaryTF --")

check("the ATR handle is built on InpPrimaryTF, not the chart period",
      re.search(r"iATR\s*\(\s*m_symbol\s*,\s*InpPrimaryTF\s*,\s*ATRPeriod\s*\)",
                BLOCK_C) is not None)
check("the funnel gate IsNewBar() keys on InpPrimaryTF",
      re.search(r"iTime\s*\(\s*_Symbol\s*,\s*InpPrimaryTF\s*,\s*0\s*\)",
                MAIN_C) is not None)
check("the block manager's own bar gate keys on InpPrimaryTF",
      re.search(r"iTime\s*\(\s*m_symbol\s*,\s*InpPrimaryTF\s*,\s*0\s*\)",
                BLOCK_C) is not None)

# If only the gate moved on to H1 while the price calls stayed elsewhere, stops
# and structure would disagree about which bars they are looking at. Pin that
# no price call hard-codes its own period.
N_BLOCK = len(re.findall(r"\b(?:iHigh|iLow|iOpen|iClose|iTime|iBarShift|Bars)"
                         r"\s*\(\s*m_symbol\s*,\s*PERIOD_", BLOCK_C))
check("no block-manager price call hard-codes a PERIOD_ constant",
      N_BLOCK == 0, N_BLOCK)

N_STRUCT = len(re.findall(r"\b(?:iHigh|iLow|iOpen|iClose|iTime)\s*\("
                          r"\s*m_symbol\s*,\s*PERIOD_", STRUCT_C))
check("no market-structure price call hard-codes a PERIOD_ constant",
      N_STRUCT == 0, N_STRUCT)


# ----------------------------------------------------------------------
# 4. The calendar counter still runs on D1 -- deliberately NOT the strategy TF.
# ----------------------------------------------------------------------
print("\n-- 4. The market-day counter is still calendar-based --")

check("the market-day counter still keys on PERIOD_D1",
      re.search(r"iTime\s*\(\s*_Symbol\s*,\s*PERIOD_D1\s*,\s*0\s*\)", MAIN_C)
      is not None)
# The likeliest casualty of a blind PERIOD_* sweep: retargeting the D1 counter
# to H1 would silently retire the market-day gate. A calendar concept must not
# follow the strategy period.
check("PERIOD_D1 was not swept away by the timeframe change",
      MAIN_C.count("PERIOD_D1") == 2, MAIN_C.count("PERIOD_D1"))
# Exactly two primary-TF gate sites in otto.mq5: the init seed + IsNewBar().
N_GATE = len(re.findall(r"iTime\s*\(\s*_Symbol\s*,\s*InpPrimaryTF\s*,\s*0\s*\)",
                        MAIN_C))
check("otto.mq5 seeds and gates on exactly two primary-TF iTime calls",
      N_GATE == 2, N_GATE)


# ----------------------------------------------------------------------
# 5. InpAnchorTF stays a RETIRED no-op -- it now LOOKS like the live knob.
# ----------------------------------------------------------------------
print("\n-- 5. InpAnchorTF is still a retired no-op --")

# NOTE: the RETIRED label lives in a // comment, so these two read the RAW
# source, not the comment-stripped view used everywhere else.
check("InpAnchorTF is still declared (so old .set files load)",
      re.search(r"^\s*input\s+int\s+InpAnchorTF\b", SRC["OttoDefines.mqh"], re.M)
      is not None)
check("InpAnchorTF is still labelled RETIRED",
      re.search(r"^\s*input\s+int\s+InpAnchorTF\s*=.*RETIRED",
                SRC["OttoDefines.mqh"], re.M) is not None)
# Its default is PERIOD_H1 -- identical to the new live default -- so a future
# reader could mistake it for the knob that did the work. It has no readers.
READERS = [f for f, body in LIVE.items()
           if f != "OttoDefines.mqh" and "InpAnchorTF" in body]
check("no shipped module reads InpAnchorTF", not READERS, READERS)


# ----------------------------------------------------------------------
# 6. Documentation and release stamps agree with the sources.
# ----------------------------------------------------------------------
print("\n-- 6. Docs and release stamps agree --")

RM = read(os.path.join(ROOT, "README.md"))
check("README states the primary TF is PERIOD_H1",
      "Primary timeframe: `PERIOD_H1`" in RM)
check("README no longer claims the primary TF is PERIOD_M15",
      "Primary timeframe: `PERIOD_M15`" not in RM)
check("README no longer says structure is computed on M15",
      "still computed on M15" not in RM)
check("README documents the current base",
      ("**Current base: v%s**" % RELEASE) in RM)
check("README has a v%s changelog section" % RELEASE,
      ("### Changed in v%s " % RELEASE) in RM)

# The v5.66 header comment in otto.mq5 named the OLD default in prose. Prose
# that contradicts the shipped value is worse than no comment at all.
check("the IsNewBar() header no longer names M15 as the default",
      "default M15" not in SRC["otto.mq5"])

# All shipped stamps move together. A half-bumped tree is the classic failure
# here: the probe derives RELEASE rather than pinning it, so this check stays
# correct on the next bump without editing.
stale = []
for f in SHIPPED:
    m = re.search(r'#property\s+version\s+"([0-9.]+)"', SRC[f])
    if not m or m.group(1) != RELEASE:
        stale.append((f, m.group(1) if m else None))
check("all %d shipped files stamp v%s" % (len(SHIPPED), RELEASE),
      not stale, stale)


def main():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("=" * 74)
    print("v5.71 DEFAULT PRIMARY TIMEFRAME = PERIOD_H1 -- STATIC PROBE")
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
