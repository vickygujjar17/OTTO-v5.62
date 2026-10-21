# OTTO EA

MetaTrader 5 Expert Advisor — MQL5 port of the Pine Script `prop_guard_tester.pine`
master build. **Current base: v5.70**

> **Primary timeframe: `PERIOD_M15`** (`InpPrimaryTF`). Pivot detection,
> block formation and the ATR handle all read the primary TF, so the EA is
> chart-independent: attach it to any chart and structure is still computed
> on M15. Bar-count inputs (`MaxBlockDistance`, `LookbackBars`) are counted
> in primary-TF bars, so they rebase when the TF changes.

## Layout

| File | Role |
|---|---|
| `OttoDefines.mqh` | Central enums, structs and `input` parameters |
| `COttoRiskManager.mqh` | Position sizing / risk |
| `COttoMarketStructure.mqh` | Market-day counter, structure helpers |
| `COttoBlockManager.mqh` | Wick1+Wick2 S/R block lifecycle and structural vetoes |
| `COttoOrderManager.mqh` | Order placement, pyramiding basket, journal hooks |
| `COttoTradeManager.mqh` | Cut / cost-BE / lock3 / ATR trail / pyramiding |
| `COttoJournal.mqh` | Human-readable trade journal |
| `CHighTableAuditor.mqh` | "High Table" decoupled watchdog: CSV audit trail + latched email alerts |
| `otto.mq5` | EA entry point and event handlers |

### Removed in v5.67 — residual local tie-breaker

`HiveMind()` (the per-chart bidirectional conflict arbiter) is deleted, with
the two helpers it alone called: `MappedZoneDirection()` in `otto.mq5` and
`COttoBlockManager::DeleteBlockType()`. Support and Resistance zones may now
arm at the same time; if both sides fill, the structural flip (SAR) resolves
the opposing position at fill time. No chart arbitrates one zone against
another any more.

### Removed in v5.63 — auxiliary veto layer

`COttoNewsFilter.mqh` (calendar blackout) and `COttoCorrelationFilter.mqh`
(currency-vector consensus + cross-chart Hive-Mind arbiter) are deleted. With
them go the Front-Run, Stale 45D, Near-Miss 6D, Momentum and FVG vetoes. What
survives is the structural funnel only: **Separation, Sizing, Broken, Flipped**.
Their `input` declarations remain as labelled no-ops so existing `.set` files
still load.

### Changed in v5.70 — non-monotonic risk tiers, +0.75R profit lock at +1.0R

**The ladder deepens at the confirmed rung, then tapers.** v5.69 was a strict
geometric cascade that halved every rung. v5.70 inverts the top of that shape:
T1 is now the **probe** — the only rung taken before the setup has proven
anything — and T2 carries the largest allocation, because it is only reached at
`+1.0R` with the basket already wearing a `+0.75R` floor.

| Rung | Trigger | v5.69 | v5.70 |
|---|---|---|---|
| T1 `RiskPercent` | at market | 1.0% | **0.5%** |
| T2 `InpRiskT2Pct` | `+1.0R` | 0.5% | **1.0%** |
| T3 `InpRiskT3Pct` | `+2.0R` | 0.25% | **0.5%** |
| T4 `InpRiskT4Pct` | `+3.0R` | 0.125% | **0.25%** |
| *summed stacked* | | *1.875%* | ***2.25%*** |

> **The ladder is no longer monotonic, and that is the point.** The shape is
> `0.5 → 1.0 → 0.5 → 0.25`: the peak sits at T2 and the ladder tapers below it.
> The v5.69 "descends strictly" and "each rung is half" assertions were
> **deleted rather than softened** — they encoded the retired cascade and no
> correct v5.70 tree can satisfy them. `_probe/test_v570_ladder.py` (renamed
> from `test_v569_ladder.py`) replaces them with the weaker ordering that
> actually survives: `T2 > T1`, `T2 > T3 > T4`, plus an explicit negative
> assertion that a geometric cascade has *not* been restored.

**The `+1.0R` rung now locks `+0.75R` of profit instead of parking at
cost-covering breakeven.** A new input `InpBEProfitLockRR = 0.75` names the
target; `InpBreakEvenRR` still names the `R` at which the rung fires. Cost
covering is preserved as a **floor**, not discarded: each branch takes
`MathMax(lock, friction)` on a LONG (`MathMin` on a SHORT), so a pathologically
tight 1R still falls back to covering commission + swap + half-spread rather
than booking a loss on a winner. `CalcBasketFriction()` therefore stays live.

