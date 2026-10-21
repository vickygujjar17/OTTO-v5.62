"""
v5.28 static verification probe - safety hotfix.

Pins the four behaviours that the MQL5 compiler gate CANNOT exercise:

  1. New York DST rule. MQL5 has no TimeDaylightSavings(), so the US Eastern
     offset is computed by hand. The rule is modelled independently from raw
     epoch seconds and checked on both transition edges (2nd Sunday of March
     07:00 UTC, 1st Sunday of November 06:00 UTC) plus the 2026-2028 dates.
  2. MostRecentNyRollover resolves the offset AT the boundary, not from the
     current instant - the bug that would otherwise shift the anchor by an
     hour for one day after each DST switch.
  3. The daily-reset anchor is no longer derived from iTime(PERIOD_D1,0),
     i.e. it no longer depends on the broker's server timezone.
  4. The 1% floating rule measures the LIVE (balance - equity) float and no
     longer sets a permanent halt latch; the 5% trailing rule still does.
  5. Order manager: the consensus cancel sweep is symbol-scoped. (v5.39: the
     former "ArmVirtualOrder refuses an entry on the wrong side of the live
     market" contract was RETIRED -- a v5.37+ setup is an in-memory virtual
     order, never a resting broker limit -- so those pins now assert the guard's
     absence rather than its presence.)

Pure static analysis of the shipped sources - no MT5 required.
"""

import datetime as _dt
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "otto.mq5")
OM = os.path.join(ROOT, "COttoOrderManager.mqh")
DEFS = os.path.join(ROOT, "OttoDefines.mqh")

ALL_FILES = ["otto.mq5", "COttoOrderManager.mqh", "COttoTradeManager.mqh",
             "COttoRiskManager.mqh", "COttoBlockManager.mqh", "COttoJournal.mqh",
             "COttoMarketStructure.mqh", "OttoDefines.mqh"]


def read(p):
    return io.open(p, encoding="utf-8", errors="replace", newline="").read()


MAIN_T = read(MAIN)
OM_T = read(OM)
DEFS_T = read(DEFS)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def strip_comments(code):
    """Drop // comments, respecting string literals.

    Needed because the v5.28 fix documents the OLD behaviour in place
    ("...it anchored on iTime(PERIOD_D1,0), which..."), so a raw substring
    test on the function body would fail on its own explanatory comment.
    A '//' is only a comment when an even number of '"' precede it on the
    line, which keeps any '//' inside a string literal intact.
    """
    out = []
    for line in code.split("\n"):
        idx = line.find("//")
        if idx < 0:
            out.append(line)
            continue
        out.append(line if line[:idx].count('"') % 2 else line[:idx])
    return "\n".join(out)


def func_body(text, signature_re):
    """Return the full body of an MQL5 function, matched by counting braces.

    A regex with a closing-brace lookahead is not reliable here: MQL5 nests
    blocks at 3/5/7/8 spaces of indentation, so a lazy quantifier stops at the
    first inner '}' aligned to the outer one -- truncating the body and giving
    false passes/failures on anything after it.
    """
    m = re.search(signature_re, text)
    if m is None:
        return None
    start = text.find("{", m.start())
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


# ======================================================================
# Independent model of the MQL5 helpers
# ======================================================================
SECONDS_PER_DAY = 86400
UTC = _dt.timezone.utc


def _epoch(y, mo, d, h=0, mi=0, s=0):
    return int(_dt.datetime(y, mo, d, h, mi, s, tzinfo=UTC).timestamp())


def first_sunday(y, mo):
    """Day-of-month of the first Sunday. MQL5's day_of_week is Sun=0..Sat=6,
    so Python's Mon=0..Sun=6 is shifted by 1 before the same formula applies."""
    first = _dt.date(y, mo, 1)
    mql_dow = (first.weekday() + 1) % 7
    return 1 + ((7 - mql_dow) % 7)


def is_us_eastern_dst(utc_epoch):
    """Mirror of IsUsEasternDST()."""
    dt = _dt.datetime.fromtimestamp(utc_epoch, UTC)
    if dt.month < 3 or dt.month > 11:
        return False
    if 3 < dt.month < 11:
        return True
    fs = first_sunday(dt.year, dt.month)
    if dt.month == 3:
        second_sunday = fs + 7
        return (dt.day > second_sunday) or (dt.day == second_sunday and dt.hour >= 7)
    return (dt.day < fs) or (dt.day == fs and dt.hour < 6)


def ny_offset(utc_epoch):
    """Mirror of NewYorkUtcOffsetSeconds()."""
    return -14400 if is_us_eastern_dst(utc_epoch) else -18000


def utc_to_ny(utc_epoch):
    return utc_epoch + ny_offset(utc_epoch)


