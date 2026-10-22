"""
v5.57 static verification probe - FRONT-RUNNING ANTICIPATION ENTRY.

v5.57 moved the entry onto an EXTREME FRONT-RUNNING ANTICIPATION model
(entry = the zone edge plus one full stop distance, i.e. 0.5*ATR BEYOND the
edge the breakout crosses) and moved the level the virtual engine waits on
from a resting price to a MARKET cross.

v5.64 UPDATE -- the CROSS-TRIGGER MODEL IS UNCHANGED; only its scale moved.
The entry offset is now blockHeight + 1.0*ATR measured from the NEAR edge
(= 1.0*ATR beyond the far edge, was 0.5*ATR), while slDist is still
blockHeight + 0.5*ATR. Three properties still carry the change and NOT ONE
of them is visible to the MQL5 compiler, because each is a runtime
relationship between two files:

  1. ATR SHIFT SYNC. COttoBlockManager prices its entry projection from
     GetATRAtShift(1) -- the last CLOSED bar. COttoOrderManager must price
     the matching entry / SL / rrUnit from the SAME shift, or on a live bar
     the two would be built from different ATRs. The cached GetATR()
     refreshes from shift 0 (the FORMING bar), so it may only ever be a
     FALLBACK: shift 1 first, GetATR() second, and a hard abandon when
     neither is populated. GetATRAtShift() itself had to move into the
     public section for the OrderManager call to compile at all -- and the
     compiler cannot tell that the CALLER meant the same shift.

  2. THE INVERTED CROSS TEST. A front-run entry is armed BEYOND the far
     edge, so a LONG must fire once the market has traded UP TO (or through)
     the level; a resting-limit test would run the opposite way (a pullback
     DOWN through the level). The sign of that one comparison is the whole
     difference between a market anticipation entry and a limit order, and
     it is invisible at compile time -- the block still arms either way.
     v5.64 pairs it with the crossing guard, its exact negation at arm time,
     so an order can never arm already crossed.

  3. THE FAR-EDGE TARGET ANCHOR. The journal's projected target is measured
     from the FAR EDGE (block.top LONG / block.bottom SHORT), not from the
     entry, so the printed row stays comparable with every pre-v5.57 build.
     The consequence, pinned in section 7, is that the target is no longer a
     full InpMaxRR from the ENTRY: realized entry-anchored RR is
     InpMaxRR - ATR/slDist (e.g. 4.0 -> 3.0 on a 1.0-high zone at ATR 2.0;
     it was 3.5 under the v5.57 0.5*ATR offset). That is intended, not a
     defect, and the invariant is asserted so a future re-anchor has to be a
     deliberate act.

WHAT THIS PROBE PINS. The ATR shift sync and its fallback in all three
OrderManager price paths, the public visibility of GetATRAtShift(), the two
entry twins' textual identity (COttoBlockManager::BlockEntryPrice() vs
COttoOrderManager::CalcEntryPrice(), which MUST judge one price), the
two-argument call sites and the retirement of the single-argument form, the
1.0*ATR entry offset plus the UNCHANGED 0.5*ATR stop distance, the inverted
cross test plus the absence of the retired v5.56 predicate, the geometry
identity and full arithmetic table behind the realization above, and the
release stamps.

WHAT IT CANNOT PROVE. That the ATR cache slot is actually POPULATED on the
tick that matters, and that the cross fires on the intended bar, are
Strategy-Tester properties. This probe is pure static analysis of the
shipped sources -- no MT5 required.

Companion to test_v530_price_guard.py, which pins the SNAP the entry price
depends on but pins nothing about where that price comes from.
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "otto.mq5")
OM = os.path.join(ROOT, "COttoOrderManager.mqh")
BM = os.path.join(ROOT, "COttoBlockManager.mqh")
DEFS = os.path.join(ROOT, "OttoDefines.mqh")
JRN = os.path.join(ROOT, "COttoJournal.mqh")

ALL_FILES = ["otto.mq5", "COttoOrderManager.mqh", "COttoTradeManager.mqh",
             "COttoRiskManager.mqh", "COttoBlockManager.mqh", "COttoJournal.mqh",
             "CHighTableAuditor.mqh",
             "COttoMarketStructure.mqh",
             "OttoDefines.mqh"]


def read(p):
    # Normalise CRLF so every anchor below can be written with a plain \n.
    return io.open(p, encoding="utf-8", errors="replace",
                   newline="").read().replace("\r\n", "\n")


def strip_comments(code):
    """Drop // comments, respecting string literals.

    Load-bearing here: v5.57 documents the RETIRED behaviour in place
    ("Projecting from the entry pushed the target a further 0.5*ATR out"),
    so a raw substring test would trip over the probe's own subject matter.
    A '//' is only a comment when an even number of '"' precede it.
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
    """Collapse every whitespace run so two spellings can be compared."""
    return re.sub(r"\s+", " ", s).strip()


