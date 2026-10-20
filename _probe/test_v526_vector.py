"""
RETIRED (v5.63) -- v5.26 Currency Vector & Affinity Correlation Engine probe.

This probe once pinned the behaviour of COttoCorrelationFilter.mqh: the affinity
matrix, Base/Quote seeding, first-order propagation, DXY/XAU anchor signs, the
maxAbsMovement guard, suffix sanitisation, the -100..+100 consensus threshold
semantics, VETO_CORRELATION, and the TS_Bias_* cross-chart tie-breaker (83
assertions in all).

v5.63 deletes that module outright. The portfolio-consensus veto and the
cross-chart Hive-Mind arbiter were the last pieces of the AUXILIARY VETO LAYER
-- the same layer as Front-Run / Stale 45D / Near-Miss 6D / Momentum / FVG --
and this release exists to strip it so the funnel decides STRUCTURE only.

The file is deliberately KEPT rather than deleted, and reduced to a tombstone:
the record of what the vector engine did is worth more to a future reader than
silence. It runs no checks and exits 0, so the probe census stays honest -- a
retired probe reporting "83/83 GREEN" against a tree with no vector engine
would be the worst possible outcome.

Coverage of the surviving structural funnel lives in test_v563_noveto.py.
"""

import sys

if __name__ == "__main__":
    print("=" * 74)
    print("test_v526_vector.py -- RETIRED (v5.63)")
    print("=" * 74)
    print()
    print("  Subject : COttoCorrelationFilter.mqh -- DELETED in v5.63")
    print("  Reason  : currency-vector consensus veto + cross-chart Hive-Mind")
    print("            tie-breaker both belonged to the auxiliary veto layer.")
    print("  Result  : no checks run. See _tools/_commit563.txt.")
    print()
    print("*** RETIRED - NOT A PASS ***")
    sys.exit(0)