The `+1.0R` branch's old outer guard (`desiredSL < primaryEntry`) is gone. It
would have skipped the lock for any stop already ratcheted to somewhere between
entry and `+0.75R`, leaving the basket under-locked; the forward-only test
(`desiredSL < beSL`) is now the only gate. The T2 fill carries the same `+0.75R`
level as its `slOverride` and is clamped against the live session stop, so the
**largest** rung is no longer born wearing the **loosest** stop — the inversion
v5.61 fixed for T3.

**The auditor's per-leg ceiling is re-anchored on the peak rung.** It was
`RiskPercent * 1.50`, which on this ladder would be `0.5 * 1.5 = 0.75%` — below
the 1.0% T2 leg, so it would have fired a false "position risk breach" on every
healthy pyramid. It now uses `max(T1,T2,T3,T4) * 1.50`, which is **1.5%**,
numerically identical to v5.69: the watchdog neither loosens nor tightens here,
only its anchor moves.

Only **lots and money** move. Every scale-in trigger, profit-lock rung and ATR
trail activation is still an **R-multiple** of the primary's own 1R, so no price
level changes and no milestone re-times — except the `+1.0R` rung's *target*,
which is now `+0.75R` by design.

### Changed in v5.69 — T1 restored to a geometric cascade, prop-firm layer stripped

> **Superseded by v5.70.** The geometric cascade described below
> (`1.0 / 0.5 / 0.25 / 0.125`, sum 1.875%) is retired. v5.70 re-tiers the ladder
> to `0.5 / 1.0 / 0.5 / 0.25` (sum 2.25%) and makes the `+1.0R` rung lock
> `+0.75R` rather than park at cost-covering breakeven. The auditor's ceiling
> also stops being `RiskPercent * 1.50` and is anchored on the peak rung
> instead. The prop-firm purge below still stands unchanged.

**T1 is back at 1.0%, and the ladder is now a geometric cascade.** v5.68 halved
every rung, which turned the v5.61+ flat head into `0.5 / 0.5 / 0.25 / 0.125`.
v5.69 restores **only T1** and leaves the three scale-ins exactly where v5.68
put them, so each rung now risks precisely half the rung above it:

| Rung | Trigger | v5.68 | v5.69 |
|---|---|---|---|
| T1 `RiskPercent` | at market | 0.5% | **1.0%** |
| T2 `InpRiskT2Pct` | `+1.0R` | 0.5% | 0.5% *(unchanged)* |
| T3 `InpRiskT3Pct` | `+2.0R` | 0.25% | 0.25% *(unchanged)* |
| T4 `InpRiskT4Pct` | `+3.0R` | 0.125% | 0.125% *(unchanged)* |
| *summed stacked* | | *1.375%* | ***1.875%*** |

> **The flat head is deliberately gone.** Through v5.68 T1 and T2 both risked
> 0.5%, so the head of the ladder was a plateau. It is now a strict cascade
> (1.0 → 0.5 → 0.25 → 0.125): each scale-in is half the size of the leg it
> rides on, which is the shape the four `InpRiskTnPct` **halving ratios** were
> originally tuned for. The probes assert `T1 > T2` strictly, so a future edit
> that re-flattens the head fails instead of sliding through.

Only **lots and money** move. Every scale-in trigger, breakeven floor, profit
lock and ATR trail rung is an **R-multiple** of the primary's own 1R, so no
price level changes and no milestone re-times. The per-leg risk ceiling moves
with T1 for free because it is **derived**, not configured: the High Table
auditor computes `maxAllowedRiskPct = RiskPercent * 1.50`, so it is 1.5% on this
ladder and would track T1 through any future retune.

### Removed in v5.69 — the prop-firm drawdown layer

Sizing is now **pure equity-based**: `RiskPercent`% of live equity at order time,
with **no drawdown circuit breaker of any kind**. Deleted outright, with no
no-op stubs left behind:

- **Daily drawdown pause** — the 3% soft breach that cancelled pending orders
  and blocked new placement for the rest of the session.
- **Trailing total-drawdown halt** — the 5% hard breach that closed the whole
  basket, cancelled every pending order and permanently halted the EA.
- **00:00 reset clock** — `CheckDailyReset()` / `MostRecentServerMidnight()`
  and the daily re-anchor they existed to perform.
- **MT5 GlobalVariable persistence** — the `OttoGv*` helper family and
  `PersistSafetyState()`. The EA now writes nothing to the terminal's shared
  `GlobalVariable` store, so a VPS restart can no longer resurrect a stale
  pause, a stale halt or a stale high-water mark.
- **The three prop-firm inputs** — `SafetyMaxRiskPct`, `SafetyDailyDDLimit` and
  `SafetyTotalDDLimit`. These were deleted rather than retained as no-ops
  (unlike the v5.63 veto inputs): nothing in the tree ever read any of them, so
  keeping them would only advertise a limit the EA does not enforce.
  `SafetyMaxRiskPct` in particular never reached the auditor — the auditor has
  always derived its own ceiling from `RiskPercent`.
