"""
v5.69 static verification probe - PROP-FIRM DRAWDOWN LAYER ABSENCE GUARD.

v5.69 deletes an entire subsystem: the daily-drawdown pause, the trailing
total-drawdown halt, the 00:00 server-time reset clock, the MT5 GlobalVariable
persistence layer that carried those baselines across a VPS restart, the three
prop-firm inputs, and the auditor's mirror of all of it. Sizing is now pure
equity-based -- RiskPercent% of live equity at order time, with no drawdown
circuit breaker anywhere.

WHY A DEDICATED PROBE. Every other v5.69 probe asserts what the tree now DOES
(the ladder is a geometric cascade; the auditor derives its ceiling from
RiskPercent). This one asserts what the tree must no longer CONTAIN, and that
is a different failure mode: a deletion is only as good as its completeness.
The compiler catches a straggler REFERENCE to a removed symbol, but it cannot
see

  * a re-added `input double SafetyDailyDDLimit = 3.0;` that nothing reads
    (compiles clean, silently re-advertises a limit that is not enforced),
  * a dead helper re-introduced under a new name and never called,
  * the GlobalVariable namespace being re-opened by some other module that
    decides to "remember" state across a restart,
  * a docstring or journal row that keeps promising a halt the EA cannot
    perform, which is worse than the halt itself being gone because the
    operator reads the journal as ground truth.

So this probe pins ABSENCE, tree-wide, on comment-stripped source, and pins the
replacement contract (no drawdown state gates placement; the journal stops
advertising one).

WHAT IT CANNOT PROVE. That the EA behaves well under a 5% drawdown -- that is a
design decision, not an invariant. This is static analysis of the shipped
sources; no MT5 required.
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

    Load-bearing: v5.69's own tombstones name every deleted symbol in place
    ("g_totalDD_Halted", "OttoGvName", ...). A raw substring scan would report
    the tombstone itself as a straggler, which would push a future maintainer
    to delete the documentation to get a green probe.
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
AUD_C = LIVE["CHighTableAuditor.mqh"]
JRN_T = SRC["COttoJournal.mqh"]


# ----------------------------------------------------------------------
# 1. The three prop-firm inputs are gone, not merely unused.
# ----------------------------------------------------------------------
print("\n-- 1. Prop-firm inputs deleted --")

for name in ("SafetyMaxRiskPct", "SafetyDailyDDLimit", "SafetyTotalDDLimit"):
    decl = re.search(r"^\s*input\s+double\s+" + name + r"\b", DEFS_C, re.M)
    check("%s is not declared as an input" % name, decl is None)
    alias = re.search(r"^\s*const\s+double\s+" + name + r"\b", DEFS_C, re.M)
    check("%s is not re-declared as a const either" % name, alias is None)

check("the group [8] header is deleted",
      "PROP FIRM SAFETY BUFFERS" not in DEFS_C)
check("no shipped source still READS a prop-firm limit",
      not any(n in "".join(LIVE.values()) for n in
              ("SafetyMaxRiskPct", "SafetyDailyDDLimit", "SafetyTotalDDLimit")))


# ----------------------------------------------------------------------
# 2. Every drawdown state symbol is gone from live code.
# ----------------------------------------------------------------------
print("\n-- 2. Drawdown state is gone tree-wide --")

DD_SYMBOLS = [
    "g_initialBalance",
    "g_dailyResetBalance",
    "g_equityHighWaterMark",
    "g_lastMidnightCheck",
    "g_dailyDD_Paused",
    "g_totalDD_Halted",
    "g_dailyDD_ResumeTime",
]

for sym in DD_SYMBOLS:
    hits = [f for f, body in LIVE.items() if sym in body]
    check("%s appears in no live code" % sym, not hits, hits)

DD_FUNCS = [
    "OttoGvName", "OttoGvLoadDouble", "OttoGvLoadFlag", "OttoGvStore",
    "OttoGvStoreFlag", "PersistSafetyState", "MostRecentServerMidnight",
    "CheckDailyReset", "MostRecentNyRollover",
]

for fn in DD_FUNCS:
    # A definition OR a call is a failure; the broad `name(` shape catches both.
    hits = [f for f, body in LIVE.items()
            if re.search(r"\b" + fn + r"\s*\(", body) is not None]
    check("%s is neither defined nor called" % fn, not hits, hits)


# ----------------------------------------------------------------------
# 3. The auditor no longer mirrors or enforces a drawdown.
# ----------------------------------------------------------------------
print("\n-- 3. Auditor drawdown mirror deleted --")

for sym in ("m_dailyResetBalance", "m_equityHwm", "m_totalHalted",
            "m_haveBaseline", "m_alertSent_DailyDDBreach",
            "m_alertSent_TotalDDBreach", "m_alertSent_Halt",
            "DailyDDPct", "TotalDDPct", "SetSafetyBaseline"):
    check("the auditor no longer names %s" % sym, sym not in AUD_C)

# AuditDrawdown() must not be CALLED. The name survives once, in the tombstone
# that explains its removal, so the check is on the call shape.
check("RunAudit no longer drives AuditDrawdown()",
      re.search(r"AuditDrawdown\s*\(\s*\)\s*;", AUD_C) is None)
check("AuditDrawdown is no longer DEFINED",
      re.search(r"void\s+AuditDrawdown\s*\(", AUD_C) is None)

# The per-leg risk audit is NOT part of the drawdown layer and must survive --
# it is the only thing left that can catch a runaway position size.
check("AuditRiskExposure survives the purge",
      re.search(r"void\s+AuditRiskExposure\s*\(", AUD_C) is not None)
check("the per-leg ceiling is still derived from RiskPercent",
      re.search(r"RiskPercent\s*\*\s*1\.50", AUD_C) is not None)


# ----------------------------------------------------------------------
# 4. Nothing gates the trade loop on drawdown state.
# ----------------------------------------------------------------------
print("\n-- 4. Placement is ungated --")

check("OnTick never early-returns on a halt",
      re.search(r"if\s*\(\s*g_totalDD_Halted\s*\)\s*return", MAIN_C) is None)
check("OnTick never calls a reset clock", "CheckDailyReset" not in MAIN_C)
check("placement is not wrapped in a pause guard",
      "if(!g_dailyDD_Paused)" not in MAIN_C)
check("placement is still invoked", "PlaceOrdersForArmedBlocks()" in MAIN_C)

# The terminal's GlobalVariable store must no longer hold any DRAWDOWN state:
# persisting a baseline across a restart was the whole point of the deleted
# layer, and re-adding a key for it would resurrect the same bug. Scoped to the
# five keys the shadow store actually wrote -- COttoOrderManager legitimately
# uses the GV store for a DIFFERENT concern (open-basket crash recovery and the
# cross-chart virtual arm locks), and that subsystem is out of scope here.
SAFETY_KEYS = ["DailyReset", "HighWater", "LastMid", "Paused", "Halted"]

for key in SAFETY_KEYS:
    hits = [f for f, body in LIVE.items()
            if re.search(r'GlobalVariableSet\s*\([^)]*"' + key + r'"', body)]
    check("no module persists a %r safety key" % key, not hits, hits)

# The safety store was namespaced "OTTO_<key>_<accountLogin>". Assert that
# LOGIN-SUFFIXED shape is gone specifically: a bare "OTTO_" prefix is still used
# by COttoOrderManager for its own basket keys (namespaced by symbol + magic),
# and that namespace is legitimate and unrelated.
check("no trade-independent OTTO_<key>_<login> key builder survives",
      not any(re.search(r'"OTTO_"[\s\S]{0,80}ACCOUNT_LOGIN', body)
              for body in LIVE.values()))
check("the auditor CSV is the only Otto_ file the EA writes for audit",
      "Otto_HighTable_Audit.csv" in SRC["CHighTableAuditor.mqh"])


# ----------------------------------------------------------------------
# 5. No shipped text still advertises a halt the EA cannot perform.
# ----------------------------------------------------------------------
print("\n-- 5. Journal and README stop promising a halt --")

PROMISES = [
    (r"\bDD halt\b", "an 'DD halt'"),
    (r"\bdrawdown limit\b", "a 'drawdown limit'"),
    (r"\btrailing drawdown\b", "a 'trailing drawdown'"),
    (r"\bdaily drawdown\b", "a 'daily drawdown'"),
]

for pat, label in PROMISES:
    # The journal is checked strictly: the operator reads those rows per trade
    # as ground truth about what the EA will do. otto.mq5 / OttoDefines.mqh /
    # CHighTableAuditor.mqh are allowed to DISCUSS the removal in tombstones,
    # which is why the scan is scoped to the journal rather than file-wide.
    check("the journal does not advertise %s" % label,
          re.search(pat, JRN_T, re.I) is None, 
          "found in COttoJournal.mqh")

check("the journal still describes the real basket machinery",
      "close all now apply" in JRN_T)
check("the risk-allocation row is no longer tagged to a dead baseline",
      "v5.68 baseline" not in JRN_T)
check("the risk-allocation row is tagged equity-based",
      "(equity-based)" in JRN_T)

# The init banner must not print a budget it no longer enforces.
check("the startup banner prints no DD budget",
      "DailyDD" not in MAIN_C and "TotalDD" not in MAIN_C)
check("the startup banner still prints the live ladder",
      "Ladder: T1 " in MAIN_C)

# README is the operator-facing contract, so a stale claim there matters.
README = read(os.path.join(ROOT, "README.md"))
check("README no longer promises a prop-firm safety buffer",
      "PROP FIRM SAFETY BUFFERS" not in README)
check("README no longer documents SafetyMaxRiskPct as a live input",
      re.search(r"SafetyMaxRiskPct\s*\|", README) is None)
check("README documents the tearsheet's replacement ladder",
      "1.875" in README)


def main():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("=" * 74)
    print("v5.69 PROP-FIRM DRAWDOWN LAYER - ABSENCE GUARD")
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

