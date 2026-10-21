"""
v5.69 static verification probe - GEOMETRIC RISK CASCADE + FULL BLOCK GEOMETRY.

Two independent changes are pinned here.

  1. THE LADDER IS NOW A GEOMETRIC CASCADE. v5.68 had halved every rung, which
     turned the v5.61 flat-head shape (T1 == T2) into 0.5 / 0.5 / 0.25 / 0.125.
     v5.69 restores ONLY T1 and leaves the three scale-ins untouched, so each
     rung now risks exactly half the rung above it:
        T1 RiskPercent   0.5   -> 1.0     (at market)
        T2 InpRiskT2Pct  0.5   -> 0.5     (at +1.0R)  unchanged
        T3 InpRiskT3Pct  0.25  -> 0.25    (at +2.0R)  unchanged
        T4 InpRiskT4Pct  0.125 -> 0.125   (at +3.0R)  unchanged
        summed                 1.375% -> 1.875%
     The flat-head shape is GONE ON PURPOSE: T1 no longer equals T2, so the
     old "T1 == T2" assertion is deleted rather than softened. A future edit
     that re-flattens the head must now red a probe instead of sliding past.
     Nothing about the GEOMETRY moved: every scale-in trigger, breakeven floor,
     profit lock and ATR trail rung is an R-multiple of the primary's own 1R,
     so changing the % risk moves LOTS and MONEY, never the price levels at
     which the ladder advances. That separation is pinned in section 3,
     because a future "tune the risk" edit that also touched a trigger would
     silently re-time the entire trade.

  2. THE JOURNAL PRINTS THE FULL BLOCK GEOMETRY. Both LogSetupArmed() and
     LogEntry() carry block top / bottom / midpoint / height, and v5.68 added
     the standalone block height in price AND pips, the 1R stop distance in
     price AND pips, and the risk allocation actually being committed.
     LogEntry() additionally prints the REALIZED fill-to-SL distance beside the
     planned 1R, so a slipped fill is visible in the journal instead of
     hiding behind the planned number. v5.69 retags the allocation row from
     "(v5.68 baseline)" to "(equity-based)" because there is no baseline to
     name any more -- sizing reads live equity at order time.

WHY A PROBE AND NOT JUST THE COMPILER. None of this is visible to MQL5C.
Doubling a `const double` compiles identically whether or not the auditor's
tolerance, the pyramid probe's pinned sum, or the documented per-leg rationale
were updated with it, and a journal row prints the same whether or not the
value behind it is the number the sizer will commit. So this probe pins the
NUMBERS, the ARITHMETIC RELATIONSHIP between them, and the ROW STRUCTURE that
the operator reads. It also pins the NEGATIVE direction: section 2 asserts that
the dead SafetyMaxRiskPct input and the whole prop-firm group are GONE, not
merely unused.

WHAT IT CANNOT PROVE. That a real fill slips, or that the terminal renders
the rows exactly as written, are runtime properties. This is static analysis
of the shipped sources -- no MT5 required.
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "otto.mq5")
DEFS = os.path.join(ROOT, "OttoDefines.mqh")
JRN = os.path.join(ROOT, "COttoJournal.mqh")
RISK = os.path.join(ROOT, "COttoRiskManager.mqh")
AUD = os.path.join(ROOT, "CHighTableAuditor.mqh")
TRADE = os.path.join(ROOT, "COttoTradeManager.mqh")

ALL_FILES = ["otto.mq5", "COttoOrderManager.mqh", "COttoTradeManager.mqh",
             "COttoRiskManager.mqh", "COttoBlockManager.mqh", "COttoJournal.mqh",
             "CHighTableAuditor.mqh", "COttoMarketStructure.mqh",
             "OttoDefines.mqh"]

# Auto-detect the release from the source stamp instead of hard-coding it, so a
# version bump does not require touching this probe (v5.68 hard-coded it and had
# to be edited by the v5.69 bump; every other probe already auto-detects).
_STAMP = re.search(r'#property\s+version\s+"([0-9.]+)"',
                   io.open(os.path.join(ROOT, "OttoDefines.mqh"),
                           encoding="utf-8", errors="replace", newline="").read())
RELEASE = _STAMP.group(1) if _STAMP else "?"


def read(p):
    # Normalise CRLF so every anchor below can be written with a plain \n.
    return io.open(p, encoding="utf-8", errors="replace",
                   newline="").read().replace("\r\n", "\n")


def strip_comments(code):
    """Drop // comments, respecting string literals.

    Load-bearing here: the v5.69 notes quote the RETIRED 0.5% / 1.375% figures
    in place ("restored to 1.0%", "was 1.375 in v5.68"), so a raw substring
    test would trip over the probe's own subject matter.
    """
    out = []
    for line in code.split("\n"):
        idx = line.find("//")
        if idx < 0:
            out.append(line)
            continue
        out.append(line if line[:idx].count('"') % 2 else line[:idx])
    return "\n".join(out)


def num_input(text, name):
    """Default of a top-level `input|const double NAME = <value>;`.

    RiskPercent is deliberately a `const` (terminal-override lock) while every
    other rung stays an `input`, so the qualifier is matched either way.
    """
    m = re.search(r"^\s*(?:input|const)\s+double\s+" + re.escape(name) +
                  r"\s*=\s*([0-9]*\.?[0-9]+)\s*;", text, re.M)
    return float(m.group(1)) if m else None


RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


MAIN_T = read(MAIN)
DEFS_T = read(DEFS)
DEFS_C = strip_comments(DEFS_T)
JRN_RAW = read(JRN)
JRN_C = strip_comments(JRN_RAW)
RISK_T = read(RISK)
AUD_C = strip_comments(read(AUD))
TRADE_C = strip_comments(read(TRADE))



# ----------------------------------------------------------------------
# 1. T1 was restored, the three scale-ins held, and the cascade is CONSISTENT.
# ----------------------------------------------------------------------
print("\n-- 1. The risk ladder is a geometric cascade --")

T1 = num_input(DEFS_C, "RiskPercent")
T2 = num_input(DEFS_C, "InpRiskT2Pct")
T3 = num_input(DEFS_C, "InpRiskT3Pct")
T4 = num_input(DEFS_C, "InpRiskT4Pct")

check("T1 RiskPercent is 1.0 (restored from v5.68's 0.5)", T1 == 1.0, T1)
check("T2 InpRiskT2Pct is still 0.5 (not restored with T1)", T2 == 0.5, T2)
check("T3 InpRiskT3Pct is still 0.25 (untouched since v5.68)", T3 == 0.25, T3)
check("T4 InpRiskT4Pct is still 0.125 (untouched since v5.68)", T4 == 0.125, T4)

if None not in (T1, T2, T3, T4):
    # The v5.61 flat head (T1 == T2) is deliberately GONE. Asserted as a strict
    # inequality so a future edit that re-flattens the ladder reds here.
    check("the head is no longer FLAT (T1 > T2, flat-head shape retired)",
          T1 > T2, (T1, T2))
    check("the ladder descends strictly (T1 > T2 > T3 > T4)",
          T1 > T2 > T3 > T4, (T1, T2, T3, T4))
    check("EVERY rung is exactly HALF the one above it (geometric cascade)",
          abs(T1 / 2.0 - T2) < 1e-12 and abs(T2 / 2.0 - T3) < 1e-12
          and abs(T3 / 2.0 - T4) < 1e-12, (T1, T2, T3, T4))
    total = T1 + T2 + T3 + T4
    check("the summed stacked exposure is 1.875 (was 1.375 in v5.68)",
          abs(total - 1.875) < 1e-12, total)
    check("no rung rounded to zero or went negative",
          min(T1, T2, T3, T4) > 0.0, min(T1, T2, T3, T4))
else:
    for n in ("the head is no longer FLAT (T1 > T2, flat-head shape retired)",
              "the ladder descends strictly (T1 > T2 > T3 > T4)",
              "EVERY rung is exactly HALF the one above it (geometric cascade)",
              "the summed stacked exposure is 1.875 (was 1.375 in v5.68)",
              "no rung rounded to zero or went negative"):
        check(n, False, (T1, T2, T3, T4))

check("still no dead InpRiskT1Pct input",
      re.search(r"^\s*input\s+double\s+InpRiskT1Pct", DEFS_C, re.M) is None)


# ----------------------------------------------------------------------
# 2. The prop-firm safety group is GONE, and the auditor ceiling follows T1.
# ----------------------------------------------------------------------
print("\n-- 2. Prop-firm safety group deleted; auditor ceiling derived --")

# v5.69 deletes the three prop-firm inputs outright rather than keeping them as
# no-ops, because nothing in the tree ever read them. Absence -- not a value --
# is the assertion, so the probe reds if any of them is re-declared.
for gone in ("SafetyMaxRiskPct", "SafetyDailyDDLimit", "SafetyTotalDDLimit"):
    check("%s is deleted from the inputs, not merely unused" % gone,
          num_input(DEFS_C, gone) is None)
check("the prop-firm group header is deleted",
      "PROP FIRM SAFETY BUFFERS" not in strip_comments(DEFS_T))

# The per-leg budget the dead input pretended to own is enforced at runtime and
# DERIVED from RiskPercent, so it tracks T1 automatically (1.0 * 1.5 = 1.5%).
check("the auditor still derives its ceiling from RiskPercent at runtime",
      re.search(r"RiskPercent\s*\*\s*1\.50", AUD_C) is not None)
check("the auditor does NOT read the deleted input",
      "SafetyMaxRiskPct" not in AUD_C)
if None not in (T1, T2):
    CEILING = T1 * 1.50
    check("the derived ceiling brackets the peak single leg (1.5%% vs %.3f%%)"
          % max(T1, T2), max(T1, T2) < CEILING,
          "%s < %s" % (max(T1, T2), CEILING))

check("the new ladder is documented in the inputs, so it is not a silent edit",
      "1.875" in DEFS_T and "GEOMETRIC CASCADE" in DEFS_T)
check("the retired flat-head rationale is gone from the live inputs",
      "FLAT-HEAD pyramid" not in strip_comments(DEFS_T))



# ----------------------------------------------------------------------
# 3. The ladder change touches MONEY, never GEOMETRY.
# ----------------------------------------------------------------------
print("\n-- 3. Risk % moves lots, never price levels --")

# Every scale-in / floor / lock / trail trigger is an R-multiple of the
# primary's own 1R. Pin that they are still expressed in R and were NOT
# touched by a percentage change.
R_INPUTS = ["InpPyramidT2RR", "InpPyramidT3RR", "InpPyramidT4RR",
            "InpBreakEvenRR", "InpTrailStartRR", "InpLockProfit2RR",
            "InpLockProfitRR"]
missing_r = [n for n in R_INPUTS if num_input(DEFS_C, n) is None]
check("every ladder trigger is still an R-multiple input", not missing_r, missing_r)

if not missing_r:
    rr = dict((n, num_input(DEFS_C, n)) for n in R_INPUTS)
    check("the triggers stay STRICTLY ASCENDING after the risk change",
          rr["InpPyramidT2RR"] < rr["InpPyramidT3RR"] < rr["InpPyramidT4RR"],
          rr)
    check("no R trigger is expressed as a fraction that a % edit could hit",
          all(v >= 0.5 for v in rr.values()), rr)

# The "half-risk" rung inside the TradeManager is an R-TRAIL milestone, not a
# % risk knob. It must NOT have been swept up in either risk edit.
check("the trade manager's half-risk rung is an R milestone, not a % knob",
      "m_halfRiskTriggers" in TRADE_C)
check("no % risk literal leaked into the trade manager",
      re.search(r"RiskPercent\s*[*/,]", TRADE_C) is None)


# ----------------------------------------------------------------------
# 4. The auditor's tolerance follows its OWN derived ceiling, not the
#    deleted input, and the T1 change moved it back to 1.5%.
# ----------------------------------------------------------------------
print("\n-- 4. The auditor tolerance is derived, never a literal --")

check("the auditor still derives its ceiling from RiskPercent at runtime",
      re.search(r"RiskPercent\s*\*\s*1\.50", AUD_C) is not None)
check("the auditor ceiling was NOT hard-coded to a literal",
      re.search(r"RiskPercent\s*\*\s*1\.50", AUD_C) is not None and
      "0.75" not in AUD_C)
# v5.69 deleted the whole drawdown layer from the auditor; only the per-leg
# risk check survives, which is what keeps this ceiling meaningful.
check("the auditor's drawdown machinery is gone",
      "AuditDrawdown" not in AUD_C or
      AUD_C.count("AuditDrawdown") == 1)   # one surviving tombstone comment
check("the auditor no longer latches a daily or total DD breach",
      "m_alertSent_DailyDDBreach" not in AUD_C.replace(
          "// v5.69: the drawdown latches (m_alertSent_DailyDDBreach,", ""))


# ----------------------------------------------------------------------
# 5. LogSetupArmed() carries the full block geometry.
# ----------------------------------------------------------------------
print("\n-- 5. Armed journal: full block geometry --")

# The combined Top/Bottom/Mid/Height row must still exist EXACTLY TWICE (once
# per logging method) -- test_v557 pins that count, so a restructure here
# would double-count.
MID_ROW = re.compile(r"\|\s*Mid=\"\s*\+\s*FmtPrice\(blk\.midpoint\)\s*\+\s*\"\s*\|\s*Height=")
n_mid = len(MID_ROW.findall(JRN_RAW))
check("the combined Mid/Height row still appears exactly twice", n_mid == 2, n_mid)

ARM = JRN_RAW[JRN_RAW.find("void              LogSetupArmed"):
              JRN_RAW.find("void              LogEntry")]
ENTRY = JRN_RAW[JRN_RAW.find("void              LogEntry"):
                JRN_RAW.find("void              LogPyramid")]
check("LogSetupArmed body was located", len(ARM) > 200, len(ARM))
check("LogEntry body was located", len(ENTRY) > 200, len(ENTRY))

check("the armed record prints the Trade Entry Point",
      "Trade Entry Point : " in ARM)
check("the armed record still explains the entry formula",
      "Near-Edge Pullback entry: near edge +/- (blockHeight + 1.0*ATR)" in ARM)
check("the armed record prints the Initial SL with its 1R",
      "Initial SL        : " in ARM and "1R = " in ARM)

# The geometry trio the operator asked for: height, distance, money.
check("the armed record prints a standalone Block Height row",
      "Block Height      : " in ARM)
check("the block height row carries pips as well as price",
      re.search(r"Block Height\s*:\s*\"\s*\+\s*FmtPrice\(blk\.blockHeight\)\s*\+\s*\"\s*\(\"\s*\+\s*FmtPips\(blk\.blockHeight\)",
                ARM) is not None)
check("the armed record prints the 1R stop distance in pips too",
      re.search(r"SL Distance \(1R\)\s*:.*FmtPips\(blk\.rrUnit\)", ARM) is not None)
check("the armed record prints the risk allocation and its dollar value",
      "Risk Allocation   : " in ARM and "RiskMoneyAt(RiskPercent)" in ARM)
check("the allocation row states the % it is quoting",
      re.search(r"Risk Allocation.*DoubleToString\(RiskPercent,\s*2\)\s*\+\s*\"%",
                ARM) is not None)

# Wick anchors: the timestamp + H/L rows survive, and now name the pivot.
check("both wick anchors still print a timestamp and H/L",
      "Wick 1 (Anchor)   : " in ARM and "Wick 2 (Retest)   : " in ARM and
      "H=\" + FmtPrice(blk.wick1.highPrice)" in ARM and
      "L=\" + FmtPrice(blk.wick1.lowPrice)" in ARM)
check("each wick row now names the pivot price that anchored the block",
      "Anchor=\" + FmtPrice(blk.wick1.price)" in ARM and
      "Anchor=\" + FmtPrice(blk.wick2.price)" in ARM)


# ----------------------------------------------------------------------
# 6. LogEntry() mirrors the geometry AND exposes a slipped fill.
# ----------------------------------------------------------------------
print("\n-- 6. Entry journal: geometry mirrored + real fill visible --")

check("the entry record prints the Execution Price",
      "Execution Price   : " in ENTRY)
check("the entry record prints the Initial Stop Loss with Target",
      "Initial Stop Loss : " in ENTRY and "Target = " in ENTRY)
check("the entry record prints volume and the committed risk",
      "Volume & Sizing   : " in ENTRY)
check("the entry record mirrors a Block Height row",
      "Block Ht  : " in ENTRY)
check("the entry record prints the REALIZED fill-to-SL distance",
      re.search(r"SL Dist\s*:.*FmtPrice\(riskDist\)", ENTRY) is not None)
check("the realized distance is printed beside the PLANNED 1R",
      re.search(r"SL Dist\s*:.*planned 1R = \"\s*\+\s*FmtPrice\(blk\.rrUnit\)",
                ENTRY) is not None)
check("riskDist is no longer a computed-and-discarded local",
      ENTRY.count("riskDist") >= 2, ENTRY.count("riskDist"))
check("the entry record prints the committed risk and its effective %",
      "Risk Alloc: $" in ENTRY and "RiskPctTail(riskMoney)" in ENTRY)

# The two helpers that make the rows possible.
check("FmtPips() is now CONSUMED, not dead code",
      len(re.findall(r"FmtPips\(", JRN_RAW)) >= 4,
      len(re.findall(r"FmtPips\(", JRN_RAW)))
check("RiskMoneyAt() is defined and used",
      "double            RiskMoneyAt(double pct)" in JRN_RAW)
check("RiskPctTail() guards against an unusable equity value",
      re.search(r"string\s+RiskPctTail\(double money\)\s*\{\s*double eq = AccountInfoDouble\(ACCOUNT_EQUITY\);\s*if\(eq <= 0\.0 \|\| money <= 0\.0\) return \"\";",
                re.sub(r"\n\s*", " ", JRN_RAW)) is not None)


# ----------------------------------------------------------------------
# 7. The boot log makes the ladder visible.
# ----------------------------------------------------------------------
print("\n-- 7. Startup surfaces the current ladder --")

check("the init log names the risk % AND its dollar value",
      "on current equity)" in RISK_T)
check("the startup banner names the risk % and its dollar value",
      "% dynamic equity" in MAIN_T and "AccountInfoDouble(ACCOUNT_EQUITY)" in MAIN_T)
check("the startup banner prints the full ladder",
      "Ladder: T1 " in MAIN_T and "InpRiskT3Pct" in MAIN_T)
check("the startup banner no longer prints a DD budget it does not enforce",
      "DailyDD" not in MAIN_T and "TotalDD" not in MAIN_T)
check("the risk manager header no longer claims a flat 1% model",
      "Strict 1% dynamic-equity model" not in RISK_T)


# ----------------------------------------------------------------------
# 8. Nothing else was swept up in the edit.
# ----------------------------------------------------------------------
print("\n-- 8. No collateral damage --")

check("RiskPercent is still the ONLY source for T1 sizing",
      re.search(r"GetRiskMoney[\s\S]{0,400}RiskPercent", RISK_T) is not None)
check("the sizer still ABORTS below broker min rather than clamping up",
      "never fall back to a fixed lot" in RISK_T)
check("the shared overshoot factor is untouched",
      re.search(r"OTTO_RISK_OVERSHOOT_MULT", DEFS_T) is not None)

# The superseded sums must not survive in any LIVE code. 2.75% was the v5.67
# total and 1.375% the v5.68 total; both are quoted in comments as history,
# which is why the scan strips comments first.
STALE = []
for f in ALL_FILES:
    body = strip_comments(read(os.path.join(ROOT, f)))
    if "2.75" in body or "1.375" in body:
        STALE.append(f)
check("no live code still asserts a retired ladder sum (2.75 / 1.375)",
      not STALE, STALE)


# ----------------------------------------------------------------------
# 9. Version stamps agree on the current release.
# ----------------------------------------------------------------------
print("\n-- 9. Release stamps --")

prop = []
for f in ALL_FILES:
    m = re.search(r'#property\s+version\s+"([0-9.]+)"', read(os.path.join(ROOT, f)))
    prop.append(m.group(1) if m else None)
missing = [(f, v) for f, v in zip(ALL_FILES, prop) if v != RELEASE]
check("all %d files stamp v%s" % (len(ALL_FILES), RELEASE), not missing, missing)
check("README documents the current base",
      ("**Current base: v%s**" % RELEASE) in read(os.path.join(ROOT, "README.md")))
check("the startup banner names the current release",
      ("OTTO EA v%s" % RELEASE) in MAIN_T)
check("the EA description names the current release",
      ("OTTO v%s" % RELEASE) in DEFS_T)


def main():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("=" * 74)
    print("v5.69 GEOMETRIC RISK CASCADE + FULL BLOCK GEOMETRY - STATIC PROBE")
    print("=" * 74)
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        line = "  [%s] %s" % (mark, name)
        if not ok and detail:
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