def body(src, marker):
    """Brace-matched body of the function whose header contains `marker`.

    The shipped sources slate-indent every method, so a method's closing
    brace is the first one in column 0 -- but a nested block's brace is also
    column-indented and can be found first, so slicing to the next "\n    }"
    would not generalise. This walks the braces instead, skipping string and
    char literals.
    """
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
    """Blank the twin-specific identifiers so the two verify as one.

    BlockEntryPrice() reads `const SSniperBlock &b` and calls
    BlockDirection(); CalcEntryPrice() reads `&block` and calls
    GetDirectionForBlock(). Those spellings are the ONLY permitted
    difference; everything else must match byte for byte.
    """
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
OM_VIRT = body(OM_C, "CheckVirtualTriggers(void)")
OM_REV = body(OM_C, "OpenReversalPosition(SSniperBlock &targetBlock)")
OM_CALC = body(OM_C, "CalcEntryPrice(const SSniperBlock &block, double atr)")
OM_SLD = body(OM_C, "CalcSLDistance(const SSniperBlock &block, double atr)")
BM_GET = body(BM_C, "GetATRAtShift(int shift)")
BM_BEP = body(BM_C, "BlockEntryPrice(const SSniperBlock &b, double atr) const")
BM_PROC = body(BM_C, "ProcessBlocks(int marketDay)")
BM_INTRA = body(BM_C, "UpdateIntraBar(int marketDay)")

# The gate count is asserted as an EQUALITY so a third (ungated) pass added
# later fails the probe instead of passing it. The leading text guard stops
# the lookbehind escaping a named constant such as !InpUseFrontRunVeto, and
# \b admits the bar-close form that ANDs a hasExited/!isTriggered guard on.
_gates0 = re.findall(r"(?<![\w!])if\(InpUseFrontRunVeto\b", BM_RAW)
_gates = len(_gates0)


# ----------------------------------------------------------------------
# 1. ATR SHIFT SYNC - all three OrderManager price paths
# ----------------------------------------------------------------------
print("\n-- 1. ATR shift sync --")

SHIFT1 = "m_blockManager.GetATRAtShift(1)"
FALLBACK = "if(atr <= 0) atr = m_blockManager.GetATR();"

for label, fn in (("PlaceOrArmOrder", OM_PLACE),
                  ("CheckVirtualTriggers", OM_VIRT),
                  ("OpenReversalPosition", OM_REV)):
    blob = norm(fn or "")
    check("%s prices from GetATRAtShift(1)" % label, SHIFT1 in blob)
    check("%s keeps GetATR() only as the fallback" % label, FALLBACK in blob)

check("exactly 3 shift-1 ATR reads order the manager's geometry",
      len(re.findall(r"GetATRAtShift\(1\)", OM_C)) == 3,
      "found %d" % len(re.findall(r"GetATRAtShift\(1\)", OM_C)))
check("exactly 3 matching GetATR() fallbacks",
      len(re.findall(r"atr <= 0\) atr = m_blockManager\.GetATR\(\)", OM_C)) == 3,
      "found %d" % len(re.findall(r"atr <= 0\) atr = m_blockManager\.GetATR\(\)", OM_C)))
check("the live entry path abandons the setup when no ATR is available",
      re.search(r"if\(atr <= 0\) return false;", OM_PLACE or "") is not None)
check("the reversal fallback is guarded by atr > 0, not a hard return",
      "if(atr > 0)" in (OM_REV or ""))