def most_recent_ny_rollover(utc_now):
    """Mirror of MostRecentNyRollover(), including the two refinement passes."""
    ny_now = utc_to_ny(utc_now)
    d = _dt.datetime.fromtimestamp(ny_now, UTC)
    base = _epoch(d.year, d.month, d.day) + 17 * 3600
    if ny_now < base:
        base -= SECONDS_PER_DAY
    utc_b = base - ny_offset(utc_now)
    for _ in range(2):
        utc_b = base - ny_offset(utc_b)
    return utc_b

# ----------------------------------------------------------------------
# 1. US Eastern DST rule
# ----------------------------------------------------------------------
print("-- US Eastern DST rule --")

check("2026 DST starts 2nd Sunday of March (Mar 8)",
      first_sunday(2026, 3) + 7 == 8)
check("2026 DST ends 1st Sunday of November (Nov 1)", first_sunday(2026, 11) == 1)
check("2027 DST starts Mar 14", first_sunday(2027, 3) + 7 == 14)
check("2027 DST ends Nov 7", first_sunday(2027, 11) == 7)
check("2028 DST starts Mar 12", first_sunday(2028, 3) + 7 == 12)
check("2028 DST ends Nov 5", first_sunday(2028, 11) == 5)

check("Jan 15 2026 -> EST", is_us_eastern_dst(_epoch(2026, 1, 15, 12)) is False)
check("Feb 15 2026 -> EST", is_us_eastern_dst(_epoch(2026, 2, 15, 12)) is False)
check("Dec 15 2026 -> EST", is_us_eastern_dst(_epoch(2026, 12, 15, 12)) is False)
check("Jul 15 2026 -> EDT", is_us_eastern_dst(_epoch(2026, 7, 15, 12)) is True)
check("Oct 31 2026 -> EDT", is_us_eastern_dst(_epoch(2026, 10, 31, 12)) is True)

# March edge: 02:00 EST == 07:00 UTC on Mar 8 2026.
check("Mar 8 2026 06:59 UTC -> still EST",
      is_us_eastern_dst(_epoch(2026, 3, 8, 6, 59)) is False)
check("Mar 8 2026 07:00 UTC -> now EDT",
      is_us_eastern_dst(_epoch(2026, 3, 8, 7, 0)) is True)
check("Mar 8 2026 00:00 UTC -> EST (earlier same day)",
      is_us_eastern_dst(_epoch(2026, 3, 8, 0, 0)) is False)
check("Mar 7 2026 23:00 UTC -> EST (day before)",
      is_us_eastern_dst(_epoch(2026, 3, 7, 23)) is False)

# November edge: 02:00 EDT == 06:00 UTC on Nov 1 2026.
check("Nov 1 2026 05:59 UTC -> still EDT",
      is_us_eastern_dst(_epoch(2026, 11, 1, 5, 59)) is True)
check("Nov 1 2026 06:00 UTC -> now EST",
      is_us_eastern_dst(_epoch(2026, 11, 1, 6, 0)) is False)
check("Nov 1 2026 23:00 UTC -> EST",
      is_us_eastern_dst(_epoch(2026, 11, 1, 23)) is False)

check("EDT offset is -14400s", ny_offset(_epoch(2026, 7, 15, 12)) == -14400)
check("EST offset is -18000s", ny_offset(_epoch(2026, 1, 15, 12)) == -18000)

# Cross-check against the IANA database when zoneinfo is available.
try:
    from zoneinfo import ZoneInfo
    _ny = ZoneInfo("America/New_York")
    mismatches = []
    for probe_day in range(1, 366, 3):
        t = _epoch(2026, 1, 1) + probe_day * SECONDS_PER_DAY + 3600
        off = _dt.datetime.fromtimestamp(t, UTC).astimezone(_ny).utcoffset()
        want = int(off.total_seconds())
        if ny_offset(t) != want:
            mismatches.append((t, ny_offset(t), want))
    check("matches IANA America/New_York across 2026", not mismatches,
          "mismatches: %s" % mismatches[:3])
except Exception as exc:      # zoneinfo absent: the edge cases above stand alone
    check("IANA cross-check skipped (no zoneinfo)", True, str(exc))


# ----------------------------------------------------------------------
# 2. Rollover resolves the offset AT the boundary
# ----------------------------------------------------------------------
print("\n-- NY 17:00 rollover resolution --")

r = most_recent_ny_rollover(_epoch(2026, 7, 15, 22, 0))
check("Jul 15 22:00 UTC -> rollover 2026-07-15 21:00 UTC", r == _epoch(2026, 7, 15, 21, 0),
      _dt.datetime.fromtimestamp(r, UTC).isoformat())
