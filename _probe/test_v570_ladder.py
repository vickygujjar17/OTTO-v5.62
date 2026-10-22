"""
v5.70 static verification probe - NON-MONOTONIC RISK TIERS + +0.75R PROFIT LOCK.

Three independent changes are pinned here.

  1. THE LADDER DEEPENS AT THE CONFIRMED RUNG, THEN TAPERS. v5.69 was a strict
     geometric cascade (1.0 / 0.5 / 0.25 / 0.125). v5.70 inverts the top of that
     shape -- T1 is now the PROBE and T2 carries the largest allocation:
        T1 RiskPercent   1.0   -> 0.5     (at market)
        T2 InpRiskT2Pct  0.5   -> 1.0     (at +1.0R)
        T3 InpRiskT3Pct  0.25  -> 0.5     (at +2.0R)
        T4 InpRiskT4Pct  0.125 -> 0.25    (at +3.0R)
        summed                 1.875% -> 2.25%
     The new shape is NON-MONOTONIC (0.5 -> 1.0 -> 0.5 -> 0.25). The v5.69
     "descends strictly" and "every rung is exactly half" assertions are
     therefore DELETED, not softened: they encoded the retired cascade and
     cannot be satisfied by any correct v5.70 tree. What replaces them is the
     weaker ordering that actually survives -- T2 > T1, T2 > T3, T3 > T4, i.e.
     the confirmed rung is the peak and the ladder tapers below it. A future
     edit that restores a monotonic cascade must red here rather than slide by.
     Nothing about the GEOMETRY moved: every scale-in trigger, profit lock and
     ATR trail rung is still an R-multiple of the primary's own 1R, so changing
     the % risk moves LOTS and MONEY, never the price levels at which the ladder
     advances. That separation is pinned in section 3.

  2. THE +1.0R RUNG LOCKS +0.75R. Through v5.69 the +1.0R milestone moved the
     unified stop to COST-COVERING BREAKEVEN (entry +/- beOffset, i.e. ~+0.0R).
     v5.70 locks +0.75R instead, via the new InpBEProfitLockRR input. Friction
     survives as a FLOOR under the lock (MathMax on a LONG, MathMin on a SHORT),
     so the cost-covering guarantee is preserved rather than discarded and
     CalcBasketFriction() stays live. The T2 fill carries the same lock as its
     slOverride, so the largest rung is no longer born in the loosest stop.

  3. THE AUDITOR CEILING IS ANCHORED ON THE PEAK RUNG. A RiskPercent-anchored
     ceiling would now be 0.5 * 1.5 = 0.75% and would fire a false positive on
     every healthy 1.0% T2 leg. It is re-anchored on max(T1..T4) * 1.50, which
     is 1.5% here -- numerically identical to v5.69, so this release neither
     loosens nor tightens the watchdog, only its anchor.

WHY A PROBE AND NOT JUST THE COMPILER. None of this is visible to MQL5C.
Changing a `const double` compiles identically whether or not the auditor's
tolerance, the pyramid probe's pinned sum, or the documented per-leg rationale
were updated with it. Nor can the compiler notice that a probe still asserts a
geometric cascade the sources no longer implement. So this probe pins the
NUMBERS, the ARITHMETIC RELATIONSHIP between them, and the NEGATIVE direction:
section 2 asserts the retired 1.875% cascade rationale is GONE, not merely
absent from the code paths.

WHAT IT CANNOT PROVE. That a real fill slips, or that the terminal renders the
rows exactly as written, are runtime properties. This is static analysis of the
shipped sources -- no MT5 required.
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
# 1. The ladder deepens at T2 and tapers below it -- NON-MONOTONIC by design.
# ----------------------------------------------------------------------
print("\n-- 1. The risk ladder tapers from a confirmed-rung peak --")

T1 = num_input(DEFS_C, "RiskPercent")
T2 = num_input(DEFS_C, "InpRiskT2Pct")
T3 = num_input(DEFS_C, "InpRiskT3Pct")
T4 = num_input(DEFS_C, "InpRiskT4Pct")

check("T1 RiskPercent is 0.5 (the probe rung, halved from v5.69's 1.0)",
      T1 == 0.5, T1)
check("T2 InpRiskT2Pct is 1.0 (the confirmed rung carries the size)",
      T2 == 1.0, T2)
check("T3 InpRiskT3Pct is 0.5", T3 == 0.5, T3)
check("T4 InpRiskT4Pct is 0.25", T4 == 0.25, T4)

if None not in (T1, T2, T3, T4):
    # The v5.69 geometric cascade (T1 > T2 > T3 > T4, each exactly half the one
    # above) is RETIRED. Those two assertions are deleted outright: no correct
    # v5.70 tree can satisfy them, so keeping a softened version would only
    # preserve a claim the operator has explicitly reversed. What replaces them
    # is the weaker shape that IS still intended -- T2 is the peak (it is the
    # only rung taken after the trade has already proven a full R) and the
    # ladder tapers monotonically below it.
    check("T2 is the PEAK rung (T2 > T1 and T2 > T3)",
          T2 > T1 and T2 > T3, (T1, T2, T3))
    check("the ladder tapers strictly below the peak (T2 > T3 > T4)",
          T2 > T3 > T4, (T2, T3, T4))
    check("the ladder is NON-MONOTONIC -- the retired cascade is NOT restored",
          not (T1 >= T2 >= T3 >= T4), (T1, T2, T3, T4))
    check("no rung is exactly half the one above it (cascade retired)",
          not (abs(T1 / 2.0 - T2) < 1e-12 and abs(T2 / 2.0 - T3) < 1e-12
               and abs(T3 / 2.0 - T4) < 1e-12), (T1, T2, T3, T4))
    total = T1 + T2 + T3 + T4
    check("the summed stacked exposure is 2.25 (was 1.875 in v5.69)",
          abs(total - 2.25) < 1e-12, total)
    check("no rung rounded to zero or went negative",
          min(T1, T2, T3, T4) > 0.0, min(T1, T2, T3, T4))
else:
    for n in ("T2 is the PEAK rung (T2 > T1 and T2 > T3)",
              "the ladder tapers strictly below the peak (T2 > T3 > T4)",
              "the ladder is NON-MONOTONIC -- the retired cascade is NOT restored",
              "no rung is exactly half the one above it (cascade retired)",
              "the summed stacked exposure is 2.25 (was 1.875 in v5.69)",
              "no rung rounded to zero or went negative"):
        check(n, False, (T1, T2, T3, T4))

check("still no dead InpRiskT1Pct input",
      re.search(r"^\s*input\s+double\s+InpRiskT1Pct", DEFS_C, re.M) is None)


# ----------------------------------------------------------------------
# 2. The prop-firm group stays deleted; the auditor ceiling follows the PEAK RUNG.
# ----------------------------------------------------------------------
print("\n-- 2. Prop-firm safety group still deleted; ceiling anchored on the peak --")

# v5.69 deletes the three prop-firm inputs outright rather than keeping them as
# no-ops, because nothing in the tree ever read them. Absence -- not a value --
# is the assertion, so the probe reds if any of them is re-declared.
for gone in ("SafetyMaxRiskPct", "SafetyDailyDDLimit", "SafetyTotalDDLimit"):
    check("%s is deleted from the inputs, not merely unused" % gone,
          num_input(DEFS_C, gone) is None)
check("the prop-firm group header is deleted",
      "PROP FIRM SAFETY BUFFERS" not in strip_comments(DEFS_T))

# The per-leg budget the dead input pretended to own is enforced at runtime and
# DERIVED from the PEAK RUNG, so it tracks whichever tier is largest (1.0 * 1.5
# = 1.5%). It must NOT be anchored on RiskPercent alone: with T1 halved to 0.5 a
# RiskPercent-anchored ceiling would be 0.75%, below the 1.0% T2 leg, and the
# watchdog would fire on a perfectly healthy pyramid.
check("the auditor derives its ceiling from the PEAK RUNG, not from T1",
      re.search(r"peakRungPct\s*\*\s*1\.50", AUD_C) is not None)
check("the peak-rung anchor actually takes the max over all four tiers",
      re.search(r"peakRungPct\s*=\s*MathMax\(\s*RiskPercent\s*,[\s\S]{0,200}"
                r"InpRiskT2Pct[\s\S]{0,200}InpRiskT3Pct[\s\S]{0,200}InpRiskT4Pct",
                AUD_C) is not None)
check("the auditor no longer multiplies RiskPercent alone (T1 is not the peak)",
      re.search(r"RiskPercent\s*\*\s*1\.50", AUD_C) is None)
check("the auditor does NOT read the deleted input",
      "SafetyMaxRiskPct" not in AUD_C)
if None not in (T1, T2, T3, T4):
    CEILING = max(T1, T2, T3, T4) * 1.50
    check("the derived ceiling brackets the peak single leg (1.5%% vs %.3f%%)"
          % max(T1, T2, T3, T4), max(T1, T2, T3, T4) < CEILING,
          "%s < %s" % (max(T1, T2, T3, T4), CEILING))
    # The specific regression this release had to fix: a T1-anchored ceiling.
    check("a T1-anchored ceiling would indeed have been breached by T2",
          T2 > T1 * 1.50, (T1 * 1.50, T2))

check("the new ladder is documented in the inputs, so it is not a silent edit",
      "2.25" in DEFS_T and "NON-MONOTONIC" in DEFS_T)
check("the retired geometric-cascade rationale is gone from the live inputs",
      not re.search(r"^// v5\.69: the ladder is a GEOMETRIC CASCADE", DEFS_T, re.M))
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
#    deleted input, and the peak-rung anchor keeps it at 1.5%.
# ----------------------------------------------------------------------
print("\n-- 4. The auditor tolerance is derived, never a literal --")

check("the auditor derives its ceiling at runtime, not from a literal",
      re.search(r"peakRungPct\s*\*\s*1\.50", AUD_C) is not None)
check("the auditor ceiling was NOT hard-coded to a literal percentage",
      re.search(r"maxAllowedRiskPct\s*=\s*[0-9]", AUD_C) is None)
# v5.69 deleted the whole drawdown layer from the auditor; only the per-leg
# risk check survives, which is what keeps this ceiling meaningful.
check("the auditor's drawdown machinery is gone",
      "AuditDrawdown" not in AUD_C or
      AUD_C.count("AuditDrawdown") == 1)   # one surviving tombstone comment
check("the auditor no longer latches a daily or total DD breach",
      "m_alertSent_DailyDDBreach" not in AUD_C.replace(
          "// v5.69: the drawdown latches (m_alertSent_DailyDDBreach,", ""))


# ----------------------------------------------------------------------
# 4b. The +1.0R rung LOCKS +0.75R instead of parking at cost-covering BE.
# ----------------------------------------------------------------------
print("\n-- 4b. The +1.0R rung locks +0.75R (friction kept as a floor) --")

LOCK = num_input(DEFS_C, "InpBEProfitLockRR")
check("InpBEProfitLockRR exists and is 0.75", LOCK == 0.75, LOCK)
check("the +1.0R trigger itself is untouched (InpBreakEvenRR still 1.0)",
      num_input(DEFS_C, "InpBreakEvenRR") == 1.0,
      num_input(DEFS_C, "InpBreakEvenRR"))

# The lock is applied on BOTH ladder branches AND on the T2 fill override, and
# each site multiplies the SHARED input by its own rrUnit -- a hard-coded 0.75
# would drift silently if the input moved. Three sites: LONG, SHORT, T2 fill.
N_LOCK = len(re.findall(r"InpBEProfitLockRR\s*\*\s*rrUnit", TRADE_C))
check("the lock is applied on both branches and the T2 fill override",
      N_LOCK == 3, N_LOCK)
check("the LONG branch keeps friction as a FLOOR via MathMax",
      re.search(r"beSL\s*=\s*MathMax\(\s*lockSL\s*,\s*frictionSL\s*\)", TRADE_C)
      is not None)
check("the SHORT branch keeps friction as a FLOOR via MathMin",
      re.search(r"beSL\s*=\s*MathMin\(\s*slLock\s*,\s*frictionSL\s*\)", TRADE_C)
      is not None)
# Cost-covering must still be reachable, or the v5.27 guarantee silently died.
check("CalcBasketFriction() is still consumed, so cost-covering did not go dead",
      len(re.findall(r"CalcBasketFriction\(", TRADE_C)) >= 3,
      len(re.findall(r"CalcBasketFriction\(", TRADE_C)))
# The old outer guard would SKIP the lock for a stop already between entry and
# +0.75R, leaving the basket under-locked. Only the forward-only test remains.
check("the retired 'desiredSL < primaryEntry' outer guard is gone",
      "desiredSL < primaryEntry)" not in TRADE_C and
      "desiredSL > primaryEntry)" not in TRADE_C)
check("the ratchet is guarded forward-only on the LONG branch",
      re.search(r"if\(desiredSL\s*<\s*beSL\)", TRADE_C) is not None)
check("the ratchet is guarded forward-only on the SHORT branch",
      re.search(r"if\(desiredSL\s*>\s*beSL\)", TRADE_C) is not None)

# T2 must be BORN wearing the lock, not the old friction-BE. A friction-BE
# override on the largest rung is the inversion v5.61 fixed for T3.
check("the T2 fill carries InpBEProfitLockRR as its slOverride",
      re.search(r"lockRaw\s*=[^\n]*InpBEProfitLockRR\s*\*\s*rrUnit", TRADE_C)
      is not None)
check("the T2 fill is clamped against the live session stop",
      re.search(r"groupSL\s*=\s*\(dir==DIR_LONG\)\s*\?\s*MathMax\(\s*lockRaw\s*,\s*sessionNow2\s*\)"
                r"[\s\S]{0,120}MathMin\(\s*lockRaw\s*,\s*sessionNow2\s*\)",
                TRADE_C) is not None)
check("the T2 group-stop log no longer advertises cost-covering breakeven",
      "Cost-Covering Breakeven" not in TRADE_C)
check("the T2 group-stop log names the +0.75R milestone",
      "+0.75R" in TRADE_C)

# The journal event that fires on the rung must describe what actually happened.
check("the journal reports a +0.75R profit lock, not a breakeven",
      "SL -> +0.75R PROFIT LOCK" in MAIN_T and
      "BREAKEVEN (COST-COVERING)" not in MAIN_T)


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
# v5.72 -- the formula is now picked from InpEntryStyle inside LogSetupArmed, so
# the MIDPOINT wording must live in the same method body.
check("the armed record explains the MIDPOINT formula the default build prints",
      "Midpoint entry: (top + bottom) / 2.0 - exact zone centre" in ARM and
      "InpEntryStyle == ENTRY_MIDPOINT" in ARM)
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
    if "2.75" in body or "1.375" in body or "1.875" in body:
        STALE.append(f)
check("no live code still asserts a retired ladder sum (2.75 / 1.875 / 1.375)",
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
    print("v5.70 NON-MONOTONIC RISK TIERS + +0.75R PROFIT LOCK - STATIC PROBE")
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