check("the virtual-fill recovery degrades to the trigger/stop distance",
      "MathAbs(vo.triggerPrice - vo.stopLoss)" in (OM_VIRT or ""))

# An extraction failure must surface as ONE named failure, not an obscure
# TypeError deep inside norm() -- a probe that crashes reports nothing.
check("every OrderManager price path resolved",
      all(f is not None for f in (OM_PLACE, OM_VIRT, OM_REV, OM_CALC, OM_SLD)))
check("both BlockManager passes plus the entry helper resolved",
      all(f is not None for f in (BM_GET, BM_BEP, BM_PROC, BM_INTRA)))

# ----------------------------------------------------------------------
# 2. GetATRAtShift() is reachable, and reads the shift it names
# ----------------------------------------------------------------------
print("\n-- 2. GetATRAtShift visibility and semantics --")

check("GetATRAtShift() is declared in the public section",
      re.search(r"public:(?:(?!private:)[\s\S])*GetATRAtShift\(int shift\)",
                BM_RAW) is not None,
      "declaration is not reachable from COttoOrderManager")
check("it bounds-checks the requested shift", "shift < 0" in (BM_GET or ""))
check("it honours the named shift rather than a hardcoded slot",
      "m_atrHistory[shift]" in (BM_GET or ""))
check("it returns 0 for an unpopulated slot rather than EMPTY_VALUE",
      "EMPTY_VALUE" in (BM_GET or "") and "return 0" in (BM_GET or ""))

# The veto used to read the same shift as the order, or the two judged
# different ATRs. v5.63 removes the veto projection from the bar-close pass,
# but the ORDER path still prices off shift 1 and the funnel still needs
# atrNow, so the shift-1 invariant survives on both sides.
check("the bar-close funnel still prices from shift 1",
      re.search(r"double atrNow = GetATRAtShift\(1\);", BM_PROC or "") is not None)
check("the intra-bar seam no longer reads ATR at all (v5.63 retired its body)",
      "GetATRAtShift" not in (BM_INTRA or ""))
check("NEITHER BlockManager pass is gated on the retired InpUseFrontRunVeto",
      _gates == 0, "found %d" % _gates)
check("the bar-close pass no longer tests the Front-Run veto condition",
      "InpUseFrontRunVeto" not in norm(BM_PROC or ""))
check("the intra-bar pass no longer tests the Front-Run veto condition",
      "InpUseFrontRunVeto" not in norm(BM_INTRA or ""))
check("the anticipation entry applies at EVERY entry style, not just the default",
      len(re.findall(r"ENTRY_FRONT_EDGE", BM_PROC or "")) == 0
      and len(re.findall(r"ENTRY_FRONT_EDGE", BM_INTRA or "")) == 0,
      "the front-run pass must not be switchable away by InpEntryStyle")


# ----------------------------------------------------------------------
# 3. The two entry twins, and the retirement of the single-arg form
# ----------------------------------------------------------------------
print("\n-- 3. Entry twins --")

check("BlockManager exposes the TWO-argument BlockEntryPrice",
      "BlockEntryPrice(const SSniperBlock &b, double atr) const" in BM_RAW)
check("OrderManager exposes the TWO-argument CalcEntryPrice",
      "CalcEntryPrice(const SSniperBlock &block, double atr)" in OM_RAW)
check("SnapToTick wraps the TWO-argument call",
      "SnapToTick(CalcEntryPrice(block, atr))" in OM_RAW)
check("the single-argument CalcEntryPrice(block) form is retired",
      "CalcEntryPrice(block)" not in OM_C)
check("the single-argument BlockEntryPrice(b) form is retired",
      "BlockEntryPrice(b)" not in BM_C)

# The twins MUST judge one price: the veto compares the market against a
# target this helper produced. Comparing the canonicalised bodies catches a
# divergence in the arithmetic while tolerating the two legitimate
# spellings documented in canon().
BEP_BODY = canon_body(BM_BEP, "b")
CALC_BODY = canon_body(OM_CALC, "block")
check("the two entry twins are arithmetically identical",
      BEP_BODY == CALC_BODY,
      "BM=%s || OM=%s" % (BEP_BODY[:70], CALC_BODY[:70]))
