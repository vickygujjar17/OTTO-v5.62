"""v5.67 -- remove the residual HiveMind() tie-breaker.

Byte-level rewrites (rb/wb) so the 10 deferred mojibake em-dashes and every
other non-ASCII byte in the tree survive untouched. Every edit is verified
in-place before the file is written back.
"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRLF = b"\r\n"


def load(name):
    path = os.path.join(ROOT, name)
    raw = io.open(path, "rb").read()
    assert raw.count(b"\n") == raw.count(CRLF), "%s: bare LF present" % name
    return path, raw.split(CRLF)


def save(path, lines):
    io.open(path, "wb").write(CRLF.join(lines))


def drop(lines, first, last, tag):
    """Delete 1-based inclusive line range, asserting the boundary text."""
    assert 1 <= first <= last <= len(lines), tag
    del lines[first - 1:last]
    print("  %-46s dropped %d lines (%d..%d)" % (tag, last - first + 1, first, last))


def replace(lines, first, last, new, tag):
    """Replace 1-based inclusive line range with `new` (list of bytes)."""
    assert 1 <= first <= last <= len(lines), tag
    lines[first - 1:last] = new
    print("  %-46s %d..%d -> %d lines" % (tag, first, last, len(new)))


# ----------------------------------------------------------------------
# otto.mq5
# ----------------------------------------------------------------------
path, L = load("otto.mq5")
print("otto.mq5 (%d lines)" % len(L))

# --- 1. Delete MappedZoneDirection() + HiveMind() and their banners.
# Boundaries asserted so a stale line number can never delete the wrong code.
assert L[559].startswith(b"//+---"), L[559]
assert L[560] == b"//| MAPPED direction of a zone for the local bias vote.             |", L[560]
assert L[579] == b"ENUM_TRADE_DIRECTION MappedZoneDirection(const SSniperBlock &b)", L[579]
assert L[608] == b"void HiveMind(void)", L[608]
assert L[649] == b"  }", L[649]
assert L[652].startswith(b"//+---"), L[652]
drop(L, 560, 652, "otto.mq5: MappedZoneDirection+HiveMind")

# --- 2. Delete the call site (blank + comment + call), located by content
# because step 1 already shifted every line number below 652.
ci = L.index(b"      HiveMind();")
assert L[ci - 1] == b"      // Hive Mind (correlation tie-breaker)", L[ci - 1]
assert L[ci - 2] == b"", L[ci - 2]
assert L[ci + 1] == b"     }", L[ci + 1]
drop(L, ci - 1, ci + 1, "otto.mq5: OnTick HiveMind() call")
assert b"HiveMind" not in b"\n".join(L), "HiveMind reference survived"

# --- 3. Include note: record that the tie-breaker is gone too.
assert L[25].startswith(b"// v5.63: COttoNewsFilter.mqh"), L[25]
replace(L, 26, 29, [
    b"// v5.63: COttoNewsFilter.mqh and COttoCorrelationFilter.mqh are no longer",
    b"// included. Both were auxiliary veto machinery (calendar blackout, portfolio",
    b"// currency-vector consensus) rather than parts of the structural engine, and",
    b"// both are deleted from the tree. v5.67 then removed the residual per-chart",
    b"// HiveMind() tie-breaker, so nothing here arbitrates one zone against another.",
], "otto.mq5: include notes")

# --- 4. TS_Bias_* note: say the local tie-breaker is gone as well.
# Located by content (step 3 shifted these indices by one) and padded to the
# width of the box it lives in, so the right-hand rule stays unbroken.
ti = next(i for i, ln in enumerate(L) if b"TS_Bias_*" in ln)
WIDTH = len(L[ti])
def box(text):
    return (b"//| " + text).ljust(WIDTH - 1) + b"|"

assert L[ti + 2].startswith(b"//| the cross-chart arbiter that published it is deleted."), L[ti + 2]
replace(L, ti + 1, ti + 3, [
    box(b"cannot collide. v5.63: the TS_Bias_* namespace that"),
    box(b"COttoCorrelationFilter used to own is no longer written at all --"),
    box(b"the cross-chart arbiter that published it is deleted. v5.67 also"),
    box(b"drops the residual local tie-breaker, so this tree arbitrates"),
    box(b"nothing: every chart trades only its own zones."),
], "otto.mq5: TS_Bias note")
for i in range(ti, ti + 5):   # exactly the 5 lines just written (replace is 1-based)
    assert len(L[i]) == WIDTH, (i, len(L[i]), L[i])
save(path, L)
print("  -> %d lines\n" % len(L))

# ----------------------------------------------------------------------
# COttoBlockManager.mqh -- DeleteBlockType() had exactly one caller.
# ----------------------------------------------------------------------
path, L = load("COttoBlockManager.mqh")
print("COttoBlockManager.mqh (%d lines)" % len(L))
assert L[1103] == b"   void              DeleteBlockType(ENUM_BLOCK_TYPE type)", L[1103]
assert L[1116] == b"     }", L[1116]
assert L[1118].startswith(b"   //+---"), L[1118]
drop(L, 1100, 1118, "BlockManager: DeleteBlockType()")
# The structural FLIPPED veto must survive: SetVeto(i, VETO_FLIPPED) stays.
assert b"SetVeto(i, VETO_FLIPPED)" in b"\n".join(L)
save(path, L)
print("  -> %d lines\n" % len(L))

# ----------------------------------------------------------------------
# COttoOrderManager.mqh -- MappedZoneDirection() no longer has a twin copy.
# ----------------------------------------------------------------------
path, L = load("COttoOrderManager.mqh")
print("COttoOrderManager.mqh (%d lines)" % len(L))
assert L[560] == b"      // TP, basket seed, correlation gate), so the mapping stays coherent.", L[560]
replace(L, 561, 564, [
    b"      // TP, basket seed), so the mapping stays coherent. v5.67 removed the",
    b"      // otto.mq5 MappedZoneDirection() copy along with HiveMind(), so this",
    b"      // and COttoBlockManager::BlockDirection() are now the only two twins",
    b"      // and must stay in lockstep.",
], "OrderManager: twin note")
save(path, L)
print("  -> %d lines\n" % len(L))

# ----------------------------------------------------------------------
# OttoDefines.mqh -- the v5.63 tombstone promised a LOCAL tie-breaker; v5.67
# removes that too, so the note must stop claiming HiveMind() still runs.
# ----------------------------------------------------------------------
path, L = load("OttoDefines.mqh")
print("OttoDefines.mqh (%d lines)" % len(L))
assert L[440].startswith(b"// v5.63 \xe2\x80\x94 CURRENCY-VECTOR PURGE."), L[440]
assert L[450] == b"// v5.63 removes, so the whole module goes. HiveMind() now resolves a", L[450]
assert L[451] == b"// bidirectional conflict from THIS chart's own block votes and nothing else.", L[451]
replace(L, 451, 452, [
    b"// v5.63 removes, so the whole module goes.",
    b"//",
    b"// v5.67 finishes the job: the LOCAL HiveMind() tie-breaker that (2) left",
    b"// behind is deleted too, with the two single-caller helpers it depended on,",
    b"// MappedZoneDirection() and COttoBlockManager::DeleteBlockType(). Nothing now",
    b"// arbitrates one polarity against the other: each chart trades its own zones,",
    b"// and when both sides of a live conflict actually fill, the structural flip",
    b"// (SAR) closes the loser at fill time instead of deleting it before it arms.",
], "OttoDefines: v5.63 tombstone amended")
save(path, L)
print("  -> %d lines\n" % len(L))

# ----------------------------------------------------------------------
# README.md -- record the removal above the v5.63 entry (newest first).
# Em-dash stays real UTF-8 (e2 80 94) to match the surrounding prose.
# ----------------------------------------------------------------------
path, L = load("README.md")
print("README.md (%d lines)" % len(L))
DASH = b"\xe2\x80\x94"
assert L[24] == b"", L[24]
assert L[25] == b"### Removed in v5.63 " + DASH + b" auxiliary veto layer", L[25]
new = [
    b"### Removed in v5.67 " + DASH + b" residual local tie-breaker",
    b"",
    b"`HiveMind()` (the per-chart bidirectional conflict arbiter) is deleted, with",
    b"the two helpers it alone called: `MappedZoneDirection()` in `otto.mq5` and",
    b"`COttoBlockManager::DeleteBlockType()`. Support and Resistance zones may now",
    b"arm at the same time; if both sides fill, the structural flip (SAR) resolves",
    b"the opposing position at fill time. No chart arbitrates one zone against",
    b"another any more.",
    b"",
]
L[25:25] = new
save(path, L)
print("  -> %d lines (+%d)\n" % (len(L), len(new)))

# ----------------------------------------------------------------------
# _probe/test_v563_noveto.py -- the checks that asserted HiveMind() EXISTS
# must invert, or the probe fails on the release that removes it.
# ----------------------------------------------------------------------
path, L = load("_probe/test_v563_noveto.py")
print("test_v563_noveto.py (%d lines)" % len(L))
assert L[259] == b'    hm = body(MAIN_C, "void HiveMind(")', L[259]
assert L[269] == b'              "majority Long -> kept Resistance" in hm)', L[269]
replace(L, 260, 270, [
    b"    # v5.67 removes the residual LOCAL tie-breaker as well, so these",
    b"    # assertions run inverted: the arbiter and its helpers must be gone,",
    b"    # while the structural flip that replaces it must survive.",
    b'    check("HiveMind() is no longer defined",',
    b'          body(MAIN_C, "void HiveMind(") is None)',
    b'    check("its single-caller helpers are gone too",',
    b'          "MappedZoneDirection" not in MAIN_C and',
    b'          "DeleteBlockType" not in BM_C)',
    b'    check("no live code broadcasts or resolves a cross-chart bias",',
    b'          "BroadcastBias" not in MAIN_C and',
    b'          "ResolveBidirectionalConflict" not in MAIN_C)',
    b'    check("its log namespace is gone from the shipped source",',
    b'          "[HiveMind]" not in MAIN_T)',
    b'    check("the structural flip that resolves an opposing fill survives",',
    b'          "SetVeto(i, VETO_FLIPPED)" in BM_C)',
], "probe: invert HiveMind assertions")
save(path, L)
print("  -> %d lines\n" % len(L))
print("done")