- **The auditor's mirror of all of the above** — `AuditDrawdown()`, the
  `DailyDDPct()` / `TotalDDPct()` measures, the pushed `SetSafetyBaseline()`
  ingress, and the three DD latches. `AuditRiskExposure()` survives: the per-leg
  runaway-size check is not part of the drawdown layer.

The journal and the init banner were retagged to match — the risk-allocation row
now reads `(equity-based)` instead of `(v5.68 baseline)`, the manual-adoption
note no longer lists a "DD halt" among the machinery that applies to an adopted
ticket, and the startup banner prints the ladder without a DD budget column.
`_probe/test_v569_propstrip.py` is a dedicated **absence guard**: it fails if any
of the deleted symbols, functions, inputs or promises come back.

### Changed in v5.68 — risk baseline halved, journal geometry completed

**The initial risk allocation is halved.** All four pyramid rungs moved as one
piece, so the ladder keeps its shape while every absolute number halves:

| Rung | Trigger | v5.67 | v5.68 |
|---|---|---|---|
| T1 `RiskPercent` | at market | 1.0% | **0.5%** |
| T2 `InpRiskT2Pct` | `+1.0R` | 1.0% | **0.5%** |
| T3 `InpRiskT3Pct` | `+2.0R` | 0.5% | **0.25%** |
| T4 `InpRiskT4Pct` | `+3.0R` | 0.25% | **0.125%** |
| *summed stacked* | | *2.75%* | ***1.375%*** |

Only **lots and money** change. Every scale-in trigger, breakeven floor, profit
lock and ATR trail rung is an **R-multiple** of the primary's own 1R, so no
price level moves and no milestone re-times.

> **Superseded by v5.69.** v5.68 also claimed that `SafetyMaxRiskPct` "stays at
> 1.5% on purpose" and that it capped the ladder. That input never capped
> anything — nothing in the tree ever read it — and v5.69 deleted it along with
> the rest of the prop-firm group. The auditor's tolerance was always derived as
> `RiskPercent * 1.50`.

> **Consequence to watch:** a halved target means the v5.49 below-min rule now
> aborts more often on small accounts. It still never clamps up to a fixed lot.

**The journal now carries the full block geometry.** Both `LogSetupArmed()` and
`LogEntry()` print block top / bottom / midpoint / height, and v5.68 adds the
standalone **Block Height** in price *and* pips, the **1R stop distance** in
price *and* pips, and the **risk allocation** actually being committed. Wick
rows now name the pivot `price` that anchored the block, and `LogEntry()` prints
the **realized** fill-to-SL distance beside the planned 1R so a slipped fill is
visible instead of hiding behind the planned number.

## Build (strict gate)

Sources are CRLF and the EA resolves its modules through angle-bracket
includes (`#include <Otto/<file>.mqh>`), so it is compiled from a staged tree
that mirrors the terminal layout (`MQL5\Experts` + `MQL5\Include\Otto`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File _tools\build_check.ps1
```

The gate is only passed on **0 errors, 0 warnings**.

`-Source` defaults to the checkout the script lives in (`$PSScriptRoot\..`), so
the command above needs no editing after a fresh clone; pass
`-Source <dir>` to gate a different tree.

## Line endings

`_tools\normalize_eol.py` rewrites MQL5 sources to strict CRLF byte-safely
(non-ASCII content is preserved exactly):

```powershell
python _tools\normalize_eol.py .            # rewrite
python _tools\normalize_eol.py . --check    # report only
```

## Version policy

Every update bumps `#property version` in **all** `.mqh`/`.mq5` files, the
banner in `OttoDefines.mqh`, the startup `Print()` banner in `otto.mq5`, the
four versioned input-group labels and the README base line.
`_tools\_bump_version.py` performs the rewrite, skipping any line containing
`FIX (` so historical annotations survive. It auto-detects the live release
from `OttoDefines.mqh` (no hardcoded from/to pair to rot) and fails if any
old-release literal is left behind, so a partial bump cannot be committed.

> `#property link` names the GitHub *repository*, not the release, so it is
> intentionally excluded from the bump.

Release steps, in order:

1. Run `python _tools\_bump_version.py` and eyeball the reported diff.
2. Add a `_commitNNN.txt` changelog (title, per-area sections, `VERIFICATION`).
3. Pass the gate: `powershell -NoProfile -ExecutionPolicy Bypass -File _tools\build_check.ps1`
   on **0 errors, 0 warnings**.
4. Commit with the version first in the subject, then the upgrade list:
   `NNN: <area> — <what changed>`. One commit may cover several areas; every
   commit for a release is prefixed with that release's number.