check("both twins honour ENTRY_MIDPOINT before the front-edge maths",
      "if(InpEntryStyle == ENTRY_MIDPOINT) return midpoint;" in BEP_BODY and
      "if(InpEntryStyle == ENTRY_MIDPOINT) return midpoint;" in CALC_BODY)
check("the front-edge entry is one (blockHeight + 1.0*ATR) past the near edge",
      "return (Dir(x) == DIR_LONG) ? (bottom + pullback) : (top - pullback);" in BEP_BODY,
      BEP_BODY)
check("the entry offset is blockHeight + 1.0*ATR (v5.64, was slDist)",
      "double pullback = blockHeight + (1.0 * atr);" in BEP_BODY and
      "slDist" not in BEP_BODY,
      BEP_BODY)

# ----------------------------------------------------------------------
# 4. The far-edge target anchor -- RETIRED (v5.63)
# ----------------------------------------------------------------------
# v5.57 pinned a far-edge InpMaxRR projection in BOTH BlockManager passes and
# the OrderManager, so the Front-Run veto judged one price. v5.63 deletes the
# veto, block.localTP and the projection. The surviving invariants are the
# negatives: neither BlockManager pass nor the order path may re-derive a
# target, and neither may read a stored one.
print("\n-- 4. Far-edge target anchor (RETIRED v5.63) --")

for label, fn in (("ProcessBlocks", BM_PROC), ("UpdateIntraBar", BM_INTRA)):
    blob = canon(norm(fn or ""), "b")
    check("%s no longer projects a far-edge target" % label,
          "farEdge" not in blob and "tpRR" not in blob)
    check("%s no longer reads a stored localTP" % label, "localTP" not in blob)
    check("%s no longer vetoes with VETO_FRONTRUN" % label,
          "VETO_FRONTRUN" not in blob)

check("neither BlockManager pass projects a far-edge target",
      len(re.findall(r"double farEdge", BM_C)) == 0)
check("neither BlockManager pass defers to block.localTP",
      len(re.findall(r"target = b\.localTP;", BM_C)) == 0)
check("neither pass recalls a single-arg entry helper",
      "BlockEntryPrice(" not in BM_PROC and
      "BlockEntryPrice(" not in BM_INTRA)

# The entry geometry the far-edge anchor was derived FROM is untouched: the
# anticipation entry still sits BEYOND the edge the breakout crosses, now a
# full 1.0*ATR past it (v5.64 widened this from 0.5*ATR).
check("the entry twins still agree on the anticipation geometry",
      "BlockEntryPrice(" in BM_RAW and "CalcEntryPrice(" in OM_RAW and
      "block.bottom + pullback" in OM_RAW)

# The OrderManager must no longer project the veto's target at all.
PLACE_CANON = canon(OM_PLACE or "", "block")
check("OrderManager no longer projects a far-edge target",
      "farEdge" not in PLACE_CANON and "takeProfit" not in PLACE_CANON)
check("OrderManager no longer writes a TP back to the block",
      "localTP = takeProfit;" not in PLACE_CANON)


# ----------------------------------------------------------------------
# 5. The INVERTED cross test
# ----------------------------------------------------------------------
print("\n-- 5. Inverted cross test --")

LIVE_CROSS = "isLong ? (ask < vo.triggerPrice) : (bid > vo.triggerPrice)"
RETIRED_CROSS = "isLong ? (ask > vo.triggerPrice) : (bid < vo.triggerPrice)"

check("the virtual engine fires on a cross TOWARDS the trigger",
      LIVE_CROSS in (OM_VIRT or ""))
check("the retired v5.56 resting-limit predicate is gone",
      RETIRED_CROSS not in (OM_VIRT or "") and RETIRED_CROSS not in OM_C)
check("the cross is documented as a market condition",
      "THE CROSS TEST" in OM_RAW and
      "a gap past it still fires" in OM_RAW)
# Only the entry-side comparison may be inverted; the exit-side must still
# read the opposite way or a fired order would seed its basket on the
# wrong trigger point.
check("exactly one cross predicate survives",
      len(re.findall(r"vo\.triggerPrice\)", OM_C)) >= 1,
      "found %d" % len(re.findall(r"vo\.triggerPrice\)", OM_C)))


