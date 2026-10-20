"""
v5.63 static verification probe -- AUXILIARY VETO PURGE.

v5.62 carried two layers in the execution funnel:

  STRUCTURAL (kept)   -- does this ZONE still exist and is it well formed?
                         VETO_SIZING / VETO_NO_SEPARATION / VETO_BROKEN /
                         VETO_FLIPPED, all decided from closed candles.

  AUXILIARY (purged)  -- does this TRADE look attractive right now?
                         Front-Run (InpMaxRR target already touched), Stale
                         (45 market days), Near-Miss (6 days in a proximity
                         band), Momentum / FVG (8-bar scan), currency-vector
                         consensus (VETO_CORRELATION), News Shield blackout.

v5.63 deletes the second layer COMPLETELY -- enum members, struct fields,
inputs (declared no-ops for .set compatibility), funnel branches, the
intra-bar re-check, the order-path gates, the consensus cancel sweep, the
cross-chart Hive-Mind arbiter, and the two modules that existed only to
serve it (COttoNewsFilter.mqh, COttoCorrelationFilter.mqh).

This probe asserts BOTH halves: that the auxiliary layer is gone in every
form, and that the structural layer is intact and still wired. A purge probe
that only checked for absence would pass on an empty file, so every removed
symbol is paired with a surviving one.

Pure static analysis of the shipped sources -- no MT5 required.
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "otto.mq5")
OM = os.path.join(ROOT, "COttoOrderManager.mqh")
BM = os.path.join(ROOT, "COttoBlockManager.mqh")
DEFS = os.path.join(ROOT, "OttoDefines.mqh")
JRN = os.path.join(ROOT, "COttoJournal.mqh")
BUILD = os.path.join(ROOT, "_tools", "build_check.ps1")

# The 9 modules that ship in v5.63 (was 11).
ALL_FILES = ["otto.mq5", "COttoOrderManager.mqh", "COttoTradeManager.mqh",
             "COttoRiskManager.mqh", "COttoBlockManager.mqh", "COttoJournal.mqh",
             "CHighTableAuditor.mqh", "COttoMarketStructure.mqh",
             "OttoDefines.mqh"]

REMOVED_FILES = ["COttoNewsFilter.mqh", "COttoCorrelationFilter.mqh"]


def read(p):
    return io.open(p, encoding="utf-8", errors="replace",
                   newline="").read().replace("\r\n", "\n")


def strip_comments(code):
    """Drop // comments, respecting string literals.

    Load-bearing: this release DOCUMENTS its own removals in place
    (tombstones naming VETO_FRONTRUN, localTP, the vector engine, ...). A raw
    substring test would fire on the documentation of the purge rather than on
    live code, so every "is it gone" assertion runs on stripped text.
    """
    out = []
    for line in code.split("\n"):
        idx = line.find("//")
        if idx < 0:
            out.append(line)
            continue
        out.append(line if line[:idx].count('"') % 2 else line[:idx])
    return "\n".join(out)


def body(src, marker):
    """Brace-matched body of the function whose header contains `marker`."""
    i = src.find(marker)
    if i < 0:
        return None
    j = src.find("{", i)
    if j < 0:
        return None
    depth = 0
    k, n = j, len(src)
    while k < n:
        c = src[k]
        if c == '"':
            k += 1
            while k < n and src[k] != '"':
                k += 2 if src[k] == "\\" else 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
        k += 1
    return None


MAIN_T, OM_T, BM_T, DEFS_T, JRN_T = (read(p) for p in (MAIN, OM, BM, DEFS, JRN))
MAIN_C, OM_C, BM_C, DEFS_C = (strip_comments(x) for x in (MAIN_T, OM_T, BM_T, DEFS_T))

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def main():
    # ------------------------------------------------------------------
    print("\n-- 1. Purged veto reasons are gone from the enum --")
    # ------------------------------------------------------------------
    purged = ["VETO_STALE", "VETO_FRONTRUN", "VETO_NEARMISS",
              "VETO_MOMENTUM", "VETO_FVG", "VETO_CORRELATION"]
    for sym in purged:
        check("%s is not a declared enumerator" % sym,
              re.search(r"^\s*%s\b\s*[,=]" % sym, DEFS_C, re.M) is None)
        hits = [f for f, t in (("otto.mq5", MAIN_C), ("COttoOrderManager.mqh", OM_C),
                               ("COttoBlockManager.mqh", BM_C))
                if re.search(r"\b%s\b" % sym, t)]
        check("%s has no live code reference" % sym, not hits, ",".join(hits))

    keepers = ["VETO_NONE", "VETO_SIZING", "VETO_NO_SEPARATION",
               "VETO_BROKEN", "VETO_FLIPPED"]
    for sym in keepers:
        check("%s still declared" % sym,
              re.search(r"\b%s\b" % sym, DEFS_C) is not None)

    # ------------------------------------------------------------------
    print("\n-- 2. Structural break/flip is intact and still wired --")
    # ------------------------------------------------------------------
    check("the break test still exists as `bool isBroken`",
          "bool isBroken" in BM_C)
    check("the break test still reads ATRBufferBreak off the FAR edge",
          BM_C.count("ATRBufferBreak") >= 2)
    check("BROKEN still vetoes an armed block",
          "SetVeto(i, VETO_BROKEN)" in BM_C)
    check("FLIPPED still vetoes a wide-range break",
          "SetVeto(i, VETO_FLIPPED)" in BM_C)
    check("the flip still reverts polarity before vetoing",
          "b.type = (b.type == BLOCK_SUPPORT) ? BLOCK_RESISTANCE : BLOCK_SUPPORT;" in BM_C)
    check("SIZING and NO_SEPARATION still emit",
          "VETO_SIZING" in BM_C and "VETO_NO_SEPARATION" in BM_C)

    pb = body(BM_C, "void                    ProcessBlocks(")
    check("ProcessBlocks located", pb is not None)
    if pb:
        check("the funnel no longer sets a time-based veto",
              "marketDay - b." not in pb and "InpStaleDays" not in pb)
        check("the funnel no longer runs an 8-bar momentum/FVG scan",
              "3.5 * atrJ" not in pb and "GetATRAtShift(j)" not in pb)
        check("the funnel still arms and still tests break/flip",
              "b.isArmed = true" in pb and "bool isBroken" in pb)

    # ------------------------------------------------------------------
    print("\n-- 3. Purged inputs survive only as declared no-ops --")
    # ------------------------------------------------------------------
    retired_inputs = ["InpUseFvgVeto", "InpUseMomVeto", "InpUseNearMissVeto",
                      "InpUseFrontRunVeto", "InpUseStaleVeto", "InpStaleDays",
                      "EnableNewsFilter", "NewsMinutesBefore", "NewsMinutesAfter",
                      "InpSimNewsShield", "InpSimMacroVeto", "InpSimSentiment",
                      "InpEnableVectorEngine", "InpConsensusVetoThreshold",
                      "InpUseExternalAnchors", "InpAnchorTF",
                      "InpCancelOpposingPendings"]
    for name in retired_inputs:
        check("%s is still DECLARED (an old .set must load)" % name,
              re.search(r"^\s*input\s+\w+\s+%s\s*=" % name, DEFS_T, re.M) is not None)
        check("%s is labelled RETIRED (v5.63)" % name,
              # The label is a TRAILING comment, so it sits after the ';'.
              re.search(r"input\s+\w+\s+%s\s*=[^;\n]*;\s*//[^\n]*RETIRED" % name,
                        DEFS_T) is not None)
        live = [label for label, text in
                (("otto.mq5", MAIN_C), ("COttoOrderManager.mqh", OM_C),
                 ("COttoBlockManager.mqh", BM_C))
                if re.search(r"\b%s\b" % name, text)]
        check("%s has no live reader" % name, not live, ",".join(live))

    check("InpUseSeparationVeto is NOT retired (it is structural)",
          re.search(r"input\s+bool\s+InpUseSeparationVeto\s*=", DEFS_T) is not None and
          "RETIRED" not in DEFS_T.split("InpUseSeparationVeto")[1].split("\n")[0])
    check("InpMaxRR survives (journal projection, never a veto input)",
          re.search(r"input\s+double\s+InpMaxRR\s*=", DEFS_T) is not None)

    # ------------------------------------------------------------------
    print("\n-- 4. Struct fields retired with their only readers --")
    # ------------------------------------------------------------------
    for fld in ["localTP", "wick1Day", "minProxDist", "anchorTime",
                "anchorDay", "anchorPrice", "anchorId"]:
        check("SSniperBlock::%s is gone from the struct" % fld,
              re.search(r"^\s*(double|int|datetime)\s+%s\s*;" % fld,
                        DEFS_C, re.M) is None)
        check("no live code writes %s" % fld,
              not re.search(r"\.%s\s*=" % fld, OM_C + BM_C))
    check("m_anchorCounter is gone from the BlockManager",
          "m_anchorCounter" not in BM_C)

    # ------------------------------------------------------------------
    print("\n-- 5. The order path carries no discretionary gate --")
    # ------------------------------------------------------------------
    poa = body(OM_C, "bool                    PlaceOrArmOrder(")
    check("PlaceOrArmOrder located", poa is not None)
    if poa:
        for gone in ["IsConsensusOpposed", "IsTradeVetoed", "SentimentPasses",
                     "m_correlationFilter", "InpSimNewsShield", "InpSimMacroVeto",
                     "VETO_CORRELATION"]:
            check("PlaceOrArmOrder no longer calls %s" % gone, gone not in poa)
        check("PlaceOrArmOrder still applies the spread gate",
              "IsSpreadAcceptable()" in poa)
        check("PlaceOrArmOrder still applies CanPlaceForDirection()",
              "CanPlaceForDirection(block)" in poa)
        check("PlaceOrArmOrder still records localEntry/localSL/rrUnit",
              "block.localEntry" in poa and "block.localSL" in poa and
              "block.rrUnit" in poa)
        check("no take-profit is projected or transmitted",
              "takeProfit" not in poa)

    check("CancelOpposingConsensusOrders declaration is gone",
          "CancelOpposingConsensusOrders(void)" not in OM_C)
    check("SentimentPasses is gone", "SentimentPasses" not in OM_C)
    check("the OrderManager holds no correlation filter pointer",
          "m_correlationFilter" not in OM_C)
    check("the OrderManager no longer includes the correlation module",
          "COttoCorrelationFilter.mqh" not in OM_C)

    # ------------------------------------------------------------------
    print("\n-- 6. The retired modules are gone and unreferenced --")
    # ------------------------------------------------------------------
    for f in REMOVED_FILES:
        check("%s is deleted from the tree" % f,
              not os.path.exists(os.path.join(ROOT, f)))
        check("%s is not included by any shipped source" % f,
              not re.search(r"#include\s*[<\"]Otto[/\\]%s" % re.escape(f),
                            MAIN_T + OM_T + BM_T + DEFS_T + JRN_T))
    check("otto.mq5 holds no news-filter instance or call",
          "g_newsFilter" not in MAIN_C)
    check("otto.mq5 holds no correlation-filter instance or call",
          "g_correlationFilter" not in MAIN_C)
    check("OnTick keeps the CheckVetoesInTick seam", "CheckVetoesInTick" in MAIN_C)
    ib = body(BM_C, "void                    UpdateIntraBar(")
    check("UpdateIntraBar/CheckVetoesInTick is now an empty seam",
          ib is not None and "SetVeto" not in ib)

    # ------------------------------------------------------------------
    print("\n-- 7. News / consensus / sentiment removed from OnTick --")
    # ------------------------------------------------------------------
    check("OnTick no longer gates placement on a news blackout",
          "IsInNewsBlackout" not in MAIN_C)
    check("OnTick no longer refreshes vector state",
          "RefreshVectorState" not in MAIN_C)
    check("OnTick still gates placement on the daily-DD pause",
          "if(!g_dailyDD_Paused)" in MAIN_C)
    check("OnTick still runs the block funnel and order placement",
          "g_blockManager.Update(g_marketDay)" in MAIN_C and
          "g_orderManager.PlaceOrdersForArmedBlocks()" in MAIN_C)
    check("OnTick still cancels orders for structurally invalid blocks",
          "CancelOrdersForInvalidBlocks()" in MAIN_C)

    hm = body(MAIN_C, "void HiveMind(")
    check("HiveMind located", hm is not None)
    if hm:
        check("HiveMind resolves the conflict locally (no filter delegate)",
              "ResolveBidirectionalConflict" not in hm and
              "BroadcastBias" not in hm)
        check("HiveMind still deletes the losing polarity",
              "DeleteBlockType(BLOCK_SUPPORT)" in hm and
              "DeleteBlockType(BLOCK_RESISTANCE)" in hm)
        check("the KEPT side is the majority (no inverted pairing)",
              "majority Long -> kept Resistance" in hm)

    # ------------------------------------------------------------------
    print("\n-- 8. Journal + build tooling follow the 9-module tree --")
    # ------------------------------------------------------------------
    check("the journal reads no retired block field", "blk.localTP" not in JRN_T)
    check("the journal still prints a projected target", "ProjectedTarget(" in JRN_T)
    check("the journal derives that target from InpMaxRR", "InpMaxRR" in JRN_T)
    build_t = read(BUILD)
    check("build_check.ps1 stages exactly the 9 surviving modules",
          "all 9 OTTO sources" in build_t)
    for f in REMOVED_FILES:
        check("build_check.ps1 no longer expects %s" % f, f not in build_t)

    # ------------------------------------------------------------------
    print("\n-- 9. Release stamps --")
    # ------------------------------------------------------------------
    stamps = re.findall(r'#property version\s+"(\d+\.\d+)"', DEFS_T)
    check("OttoDefines.mqh carries exactly one version stamp",
          len(set(stamps)) == 1, "found: %s" % sorted(set(stamps)))
    current = sorted(set(stamps))[0] if stamps else "?"
    missing = [f for f in ALL_FILES
               if not re.search(r'#property version\s+"%s"' % re.escape(current),
                                read(os.path.join(ROOT, f)))]
    check("all %d shipped sources carry one common stamp" % len(ALL_FILES),
          not missing, "missing: %s" % ", ".join(missing))
    major, minor = (current.split(".") + ["0", "0"])[:2]
    check("the common stamp is v5.63 or later",
          (int(major), int(minor)) >= (5, 63), "stamps=%s" % sorted(set(stamps)))
    check("the startup banner names the current release",
          ("OTTO EA v%s" % current) in MAIN_T)

    # ------------------------------------------------------------------
    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n" + "=" * 74)
    for name, ok, detail in RESULTS:
        line = "  [%s] %s" % ("PASS" if ok else "FAIL", name)
        if not ok and detail:
            line += "  <%s>" % detail
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

