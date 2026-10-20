"""
v5.64 static verification probe - NEAR-EDGE PULLBACK entry geometry + guard.

v5.64 widens the anticipation entry from 0.5*ATR to 1.0*ATR past the far edge
the breakout crosses, DECOUPLES that offset from the stop distance, and adds a
price-crossing guard so a setup the market has already run through is refused
instead of chased. Four properties carry that change and none is visible to
the MQL5 compiler:

  1. TWO INDEPENDENT COEFFICIENTS. The entry offset is blockHeight + 1.0*ATR
     (measured from the NEAR edge, which collapses to exactly 1.0*ATR past the
     FAR edge). slDist is UNCHANGED at blockHeight + 0.5*ATR. Under v5.57 the
     entry offset WAS slDist, so one edit to either coefficient silently moved
     both. They are now separate numbers and must stay separate: the risk
     distance feeds every lot size, every 1R trail milestone and every basket
     seed.

  2. THE STOP MOVES WITH THE ENTRY. stop = entry -/+ slDist, so with the
     offset widened the stop now lands 0.5*ATR INSIDE the zone whenever
     ATR < 2*blockHeight (it sat exactly ON the near edge in v5.57). That is
     the accepted consequence of clause 1, pinned numerically in section 3 so
     it cannot drift in either direction.

  3. THE CROSSING GUARD. IsEntryCrossed() is the EXACT NEGATION of the virtual
     trigger test, evaluated at ARM time -- the only place the distinction
     between "waiting for the cross" and "the cross already happened" still
     exists. It must reject BEFORE the router (so a crossed setup cannot become
     a chasing rest-limit either) and must LATCH hasPlacedOrder (the setup is
     spent, not deferred, so the per-tick arming pass must not retest it).
     It must SKIP ENTRY_MIDPOINT, whose entry sits behind the market by
     construction and would otherwise be retired wholesale.

  4. TWIN IDENTITY. CalcEntryPrice() (OrderManager) and BlockEntryPrice()
     (BlockManager) must judge one price. They are dormant -- the Front-Run
     veto that last read the pair is retired -- which makes a divergence
     completely silent, so the identity is asserted rather than assumed.

Pure static analysis of the shipped sources - no MT5 required.
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "otto.mq5")
OM = os.path.join(ROOT, "COttoOrderManager.mqh")
BM = os.path.join(ROOT, "COttoBlockManager.mqh")
JRN = os.path.join(ROOT, "COttoJournal.mqh")
DEFS = os.path.join(ROOT, "OttoDefines.mqh")

ALL_FILES = ["otto.mq5", "COttoOrderManager.mqh", "COttoTradeManager.mqh",
             "COttoRiskManager.mqh", "COttoBlockManager.mqh", "COttoJournal.mqh",
             "CHighTableAuditor.mqh",
             "COttoMarketStructure.mqh",
             "OttoDefines.mqh"]


def read(p):
    return io.open(p, encoding="utf-8", errors="replace",
                   newline="").read().replace("\r\n", "\n")


def strip_comments(code):
    """Drop // comments, respecting string literals.

    Load-bearing here: v5.64 documents the RETIRED v5.57 collapse in place
    ("the SL landed exactly ON the near edge"), so a raw substring test would
    fire on this file's own subject matter.
    """
    out = []
    for line in code.split("\n"):
        idx = line.find("//")
        if idx < 0:
            out.append(line)
            continue
        out.append(line if line[:idx].count('"') % 2 else line[:idx])
    return "\n".join(out)


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def body(src, marker):
    """Brace-matched body of the function whose header contains `marker`."""
    i = src.find(marker)
    if i < 0:
        return None
    j = src.find("{", i)
    if j < 0:
        return None
    depth = 0
    k = j
    n = len(src)
    while k < n:
        c = src[k]
        if c == '"':
            k += 1
            while k < n and src[k] != '"':
                k += 2 if src[k] == "\\" else 1
        elif c == "'":
            k += 1
            while k < n and src[k] != "'":
                k += 2 if src[k] == "\\" else 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
        k += 1
    return src[j:]


def canon(fragment, var):
    """Blank the twin-specific identifiers so the two verify as one."""
    s = fragment
    s = s.replace(var + ".", "")
    s = s.replace("GetDirectionForBlock(block)", "Dir(x)")
    s = s.replace("BlockDirection(b)", "Dir(x)")
    return norm(s)


def canon_body(fn, var):
    raw = fn or ""
    brace = raw.find("{")
    return canon(raw[brace:] if brace >= 0 else raw, var)


RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


OM_RAW = read(OM)
BM_RAW = read(BM)
JRN_RAW = read(JRN)
MAIN_T = read(MAIN)
DEFS_T = read(DEFS)
OM_C = strip_comments(OM_RAW)
BM_C = strip_comments(BM_RAW)

OM_PLACE = body(OM_C, "PlaceOrArmOrder(int blockIndex")
OM_CALC = body(OM_C, "CalcEntryPrice(const SSniperBlock &block, double atr)")
OM_SLD = body(OM_C, "CalcSLDistance(const SSniperBlock &block, double atr)")
OM_GUARD = body(OM_C, "IsEntryCrossed(const SSniperBlock &block, double entryPrice)")
OM_VIRT = body(OM_C, "CheckVirtualTriggers(void)")
OM_REV = body(OM_C, "OpenReversalPosition(SSniperBlock &targetBlock)")
OM_ORDTYPE = body(OM_C, "GetOrderTypeForBlock(const SSniperBlock &block)")
BM_BEP = body(BM_C, "BlockEntryPrice(const SSniperBlock &b, double atr) const")


# ----------------------------------------------------------------------
# 1. The two coefficients are independent
# ----------------------------------------------------------------------
print("\n-- 1. Entry offset vs stop distance --")

check("CalcEntryPrice located", OM_CALC is not None)
check("BlockEntryPrice located", BM_BEP is not None)
check("CalcSLDistance located", OM_SLD is not None)

check("the entry offset is blockHeight + 1.0*ATR",
      "double pullback = block.blockHeight + (1.0 * atr);" in (OM_CALC or ""),
      OM_CALC)
check("the BlockManager twin uses the SAME offset expression",
      "double pullback = b.blockHeight + (1.0 * atr);" in (BM_BEP or ""),
      BM_BEP)
check("the entry is anchored on the NEAR edge (bottom LONG / top SHORT)",
      "block.bottom + pullback" in (OM_CALC or "") and
      "block.top - pullback" in (OM_CALC or ""))
check("the entry no longer reuses slDist as its offset",
      "slDist" not in (OM_CALC or "") and "slDist" not in (BM_BEP or ""),
      "an entry that reads slDist re-couples the two coefficients")

check("CalcSLDistance is untouched at blockHeight + 0.5*ATR",
      norm(OM_SLD or "") == "{\n      return block.blockHeight + (0.5 * atr);\n     }"
      or re.search(r"return\s+block\.blockHeight\s*\+\s*\(0\.5\s*\*\s*atr\)\s*;",
                   OM_SLD or "") is not None,
      OM_SLD)
check("the stop distance is NOT widened to match the entry offset",
      "(1.0 * atr)" not in (OM_SLD or ""))
check("the twins are arithmetically identical",
      canon_body(BM_BEP, "b") == canon_body(OM_CALC, "block"),
      "BM=%s || OM=%s" % (canon_body(BM_BEP, "b")[:70],
                          canon_body(OM_CALC, "block")[:70]))
check("both twins still honour ENTRY_MIDPOINT first",
      "if(InpEntryStyle == ENTRY_MIDPOINT) return midpoint;" in
      canon_body(BM_BEP, "b") and
      "if(InpEntryStyle == ENTRY_MIDPOINT) return midpoint;" in
      canon_body(OM_CALC, "block"))

# The stop must be built from the entry and slDist, never from an edge.
check("the stop is still entry +/- slDist",
      "isLong ? entryPrice - slDist : entryPrice + slDist;" in (OM_PLACE or ""))
check("rrUnit is still seeded from slDist (the 1R basis is unchanged)",
      "rrUnit = slDist;" in norm(OM_PLACE or ""))


# ----------------------------------------------------------------------
# 2. The crossing guard exists, is wired, and latches
# ----------------------------------------------------------------------
print("\n-- 2. Crossing guard --")

check("IsEntryCrossed located", OM_GUARD is not None)
check("the guard reads the same side the trigger fires on (ask LONG / bid SHORT)",
      "return isLong ? (GetAsk() >= entryPrice) : (GetBid() <= entryPrice);" in
      (OM_GUARD or ""), OM_GUARD)
check("the guard is the EXACT NEGATION of the virtual trigger test",
      "isLong ? (ask < vo.triggerPrice) : (bid > vo.triggerPrice)" in (OM_VIRT or ""))
check("the guard treats missing geometry as crossed (nothing to wait for)",
      "if(entryPrice <= 0.0) return true;" in (OM_GUARD or ""))

PLACE_W = norm(OM_PLACE or "")
check("the guard is called from PlaceOrArmOrder",
      "IsEntryCrossed(block, entryPrice)" in PLACE_W)
check("the guard is scoped to the cross-trigger style, not MIDPOINT",
      "InpEntryStyle != ENTRY_MIDPOINT && IsEntryCrossed(block, entryPrice)"
      in PLACE_W,
      "an unscoped guard would retire every midpoint setup")
check("the guard runs BEFORE the router decides physical vs virtual",
      OM_PLACE is not None and
      0 <= OM_PLACE.find("IsEntryCrossed(block, entryPrice)")
           < OM_PLACE.find("GetPriceBoundaryBuffer()"),
      "a crossed setup must not be able to reach ROUTE A as a chasing limit")
check("a crossed setup LATCHES hasPlacedOrder (spent, not deferred)",
      re.search(r"IsEntryCrossed\(block, entryPrice\)\)\s*\{\s*block\.hasPlacedOrder\s*=\s*true;",
                OM_PLACE or "") is not None)
check("a crossed setup persists the latch to the block book",
      re.search(r"IsEntryCrossed\(block, entryPrice\)\)\s*\{\s*block\.hasPlacedOrder\s*=\s*true;\s*"
                r"m_blockManager\.SetBlockAt\(blockIndex, block\);", OM_PLACE or "") is not None)
check("a crossed setup is logged with its own reason, not as a duplicate",
      "ENTRY ALREADY CROSSED" in (OM_PLACE or ""))
check("the guard does NOT veto the block (it is spent, not invalid)",
      "isVetoed" not in (OM_GUARD or ""))

# The reversal path never prices off CalcEntryPrice, so the guard must NOT be
# applied there -- it would be true on every call and retire the SAR flip.
check("the SAR reversal path is documented as guard-exempt",
      "IsEntryCrossed" not in norm(OM_REV or "") and
      "the crossing guard is deliberately NOT applied here" in OM_RAW)


# ----------------------------------------------------------------------
# 3. The geometry, asserted numerically (the v5.64 table)
# ----------------------------------------------------------------------
print("\n-- 3. Geometry table --")


def realized(bh, atr, rr):
    """Transcribe the shipped geometry with the near edge at 0.0.

    LONG is the whole story: DIR_SHORT is the mirror image. nearEdge=0,
    farEdge=bh, entry = nearEdge + (bh + 1.0*atr), stop = entry - slDist,
    tp = farEdge + InpMaxRR*slDist (the journal's far-edge-anchored row).
    """
    sl = bh + 0.5 * atr
    entry = bh + 1.0 * atr
    return (entry, entry - sl, bh + rr * sl, sl)


CASES = [(1.0, 2.0, 4.0), (2.0, 1.0, 4.0), (1.0, 1.0, 2.0), (0.5, 4.0, 4.0)]
risk_ok = anchor_ok = True
for bh, atr, rr in CASES:
    entry, stop, tp, sl = realized(bh, atr, rr)
    if abs(abs(entry - stop) - sl) > 1e-12:
        risk_ok = False                 # the risk distance must never drift
    if abs((tp - entry) - (rr - atr / sl) * sl) > 1e-12:
        anchor_ok = False               # the far-edge identity

check("entry<->stop is exactly slDist in every case", risk_ok)
check("reward from the ENTRY == (InpMaxRR - ATR/slDist) * slDist", anchor_ok)

# The published table. bh/ATR are the zone height and the ATR; entry and stop
# are absolute prices with the near edge at 0.0 and the far edge at bh. A change
# to EITHER coefficient moves a row, so this pins both at once.
TABLE = [
    # bh,  atr, entry,  stop,  where the stop lands
    (1.0, 2.0,  3.00,  1.00,  "far"),       # ATR == 2*bh  -> stop ON the far edge
    (2.0, 1.0,  3.00,  0.50,  "inside"),    # ATR <  2*bh  -> stop INSIDE the zone
    (1.0, 1.0,  2.00,  0.50,  "inside"),
    (0.5, 4.0,  4.50,  2.00,  "outside"),   # ATR >  2*bh  -> stop beyond the zone
]
for bh, atr, want_entry, want_stop, where in TABLE:
    entry, stop, tp, sl = realized(bh, atr, 4.0)
    lands = ("far" if abs(stop - bh) < 1e-12 else
             "inside" if 0.0 < stop < bh else
             "outside" if stop > bh else "near")
    check("bh=%.1f ATR=%.1f -> entry=%.2f stop=%+.2f (%s)" %
          (bh, atr, want_entry, want_stop, where),
          abs(entry - want_entry) < 1e-12 and abs(stop - want_stop) < 1e-12
          and lands == where,
          "got entry=%.4f stop=%+.4f lands=%s" % (entry, stop, lands))

# The invariant v5.57 relied on is GONE, on purpose: the stop is no longer on
# the near edge. Pinned so a "cleanup" cannot quietly restore it and re-couple
# the entry offset to slDist.
entry, stop, tp, sl = realized(1.0, 2.0, 4.0)
check("the stop is no longer pinned to the near edge (v5.57 invariant retired)",
      abs(stop) > 1e-12, "stop=%.4f" % stop)
check("a 1.0-high zone at ATR 2.0 puts the stop exactly on the FAR edge",
      abs(stop - 1.0) < 1e-12)
check("the documented 1.0-high / ATR 2.0 zone realizes 3.0R",
      abs((tp - entry) / abs(entry - stop) - 3.0) < 1e-12)
check("realized R is strictly below InpMaxRR (entry-anchored, far-edge target)",
      (tp - entry) / abs(entry - stop) < 4.0)


# ----------------------------------------------------------------------
# 4. Documentation matches the shipped arithmetic
# ----------------------------------------------------------------------
print("\n-- 4. Documentation --")

check("the entry twins' rationale survives in BOTH files",
      "identical character for character" in norm(BM_RAW) and
      "identical character for character" in norm(OM_RAW))
check("the retired v5.57 collapse is marked RETIRED in the BlockManager",
      "RETIRED (v5.64)" in BM_RAW)
check("the stop-inside-zone consequence is documented at the SL definition",
      "0.5*ATR INSIDE the zone" in norm(OM_RAW))
check("the enum documents the new geometry but keeps the name",
      "NEAR-EDGE PULLBACK (v5.64)" in DEFS_T and "ENTRY_FRONT_EDGE = 1" in DEFS_T)
check("the enum states risk per unit is unchanged",
      "risk per unit is identical to v5.63" in norm(DEFS_T))
check("the router states the guard leaves ROUTE A to MIDPOINT setups",
      "ROUTE A is left to ENTRY_MIDPOINT setups" in norm(OM_RAW))
check("the order-type comment explains why a LIMIT is still returned",
      "STILL A LIMIT, deliberately" in OM_RAW and
      "ORDER_TYPE_BUY_LIMIT" in (OM_ORDTYPE or "") and
      "ORDER_TYPE_BUY_STOP" not in (OM_ORDTYPE or ""))
check("the virtual cross test documents its v5.64 role",
      "v5.64 ROLE" in OM_RAW)
check("the journal's projected target keeps the far-edge anchor",
      "v5.64 DELIBERATELY DID NOT RE-ANCHOR THIS ON THE ENTRY" in JRN_RAW)
check("the journal no longer describes the retired 0.5*ATR edges",
      "Buy at Top Edge + 0.5*ATR" not in JRN_RAW and
      "Sell at Bottom Edge - 0.5*ATR" not in JRN_RAW and
      "SL at Top Edge" not in JRN_RAW and
      "SL at Bottom Edge" not in JRN_RAW)
check("the journal trigger row names the Near-Edge Pullback entry",
      "Near-Edge Pullback entry: near edge +/- (blockHeight + 1.0*ATR)" in JRN_RAW)
check("no source still describes an 'extreme front-run' entry",
      "EXTREME FRONT-RUNNING ANTICIPATION" not in OM_RAW and
      "EXTREME FRONT-RUNNING ANTICIPATION" not in BM_RAW and
      "EXTREME FRONT-RUNNING ANTICIPATION" not in DEFS_T)


# ----------------------------------------------------------------------
# 5. Version stamps
# ----------------------------------------------------------------------
print("\n-- 5. Version stamps --")

STAMPS = re.findall(r'#property version\s+"(\d+\.\d+)"', DEFS_T)
check("OttoDefines.mqh carries exactly one version stamp", len(STAMPS) == 1,
      "found: %s" % sorted(STAMPS))
CURRENT = STAMPS[0] if STAMPS else "?"
check("the release is v5.64 or later",
      tuple(int(x) for x in CURRENT.split(".")) >= (5, 64), CURRENT)
missing = [f for f in ALL_FILES
           if not re.search(r'#property version\s+"%s"' % re.escape(CURRENT),
                            read(os.path.join(ROOT, f)))]
check("all %d shipped sources carry one common stamp" % len(ALL_FILES),
      not missing, "missing: %s" % ", ".join(missing))
check("the startup banner names the current release",
      ("OTTO EA v%s" % CURRENT) in MAIN_T)


# ----------------------------------------------------------------------
def main():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("=" * 74)
    print("v5.64 NEAR-EDGE PULLBACK ENTRY + CROSSING GUARD - STATIC PROBE")
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