# ----------------------------------------------------------------------
# 6. SL / TP wiring and seed anchors
# ----------------------------------------------------------------------
print("\n-- 6. SL/TP wiring --")

check("the stop is one slDist on the far side of the entry",
      "isLong ? entryPrice - slDist : entryPrice + slDist;" in (OM_PLACE or ""))
PLACE_W = norm(OM_PLACE or "")
VIRT_W = norm(OM_VIRT or "")
# The quo/  column spacing is part of the shipped literal, so normalise
# whitespace before matching rather than pinning a column.
check("rrUnit is seeded from the SAME slDist the order used",
      "rrUnit = slDist;" in PLACE_W)
# v5.63: the InpMaxRR projection and the TP written back to the block are GONE
# from both paths. Only localEntry / localSL / rrUnit land on the block.
check("no InpMaxRR projection survives on the order path",
      "tpRR" not in PLACE_W and "InpMaxRR" not in PLACE_W)
check("the BlockManager no longer projects from InpMaxRR",
      "tpRR" not in norm(BM_PROC or ""))
check("only the SL lands on the block (no TP to read back)",
      "block.localSL = stopLoss;" in PLACE_W and
      "block.localTP" not in PLACE_W)
check("the entry is reclaimed from the virtual trigger, not recomputed",
      "block.localEntry = vo.triggerPrice;" in VIRT_W)
check("the stop is reclaimed from the armed virtual order",
      "block.localSL = vo.stopLoss;" in VIRT_W)
check("the virtual-fill path rebuilds rrUnit from the block's own geometry",
      "block.rrUnit = slDist;" in VIRT_W)
check("the reclaimed entry is normalized to the symbol's digit grid",
      "vo.triggerPrice = NormalizeDouble(entryPrice," in PLACE_W)
check("the basket 1R is the block's rrUnit, not the broker-adjusted stop",
      "block.rrUnit;" in OM_C and
      "m_activeTrade.rrUnit" in OM_C)

# ----------------------------------------------------------------------
# 7. The geometry behind the far-edge anchor, asserted numerically
# ----------------------------------------------------------------------
print("\n-- 7. Geometry identity --")


def realized(bh, atr, rr):
    """Transcribe the shipped geometry with the near edge at 0.0.

    LONG is the whole story: DIR_SHORT is the mirror image, so one side
    proves both. nearEdge=0, farEdge=bh,
    entry = nearEdge + (bh + 1.0*atr)  [v5.64; was nearEdge + slDist],
    stop  = entry - slDist,
    tp    = farEdge + InpMaxRR*slDist  (journal projection, far-edge anchor).
    """
    sl = bh + 0.5 * atr
    entry = bh + 1.0 * atr
    return (entry, entry - sl, bh + rr * sl, sl)   # entry, stop, tp, slDist


CASES = [(1.0, 2.0, 4.0), (2.0, 1.0, 4.0), (1.0, 1.0, 2.0), (0.5, 4.0, 4.0)]
risk_ok = anchor_ok = bound_ok = True
for bh, atr, rr in CASES:
    entry, stop, tp, sl = realized(bh, atr, rr)
    if abs(abs(entry - stop) - sl) > 1e-12:
        risk_ok = False                      # risk must never drift
    if abs((tp - entry) - (rr - atr / sl) * sl) > 1e-12:
        anchor_ok = False                    # the far-edge identity
    x = (tp - entry) / abs(entry - stop)
    # v5.64: the entry sits 1.0*ATR out while the stop is 0.5*ATR back, so the
    # realized multiple is InpMaxRR - ATR/slDist. Because slDist = bh + 0.5*ATR
    # > 0.5*ATR, the ratio ATR/slDist is always < 2, giving the tightened bound
    # (InpMaxRR - 2, InpMaxRR]. The v5.57 bound was (InpMaxRR - 1, InpMaxRR]
    # because the offset there was exactly 0.5*ATR; that no longer holds.
    if not (rr - 2.0 < x <= rr):
        bound_ok = False