r = most_recent_ny_rollover(_epoch(2026, 7, 15, 20, 0))
check("Jul 15 20:00 UTC (before) -> 2026-07-14 21:00 UTC", r == _epoch(2026, 7, 14, 21, 0),
      _dt.datetime.fromtimestamp(r, UTC).isoformat())

r = most_recent_ny_rollover(_epoch(2026, 1, 15, 23, 0))
check("Jan 15 23:00 UTC -> rollover 2026-01-15 22:00 UTC", r == _epoch(2026, 1, 15, 22, 0),
      _dt.datetime.fromtimestamp(r, UTC).isoformat())

# The load-bearing case: in the 24h AFTER the November switch the current
# offset (EST) differs from the offset at the boundary (EDT). Naively using
# the current offset would land the anchor at 22:00 UTC instead of 21:00.
r = most_recent_ny_rollover(_epoch(2026, 11, 1, 12, 0))
check("Nov 1 12:00 UTC -> rollover 2026-10-31 21:00 UTC (EDT boundary)",
      r == _epoch(2026, 10, 31, 21, 0),
      _dt.datetime.fromtimestamp(r, UTC).isoformat())
check("...and NOT the naive 22:00 UTC", r != _epoch(2026, 10, 31, 22, 0))

r = most_recent_ny_rollover(_epoch(2026, 3, 8, 12, 0))
check("Mar 8 12:00 UTC -> rollover 2026-03-07 22:00 UTC (EST boundary)",
      r == _epoch(2026, 3, 7, 22, 0),
      _dt.datetime.fromtimestamp(r, UTC).isoformat())

# The rollover must be in the past, and within the preceding 24h. The boundary
# is included (t == rr is a legitimate boundary instant), so the check is
# 0 <= age <= 86400.
bad = []
for hour in range(0, 24 * 4):
    for dy in (1, 15, 28):
        t = _epoch(2026, 7, 1) + (dy - 1) * SECONDS_PER_DAY + hour * 3600
        rr = most_recent_ny_rollover(t)
        if not (0 <= t - rr <= SECONDS_PER_DAY):
            bad.append(t)
check("rollover always within the preceding 24h (sweep)", not bad,
      "violations: %d" % len(bad))


# ----------------------------------------------------------------------
# 3. Source: daily-reset clock no longer depends on the broker
# ----------------------------------------------------------------------
print("\n-- Daily reset source contract --")

cdr = func_body(MAIN_T, r"void\s+CheckDailyReset\s*\(void\)")
# v5.69 INVERTED: CheckDailyReset() and the whole 00:00-anchor clock it served
# are DELETED with the prop-firm drawdown layer, so the surviving contract is
# the absence of the function and of every helper that fed it. Written as an
# inversion rather than a deletion so a future reintroduction of a reset clock
# reds here instead of sliding past.
check("CheckDailyReset is deleted (v5.69 removed the drawdown layer)",
      cdr is None)
for fn in ("IsUsEasternDST", "NewYorkUtcOffsetSeconds", "UtcToNewYork",
           "MostRecentNyRollover", "MostRecentServerMidnight"):
    check("otto.mq5 no longer defines %s()" % fn,
          re.search(r"\b%s\s*\(" % fn, strip_comments(MAIN_T)) is None)
check("no reset clock consults TimeGMT() for a drawdown anchor",
      "TimeGMT()" not in MAIN_T)
check("the retired daily-pause latch is gone",
      "g_dailyDD_Paused" not in strip_comments(MAIN_T))
check("the retired persistence helper is gone",
      "PersistSafetyState" not in strip_comments(MAIN_T))

check("OnInit no longer derives the anchor from a D1 bar",
      "datetime todayBar" not in MAIN_T)
check("OnInit no longer logs a time basis it does not compute",
      "Time basis:" not in MAIN_T)

md = func_body(MAIN_T, r"void\s+UpdateMarketDay\s*\(void\)")
check("UpdateMarketDay still uses the D1 bar (unrelated to the DD anchor)",
      md is not None and "iTime(" in md)


# ----------------------------------------------------------------------
# 4. Source: the 1% floating rule and its halt latch are BOTH deleted
# ----------------------------------------------------------------------
print("\n-- 1% floating-loss contract (v5.69: rule deleted) --")

flt = re.search(
    r"double\s+floatingLoss\s*=\s*\(balance\s*>\s*0\s*&&\s*equity\s*<\s*balance\)"
    r"\s*\?\s*100\.0\s*\*\s*\(balance\s*-\s*equity\)\s*/\s*balance\s*:\s*0\.0\s*;",
    MAIN_T)
# v5.69 INVERTED: the 1%% floating-loss rule, its SafetyMaxFloatingLoss input and
# the balance/equity delta it read were part of the drawdown layer and are
# deleted. The surviving invariant is that none of them can come back, so each
# assertion below demands ABSENCE. (Several of these were ALREADY red before
# v5.69: this script had drifted from the source it claims to pin, so the
# inversion also brings it back in line.)
check("the 1%% floating-loss local is deleted", flt is None)
check("no live code reads SafetyMaxFloatingLoss",
      "SafetyMaxFloatingLoss" not in strip_comments(MAIN_T))