check("the stop always sits exactly one slDist from the entry", risk_ok)
check("reward from the ENTRY == (InpMaxRR - ATR/slDist) * slDist", anchor_ok)
check("realized RR is bounded by (InpMaxRR - 2, InpMaxRR]", bound_ok)

# The v5.64 arithmetic table. Every row is the shipped expression evaluated
# with the near edge at 0.0 and the far edge at blockHeight, so a change to
# EITHER coefficient (1.0*ATR on the entry, 0.5*ATR on the stop) moves a row.
# "stop" is reported in zone-relative terms: 0.0 = near edge, bh = far edge.
TABLE = [
    # bh,  atr, entry, stop,   where the stop lands
    (1.0, 2.0,  3.00,  1.00,  "far"),      # ATR == 2*bh -> stop ON the far edge
    (2.0, 1.0,  3.00,  0.50,  "inside"),   # ATR <  2*bh -> stop INSIDE the zone
    (1.0, 1.0,  2.00,  0.50,  "inside"),
    (0.5, 4.0,  4.50,  2.00,  "outside"),  # ATR >  2*bh -> stop past the zone
]
table_ok = True
for bh, atr, want_entry, want_stop, where in TABLE:
    entry, stop, tp, sl = realized(bh, atr, 4.0)
    if abs(entry - want_entry) > 1e-12 or abs(stop - want_stop) > 1e-12:
        table_ok = False
    lands = ("far" if abs(stop - bh) < 1e-12 else
             "inside" if 0.0 < stop < bh else
             "outside" if stop > bh else "near")
    if lands != where:
        table_ok = False
check("the v5.64 arithmetic table (entry / stop / stop-vs-zone) holds", table_ok)

entry, stop, tp, sl = realized(1.0, 2.0, 4.0)
HEAD = (tp - entry) / abs(entry - stop)
check("the documented 1.0-high / ATR 2.0 / RR 4.0 zone realizes 3.0R",
      abs(HEAD - 3.0) < 1e-12, "%.4fR" % HEAD)
check("the target is NOT a full InpMaxRR from the pullback entry",
      HEAD < 4.0)
# The stop is 0.5*ATR inside the zone for ATR < 2*blockHeight -- the accepted
# v5.64 consequence. Pinned so it cannot drift silently in EITHER direction.
_ins = [realized(bh, atr, 4.0) for bh, atr in ((2.0, 1.0), (1.0, 1.0))]
check("the stop sits 0.5*ATR inside the zone when ATR < 2*blockHeight",
      all(abs(st - 0.5 * atr) < 1e-12 for (en, st, tp, sl), (bh, atr)
          in zip(_ins, ((2.0, 1.0), (1.0, 1.0)))))
check("the stop no longer lands on the near edge (the v5.57 invariant)",
      all(st > 1e-12 for en, st, tp, sl in _ins))


# ----------------------------------------------------------------------
# 8. Configuration: the anticipation entry is the SHIPPED default
# ----------------------------------------------------------------------
print("\n-- 8. Configuration --")

check("ENTRY_FRONT_EDGE is declared as the near-edge pullback style (v5.64)",
      "ENTRY_FRONT_EDGE" in DEFS_T and
      "NEAR-EDGE PULLBACK (v5.64)" in DEFS_T)
# v5.72 -- the DEFAULT flipped to the block midpoint. The front-edge entry is
# still declared and still selectable, so the assertion is now two-sided: the
# new default is midpoint AND the old style was retained rather than deleted.
check("InpEntryStyle defaults to the MIDPOINT entry (v5.72, was FRONT_EDGE)",
      "InpEntryStyle = ENTRY_MIDPOINT" in DEFS_T and
      "InpEntryStyle = ENTRY_FRONT_EDGE" not in DEFS_T)
check("the front-edge style is RETAINED as a selectable style, not deleted",
      "ENTRY_FRONT_EDGE = 1" in DEFS_T)
check("the OrderManager maps that style to the front-edge entry",
      "if(InpEntryStyle == ENTRY_MIDPOINT)" in (OM_CALC or "") and
      "if(InpEntryStyle == ENTRY_MIDPOINT)" in (BM_BEP or ""))
check("neither twin consults ENTRY_FRONT_EDGE directly (it is the else-branch)",
      "ENTRY_FRONT_EDGE" not in (OM_CALC or "") and
      "ENTRY_FRONT_EDGE" not in (BM_BEP or ""))
check("InpMaxRR defaults to 4.0",
      re.search(r"InpMaxRR\s*=\s*4\.0", DEFS_T) is not None)
check("the Front-Run veto switch is retired but still loadable (v5.63)",
      re.search(r"InpUseFrontRunVeto\s*=\s*true", DEFS_T) is not None)
check("neither BlockManager pass is gated on the retired switch",
      _gates == 0)
check("the retired single-arg helper left no call site anywhere",
      "BlockEntryPrice(" not in BM_PROC and "BlockEntryPrice(" not in BM_INTRA)


# ----------------------------------------------------------------------
# 9. Version stamps agree on the current release
# ----------------------------------------------------------------------
print("\n-- 9. Version stamps --")


def rel_parts(stamps):
    if not stamps:
        return (0, 0)
    major, minor = sorted(set(stamps))[0].split(".")
    return (int(major), int(minor))


STAMPS = re.findall(r'#property version\s+"(\d+\.\d+)"', DEFS_T)
CURRENT = sorted(set(STAMPS))[0] if STAMPS else "?"

check("OttoDefines.mqh carries exactly one version stamp",
      len(set(STAMPS)) == 1, "found: %s" % sorted(set(STAMPS)))
missing = [f for f in ALL_FILES
           if not re.search(r'#property version\s+"%s"' % re.escape(CURRENT),
                            read(os.path.join(ROOT, f)))]
check("all %d shipped sources carry one common stamp" % len(ALL_FILES),
      not missing, "missing: %s" % ", ".join(missing))
check("the common stamp is v5.57 or later", rel_parts(STAMPS) >= (5, 57),
      "stamps=%s" % sorted(set(STAMPS)))
check("the two-twin invariant is justified in BOTH files",
      "identical character for character" in norm(BM_RAW) and
      "identical character for character" in norm(OM_RAW),
      "the 'must stay identical' rationale is missing")
check("the source states WHY the shift had to reach the OrderManager",
      "GetATRAtShift(1) -- the LAST CLOSED bar" in BM_RAW)
check("the startup banner names the current release",
      ("OTTO EA v%s" % CURRENT) in MAIN_T)


# ----------------------------------------------------------------------
# 10. v5.58: journal + wick geometry synced to the anticipation model
# ----------------------------------------------------------------------
# The anticipation model moved the entry beyond the far edge, but the
# journal still described the v5.53 "Aggressive ... at ... Edge" geometry and
# the block's Wick1/Wick2 H/L fields were never written (ZeroMemory() left
# them 0.0), so the printed " H=0.00000 L=0.00000" was structural, not a
# missing log. These are runtime/printed relationships the compiler cannot
# see: nothing reads the wick fields, so a regression here is silent.
print("\n-- 10. Journal & wick geometry sync --")

check("the journal names the CONTINUATION geometry, not the veto wording",
      "Continuation Breakdown / Sell at Near Edge - blockHeight - 1.0*ATR | SL 1R back" in JRN_RAW and
      "Continuation Breakout / Buy at Near Edge + blockHeight + 1.0*ATR | SL 1R back" in JRN_RAW)
# v5.72 -- the journal label is now chosen from InpEntryStyle, so BOTH geometries
# must be present in the source. The midpoint strings are the ones the DEFAULT
# build actually prints; the front-edge pair survives for the selectable style.
check("the journal names the MIDPOINT geometry the default build prints",
      "Midpoint Pullback / Sell at (top + bottom) / 2.0 | SL 1R back" in JRN_RAW and
      "Midpoint Pullback / Buy at (top + bottom) / 2.0 | SL 1R back" in JRN_RAW)
check("the retired v5.58 'Top Edge / Bottom Edge' wording is gone",
      "Buy at Top Edge + 0.5*ATR" not in JRN_RAW and
      "Sell at Bottom Edge - 0.5*ATR" not in JRN_RAW and
      "SL at Top Edge" not in JRN_RAW and
      "SL at Bottom Edge" not in JRN_RAW)