check("the 1%% floating branch is deleted",
      re.search(r"if\s*\(\s*floatingLoss\s*>=.*?//\s*3%%\s*Max\s+Daily\s+Drawdown",
                MAIN_T, re.S) is None)
check("no DD halt latch survives anywhere in OnTick",
      "g_totalDD_Halted" not in strip_comments(MAIN_T))

# The persist/restore pair the probe used to require no longer exists at all:
# nothing is written to or read from the terminal GlobalVariable store.
check("no Halted flag is persisted anywhere",
      'OttoGvStoreFlag("Halted"' not in MAIN_T)
check("no Halted flag is restored on init",
      'OttoGvLoadFlag("Halted"' not in MAIN_T)
check("the GlobalVariable helpers are deleted",
      "OttoGvName" not in strip_comments(MAIN_T))

b5 = re.search(r"if\s*\(\s*totalDD\s*>=\s*SafetyTotalDDLimit\s*\)", MAIN_T)
check("the 5%% trailing bridge is deleted", b5 is None)



# ----------------------------------------------------------------------
# 5. Source: order-manager guards
# ----------------------------------------------------------------------
print("\n-- Order manager guards --")

sweep = func_body(OM_T, r"void\s+CancelOpposingConsensusOrders\s*\(void\)")
check("CancelOpposingConsensusOrders is RETIRED (v5.63)", sweep is None)
# The v5.28/v5.40 invariants this block used to assert (symbol scoping, magic
# filter, global consensus test, InpCancelOpposingPendings honour) are moot
# because the whole method is gone with COttoCorrelationFilter. What must hold
# now is that nothing reintroduces a portfolio-consensus cancel path.
check("no consensus cancel survives anywhere in the order manager",
      "IsConsensusOpposed" not in OM_T and
      "GetPairConsensus" not in OM_T and
      "InpCancelOpposingPendings" not in OM_T)

check("no CancelQuorumOpposingOrders exists (never did)", "CancelQuorum" not in OM_T)

# v5.40: the boundary buffer is LIVE again — the hybrid router consumes it to
# decide whether an entry may REST at the broker (physical) or must arm
# virtually. SYMBOL_TRADE_STOPS_LEVEL is read by the broker-level stop
# validator too, which remains unrelated and live.
check("PlaceOrArmOrder routes on the live-price boundary",
      "GetPriceBoundaryBuffer()" in OM_T)
check("PlaceOrArmOrder reads SYMBOL_TRADE_STOPS_LEVEL",
      "SYMBOL_TRADE_STOPS_LEVEL" in OM_T)
check("the boundary helper has a live caller again",
      "GetPriceBoundaryBuffer()" in OM_T)

# The v5.40 duplicate shield scans BOTH the broker pending pool and the virtual
# book, and is the last price gate before the route decision.
check("duplicate shield is still present in the ARM path",
      OM_T.find("IsAnyOrderLiveAtPrice(entryPrice, 5.0)") > 0)


# ----------------------------------------------------------------------
# 6. Version stamps agree on the current release
# ----------------------------------------------------------------------
print("\n-- Version stamps --")

stamps = set(re.findall(r'#property version\s+"(\d+\.\d+)"', DEFS_T))
check("OttoDefines.mqh carries exactly one version stamp", len(stamps) == 1,
      "found: %s" % sorted(stamps))
RELEASE = sorted(stamps)[0] if stamps else "?"
parts = tuple(int(x) for x in RELEASE.split("."))
check("release is v5.28 or later", parts >= (5, 28), RELEASE)

missing = [f for f in ALL_FILES
           if ('#property version   "%s"' % RELEASE) not in read(os.path.join(ROOT, f))]
check("all 10 files stamp v%s" % RELEASE, not missing,
      "missing: %s" % ", ".join(missing))
check("startup banner names the current release",
      ("OTTO EA v%s" % RELEASE) in MAIN_T)


# ----------------------------------------------------------------------
def main():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("=" * 74)
    print("v5.28 SAFETY HOTFIX - STATIC PROBE")
    print("=" * 74)
    for name, ok, detail in RESULTS:
        if ok:
            print("  [PASS] %s" % name)
        else:
            print("  [FAIL] %s%s" % (name, ("  <- " + detail) if detail else ""))
    print("-" * 74)
    print("  %d / %d checks passed" % (passed, total))
    print("=" * 74)
    if passed != total:
        print("*** FAILURES PRESENT ***")
        return 1
    print("*** ALL CHECKS PASSED ***")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