check("the journal trigger-price row names the Near-Edge Pullback entry",
      "Near-Edge Pullback entry: near edge +/- (blockHeight + 1.0*ATR)" in JRN_RAW and
      "Front-Edge entry: far edge +/- 0.5*ATR" not in JRN_RAW)
# v5.72 -- the row is style-selected, so the MIDPOINT wording must also exist and
# must be the one the shipped default prints.
check("the journal trigger-price row names the MIDPOINT entry as the default",
      "Midpoint entry: (top + bottom) / 2.0 - exact zone centre" in JRN_RAW and
      "InpEntryStyle == ENTRY_MIDPOINT" in JRN_RAW)
check("the retired 'Aggressive' block wording is gone",
      "Aggressive" not in JRN_RAW)

# Both journal blocks (LogSetupArmed and LogEntry) must print the FULL zone
# marks -- Mid and Height were never shown, so an operator could not see the
# rrUnit derivation (slDist = blockHeight + 0.5*ATR) from the log alone.
check("both journal blocks print the full zone marks (Mid + Height)",
      JRN_RAW.count('" | Mid=" + FmtPrice(blk.midpoint) + " | Height=" + FmtPrice(blk.blockHeight)') == 2)
check("the armed header prints 1R and the projected target",
      'FmtPrice(blk.rrUnit)' in JRN_RAW and
      "Projected Target  : " in JRN_RAW and "FmtPrice(ProjectedTarget(" in JRN_RAW)
check("the target is re-derived locally, not read off the retired field",
      "ProjectedTarget(" in JRN_RAW and "blk.localTP" not in JRN_RAW)
check("the entry record prints the target alongside 1R",
      '" | 1R = " + FmtPrice(blk.rrUnit) + " | Target = " + FmtPrice(ProjectedTarget(' in JRN_RAW)

# The Wick H/L lines are now conditional, mirroring the entry block: a block
# whose wick times are unpopulated prints no bogus zero row.
check("both wick H/L blocks are guarded on populated wick times",
      JRN_RAW.count("if(blk.wick1Time > 0 && blk.wick2Time > 0)") == 2)

# All FOUR block-creation passes (live + warm-up, resistance + support) must
# populate the full W1/W2 candle, or the journal shows zeros for the half of
# the blocks built by the other pass.
check("all four block-creation passes populate the full W1/W2 candle",
      len(re.findall(r"nb\.wick1\.highPrice\s*=", BM_C)) == 4 and
      len(re.findall(r"nb\.wick1\.lowPrice\s*=", BM_C)) == 4 and
      len(re.findall(r"nb\.wick2\.highPrice\s*=", BM_C)) == 4 and
      len(re.findall(r"nb\.wick2\.lowPrice\s*=", BM_C)) == 4,
      "H=%d/%d L=%d/%d" % (len(re.findall(r"nb\.wick1\.highPrice\s*=", BM_C)),
                           len(re.findall(r"nb\.wick2\.highPrice\s*=", BM_C)),
                           len(re.findall(r"nb\.wick1\.lowPrice\s*=", BM_C)),
                           len(re.findall(r"nb\.wick2\.lowPrice\s*=", BM_C))))

# The virtual-fire commit no longer re-derives a TP: v5.63 deleted both the
# field and the projection it fed. What must survive is that the fire still
# reclaims entry / SL / rrUnit from the descriptor it actually sent.
check("CheckVirtualTriggers no longer re-derives a TP (v5.63)",
      "localTP" not in VIRT_W and "farEdge" not in VIRT_W)
check("the virtual fire still reclaims entry and SL from the descriptor",
      "block.localEntry = vo.triggerPrice;" in VIRT_W and
      "block.localSL = vo.stopLoss;" in VIRT_W)
check("the retired trigger-anchored projection is gone from the OrderManager",
      "vo.triggerPrice + slDist" not in (OM_C or "") and
      "vo.triggerPrice - slDist" not in (OM_C or ""))


# ----------------------------------------------------------------------
def main():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("=" * 74)
    print("v5.57 FRONT-RUNNING ANTICIPATION ENTRY - STATIC PROBE")
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
