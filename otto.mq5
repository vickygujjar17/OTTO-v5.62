//+------------------------------------------------------------------+
//|                                                       OttoEA.mq5 |
//|                    OTTO — Goat Funded Trader (GFT) Master Build    |
//|                    Pine Script Master Build Port (v5.71)            |
//|                                    Institutional / Real-Money    |
//+------------------------------------------------------------------+
#property copyright "OTTO EA - Goat Funded Trader (GFT) Master Build"
#property version   "5.71"
#property description "OTTO EA â€” Goat Funded Trader (GFT) Master Build"
#property description "Structural vetoes only: Separation | Sizing | Broken | Flipped"
#property description "Modules: Risk | Block Manager | Order Mgmt | Trail"
#property link      "https://github.com/vickygujjar17/OTTO-v5.27"

//+------------------------------------------------------------------+
//| Includes                                                          |
//+------------------------------------------------------------------+
#include <Trade\Trade.mqh>
#include <Otto/OttoDefines.mqh>
#include <Otto/COttoRiskManager.mqh>
#include <Otto/COttoMarketStructure.mqh>
#include <Otto/COttoBlockManager.mqh>
#include <Otto/COttoOrderManager.mqh>
#include <Otto/COttoTradeManager.mqh>
#include <Otto/COttoJournal.mqh>
#include <Otto/CHighTableAuditor.mqh>
// v5.63: COttoNewsFilter.mqh and COttoCorrelationFilter.mqh are no longer
// included. Both were auxiliary veto machinery (calendar blackout, portfolio
// currency-vector consensus) rather than parts of the structural engine, and
// both are deleted from the tree. v5.67 then removed the residual per-chart
// HiveMind() tie-breaker, so nothing here arbitrates one zone against another.

//+------------------------------------------------------------------+
//| Global Module Instances                                           |
//+------------------------------------------------------------------+
COttoRiskManager       g_riskManager;
COttoMarketStructure   g_marketStructure;
COttoBlockManager      g_blockManager;
COttoOrderManager      g_orderManager;
COttoTradeManager      g_tradeManager;
COttoJournal           g_journal;
CHighTableAuditor      g_highTable;

//+------------------------------------------------------------------+
//| Global State                                                      |
//+------------------------------------------------------------------+
string   g_symbol;
bool     g_isHedging        = false;
bool     g_initialized      = false;
int      g_tickCount        = 0;
datetime g_lastStatusLog    = 0;
int      g_fileHandle       = INVALID_HANDLE;
string   g_logFileName      = "";

// --- Human-readable trade journal ---
int      g_journalHandle    = INVALID_HANDLE;
string   g_journalFileName  = "";
long     g_lastPlacedCount  = 0;   // last-seen OrderManager GetOrdersPlaced()
long     g_lastFilledCount  = 0;   // last-seen GetOrdersFilled()
long     g_lastRejectedCount= 0;   // last-seen GetOrdersRejected()
long     g_lastHalfRisk     = 0;   // last-seen GetHalfRiskTriggers()
long     g_lastBE           = 0;   // last-seen GetBreakevenTriggers()
long     g_lastTrail        = 0;   // last-seen GetTrailActivations()
bool     g_lastHadTrade     = false;

// --- High Table fact ingress (v5.32) ---
// The auditor is deliberately decoupled: it holds no COtto* reference and
// reads terminal state only. Two facts it cannot derive from the terminal
// are therefore PUSHED to it every audit cycle - the live drawdown anchors
// (which are this file's private GlobalVariable-backed state) and the trade
// the order layer believes it is driving. The counters below are the
// push-side high-water marks used to turn the order manager's monotonic
// totals into the per-cycle DELTAS the auditor escalates on.
long     g_htPushedRejects    = 0;   // GetOrdersRejected() at last push
long     g_htPushedStopFails  = 0;   // GetStopModifyFailures() at last push

// --- Market-day counter (Pine ta.change(time("D")) mirror) ---
int      g_marketDay        = 0;
datetime g_lastDailyBarTime = 0;
datetime g_lastBarTime      = 0;

// v5.69 — PROP-FIRM DRAWDOWN LAYER PURGED.
// Removed from this file, with no replacement:
//   g_initialBalance / g_dailyResetBalance / g_initialBalance re-seeding
//   g_equityHighWaterMark  (trailing-DD basis)
//   g_lastMidnightCheck    (00:00 server-time reset clock)
//   g_dailyDD_Paused / g_totalDD_Halted / g_dailyDD_ResumeTime  (latches)
//   the OttoGv* GlobalVariable helpers and PersistSafetyState()
//   MostRecentServerMidnight() and CheckDailyReset()
//   the whole STEP 0 safety block in OnTick (equity HWM ratchet, 3% daily
//   pause, 5% trailing halt, CancelAllPendingOrders + CloseEntireBasket on
//   breach) and the audit-side mirror in CHighTableAuditor.
//
// Sizing is now PURE EQUITY-BASED: RiskPercent% of live equity, with no
// drawdown circuit breaker, no persistence, and no cross-restart state. The
// EA holds nothing in the terminal's GlobalVariable store, so a VPS restart
// cannot resurrect a stale pause/halt or a stale high-water mark.

//+------------------------------------------------------------------+
//| int OnInit(void)
//+------------------------------------------------------------------+
int OnInit(void)
  {
   g_symbol = _Symbol;

   Print("==============================================================");
   Print("  OTTO EA v5.71 — 28-Pair Institutional Master Build — INITIALIZING");
   Print("  Symbol: ", g_symbol, " | Magic: ", MagicNumber);
   Print("==============================================================");

   // --- Validate Hedging Account ---
   ENUM_ACCOUNT_MARGIN_MODE marginMode = (ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   if(marginMode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      Print("FATAL: OTTO requires HEDGING account mode!");
      Print("Current mode: ", EnumToString(marginMode));
      return INIT_FAILED;
     }
   g_isHedging = true;
   Print("[INIT] Account type: HEDGING");

   // --- GOLD DEPLOYMENT KILL-SWITCH ---------------------------------
   // OTTO is strictly forbidden from executing on Gold. The instrument's
   // volatility profile and tick-value characteristics invalidate the
   // Pine-derived separation/sizing model this build is calibrated on, and
   // its stop distances routinely breach broker minimums -- so a Gold chart
   // is refused outright rather than run in a degraded mode.
   // v5.63: the "correlation tracking for externally-held Gold" note is
   // removed with the vector engine -- there is no correlation module left
   // to read an external book, so the kill-switch simply refuses Gold.
   string symUpper = g_symbol;
   StringToUpper(symUpper);
   if(StringFind(symUpper, "XAU") >= 0 || StringFind(symUpper, "GOLD") >= 0)
     {
      Print("==============================================================");
      Print("  FATAL: OTTO is FORBIDDEN from executing on Gold charts.");
      Print("  Symbol detected: ", g_symbol);
      Print("  This EA must not trade XAU* / GOLD*." );
      Print("  Move the EA to a permitted instrument and re-initialise.");
      Print("==============================================================");
      return INIT_FAILED;
     }
   Print("[INIT] Gold kill-switch: ", g_symbol, " permitted");

   Print("[INIT] Balance: ", DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
         " | Equity: ", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2),
         " | Free: ", DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2));

   // --- News Filter: REMOVED (v5.63) ---------------------------------
   // The shield module is deleted; there is nothing to initialise and no
   // calendar handle to release.

   // --- Risk Manager ---
   if(!g_riskManager.Initialize(g_symbol))
     {
      Print("[INIT] FATAL: Risk Manager init failed");
      return INIT_FAILED;
     }
   Print("[INIT] Risk Manager OK");

   // --- Market Structure (pivots) ---
   if(!g_marketStructure.Initialize(g_symbol))
     {
      Print("[INIT] FATAL: Market Structure init failed");
      return INIT_FAILED;
     }
   Print("[INIT] Market Structure OK");

   // --- Block Manager ---
   if(!g_blockManager.Initialize(g_symbol, &g_marketStructure))
     {
      Print("[INIT] FATAL: Block Manager init failed");
      return INIT_FAILED;
     }
   Print("[INIT] Block Manager OK");

   // --- Startup historical warm-up: populate blocks from past pivots ---
   g_blockManager.WarmUpHistory();
   Print("[INIT] Warm-up complete — blocks now on chart: ",
         g_blockManager.GetBlockCount());


   // --- Correlation Filter: REMOVED (v5.63) --------------------------
   // The currency-vector engine is deleted, so there is no consensus to
   // refresh and no Hive-Mind tie-breaker to consult.

   // --- Order Manager ---
   if(!g_orderManager.Initialize(g_symbol, &g_riskManager, &g_blockManager))
     {
      Print("[INIT] FATAL: Order Manager init failed");
      return INIT_FAILED;
     }
   Print("[INIT] Order Manager OK");

// --- Trade Journal (human-readable .txt lifecycle log) ---
   g_journal.Initialize(g_symbol, &g_blockManager);
   g_orderManager.SetJournal(&g_journal);


   // --- Trade Manager ---
   if(!g_tradeManager.Initialize(g_symbol, &g_riskManager, &g_orderManager, &g_blockManager))
     {
      Print("[INIT] FATAL: Trade Manager init failed");
      return INIT_FAILED;
     }
   Print("[INIT] Trade Manager OK");

   // --- High Table watchdog -----------------------------------------
   // A separate timer is registered for the audit so the watchdog is not
   // hostage to OnTick: if the trade loop stalls or simply receives no
   // ticks, High Table still runs and can still report a condition that
   // would otherwise go unseen. (v5.69: the trade loop no longer has a
   // halt or pause state to report -- that layer is deleted.)
   if(InpEnableHighTable)
     {
      g_highTable.Initialize(g_symbol, MagicNumber);
      int secs = (InpHighTableAuditSeconds < 1) ? 1 : InpHighTableAuditSeconds;
      EventSetTimer(secs);
      Print("[INIT] High Table OK | audit cadence: ", secs, "s");
     }
   else
      Print("[INIT] High Table DISABLED by input");

   // v5.32 — belt-and-braces rung-liveness warning.
   // The Trade Manager's Initialize() already logs whether the half-risk rung
   // is LIVE or INERT, but that line is gated on EnableLogging. An operator
   // running with logging OFF would otherwise never learn that InpCutRiskRR is
   // configured in a way that makes the -0.5R floor unreachable, so this one is
   // deliberately unconditional: a misconfigured rung is worth one line of
   // terminal output even in silent mode.
   if(InpCutRiskRR >= InpBreakEvenRR)
      Print("[INIT] NOTE: InpCutRiskRR (", DoubleToString(InpCutRiskRR,2),
            ") is not below InpBreakEvenRR (", DoubleToString(InpBreakEvenRR,2),
            ") -> the -0.5R half-risk rung is UNREACHABLE and will never be",
            " applied or journalled. Set InpCutRiskRR below InpBreakEvenRR to arm it.");

   // v5.69: the prop-firm safety state block that stood here (persistent daily
   // reset anchor, trailing equity high-water mark, halt/pause latches, all
   // restored from MT5 GlobalVariables) is DELETED along with the inputs and
   // the OnTick checks that consumed it. Nothing below depends on it and no
   // drawdown baseline is seeded at init any more.

   // --- Market-day counter init (mirrors ta.change(time("D"))) ---
   g_lastDailyBarTime = iTime(_Symbol, PERIOD_D1, 0);
   g_marketDay        = 0;
   g_lastBarTime      = iTime(_Symbol, InpPrimaryTF, 0);

   // --- Sync existing trade state ---
   g_tradeManager.SyncTradeState();

   // --- Setup log file ---
   if(EnableLogging)
     {
      g_logFileName = "Otto_" + g_symbol + "_" +
                      IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ".csv";
      g_fileHandle  = FileOpen(g_logFileName, FILE_CSV | FILE_WRITE | FILE_SHARE_READ, ',');
      if(g_fileHandle != INVALID_HANDLE)
        {
         FileWrite(g_fileHandle, "Time", "Symbol", "Event", "Details");
         Print("[INIT] Log file: ", g_logFileName);
        }
      else
         Print("[INIT] WARNING: Could not create log file");
     }

// --- Setup human-readable trade journal ---
   if(EnableJournal)
     {
      g_journalFileName = "Otto_Journal_" + g_symbol + "_" +
                          IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ".txt";
      g_journalHandle   = FileOpen(g_journalFileName, FILE_TXT | FILE_WRITE | FILE_SHARE_READ | FILE_ANSI);
      if(g_journalHandle != INVALID_HANDLE)
        {
         FileWriteString(g_journalHandle, "OTTO EA - Trade Journal\n");
         FileWriteString(g_journalHandle, "Symbol: " + g_symbol + " | Started: " + TimeToString(TimeCurrent()) + "\n");
         FileWriteString(g_journalHandle, "------------------------------------------------------------------\n");
         Print("[INIT] Journal file: ", g_journalFileName);
        }
      else
         Print("[INIT] WARNING: Could not create journal file");
     }
   g_initialized = true;

   Print("==============================================================");
   Print("  OTTO EA INITIALIZED SUCCESSFULLY");
   Print("  Risk: ", DoubleToString(RiskPercent,2), "% dynamic equity"
         " (=$", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY) * RiskPercent / 100.0, 2), ")",
         " | Ladder: T1 ", DoubleToString(RiskPercent,2), "% / T2 ", DoubleToString(InpRiskT2Pct,2),
         "% / T3 ", DoubleToString(InpRiskT3Pct,3), "% / T4 ", DoubleToString(InpRiskT4Pct,3), "%");
   Print("==============================================================");

   return INIT_SUCCEEDED;
  }


//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Print("==============================================================");
   Print("  OTTO EA â€” DEINITIALIZING (reason ", reason, ")");

   // v5.63: the "--- News Filter ---" block (Blackouts count) is gone with
   // the shield module.
   Print("  --- Block Manager ---");
   Print("  Created: ", g_blockManager.GetBlocksCreated(),
         " | Broken: ", g_blockManager.GetBlocksBroken(),
         " | Vetoed: ", g_blockManager.GetBlocksVetoed());
   Print("  --- Order Manager ---");
   Print("  Placed: ", g_orderManager.GetOrdersPlaced(),
         " | Filled: ", g_orderManager.GetOrdersFilled(),
         " | Rejected: ", g_orderManager.GetOrdersRejected());
   Print("  --- Trade Manager ---");
   Print("  HalfRisk: ", g_tradeManager.GetHalfRiskTriggers(),
         " | BE: ", g_tradeManager.GetBreakevenTriggers(),
         " | Trail: ", g_tradeManager.GetTrailActivations());

   // Cancel all pending orders
   int pending = g_orderManager.CountMyPending();
   if(pending > 0)
     {
      Print("  Cancelling ", pending, " pending orders...");
      g_orderManager.CancelAllPendingOrders();
     }

   // --- High Table watchdog -----------------------------------------
   // The timer MUST be killed here: OnDeinit runs on every parameter
   // change, timeframe switch and recompile, and leaving the timer alive
   // would stack a new cadence on top of the old one each re-init.
   EventKillTimer();
   g_highTable.Deinit();

   // Close log file
   if(g_fileHandle != INVALID_HANDLE)
     {
      FileClose(g_fileHandle);
      g_fileHandle = INVALID_HANDLE;
     }
// Close journal file
   if(g_journalHandle != INVALID_HANDLE)
     {
      FileClose(g_journalHandle);
      g_journalHandle = INVALID_HANDLE;
     }
   g_journal.Close();   // COttoJournal detailed .txt journal

   g_initialized = false;
   Print("==============================================================");
  }

//+------------------------------------------------------------------+
//| Daily reset clock — REMOVED (v5.69)                              |
//|                                                                  |
//| MostRecentServerMidnight() and CheckDailyReset() are deleted with |
//| the prop-firm drawdown layer they served. Nothing in this build   |
//| re-anchors on a 00:00 server-time boundary: sizing reads live     |
//| equity at order time, so there is no daily budget to reset.       |
//| The market-day counter below is independent -- it keys off        |
//| iTime(_Symbol, PERIOD_D1, 0) and never touched these helpers.     |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| New-bar detection â€” gates the block formation + veto funnel      |
//+------------------------------------------------------------------+
//| v5.66: keyed on InpPrimaryTF (default H1 as of v5.71), NOT the  |
//| chart period, so the funnel follows the primary TF, not the      |
//| chart. The gate therefore fires once an HOUR by default.        |
bool IsNewBar(void)
  {
   datetime barTime = iTime(_Symbol, InpPrimaryTF, 0);
   if(barTime == g_lastBarTime)
      return false;
   g_lastBarTime = barTime;
   return true;
  }

//+------------------------------------------------------------------+
//| Market-day counter â€” increments when the daily bar changes.      |
//| Weekends are naturally skipped (no daily bars on Sat/Sun). This  |
//| mirrors Pine ta.change(time("D")).                               |
//+------------------------------------------------------------------+
void UpdateMarketDay(void)
  {
   datetime dailyBar = iTime(_Symbol, PERIOD_D1, 0);
   if(dailyBar != g_lastDailyBarTime)
     {
      g_marketDay++;
      g_lastDailyBarTime = dailyBar;
     }
  }

//+------------------------------------------------------------------+
//| Expert tick function â€” Main Orchestration Loop                   |
//+------------------------------------------------------------------+
void OnTick(void)
  {
   if(!g_initialized) return;

   g_tickCount++;

   // ================================================================
   // STEP 0: PROP FIRM SAFETY CHECKS — REMOVED (v5.69)
   // The 3% daily-DD pause, the 5% trailing-DD halt, the equity
   // high-water ratchet, the restart persistence layer and the
   // breach-path CancelAllPendingOrders/CloseEntireBasket are all
   // deleted. OnTick no longer consults any drawdown state and has no
   // early return between init and block processing: sizing is pure
   // equity-based (RiskPercent% of live equity at order time).
   // ================================================================

   // ================================================================
   // STEP 1: NEWS FILTER — REMOVED (v5.63)
   // The shield module is deleted. There is no calendar query, no
   // blackout latch and no news state consulted anywhere in OnTick.
   // ================================================================

   // ================================================================
   // STEP 2: NEW BAR â€” block formation + veto funnel (bar-close logic)
   // Mirrors calc_on_every_tick=false.
   // ================================================================
   if(IsNewBar())
     {
      UpdateMarketDay();               // advance the trading-day counter

      // Cancel orders on freshly-invalidated blocks BEFORE the funnel reaps them
      g_orderManager.CancelOrdersForInvalidBlocks();

      // Run the funnel (W1/W2 formation + all v4.70 vetoes)
      g_blockManager.Update(g_marketDay);

      // Cancel any orders declared invalid during this bar's funnel
      g_orderManager.CancelOrdersForInvalidBlocks();
     }


   // ================================================================
   // STEP 3: INTRA-BAR CHECKS - RETIRED (v5.63)
   // The only intra-bar vetoes were the Front-Run target re-check and
   // the 6-day Near-Miss expiry. Both are purged, so this step now
   // does nothing. CheckVetoesInTick() is retained as a no-op seam;
   // block invalidation is still acted on below by
   // CancelOrdersForInvalidBlocks(), because ProcessBlocks() on the new
   // bar can veto a block structurally (BROKEN / FLIPPED / SIZING /
   // NO_SEPARATION).
   // ================================================================
   g_blockManager.CheckVetoesInTick(g_marketDay);
   g_orderManager.CancelOrdersForInvalidBlocks();

   // ================================================================
   // STEP 3b: CURRENCY-VECTOR CONSENSUS - REMOVED (v5.63)
   // The refresh and the opposing-pending sweep belonged to the vector
   // engine, which is deleted. Nothing in this cycle now reads another
   // chart's book, and no pending order is cancelled on consensus.
   // ================================================================

   // ================================================================
   // STEP 4: ORDER PLACEMENT - Pine-gated limit orders for armed blocks
   // Gated by the block's own structural veto state only. v5.63: the
   // news-blackout gate is gone with the shield. v5.69: the daily-DD
   // pause gate is gone with the prop-firm drawdown layer, so placement
   // is unconditional here -- nothing above this line can park it.
   // ================================================================

   // Every armed block routes through the single hybrid engine:
   // PlaceOrdersForArmedBlocks() ARMS the order -- a resting broker limit
   // when the price permits one, else an in-memory virtual order -- and the
   // order manager's CheckVirtualTriggers() FIRES the MARKET leg once the
   // continuation level trades through. v5.52 has no per-phase split.
   g_orderManager.PlaceOrdersForArmedBlocks();

   // ================================================================
   // STEP 5: MANAGE ACTIVE TRADES â€” dynamic trail (every tick)
   // ================================================================
   g_tradeManager.Update();

   // ================================================================
   // STEP 6: ORDER LIFECYCLE â€” fill detection + reversal completion
   // ================================================================
   g_orderManager.Update();

   // ================================================================
   // STEP 7: DIRECTION CONFLICT â€” cancel same-direction pending orders
   // ================================================================
   g_orderManager.ManageDirectionConflict();

// ================================================================
   // STEP 7B: TRADE JOURNAL — one-shot human-readable event log
   // ================================================================
   if(EnableJournal)
      JournalCheckEvents();
   // ================================================================
   // STEP 8: PERIODIC STATUS LOGGING
   // ================================================================
   if(EnableLogging && TimeCurrent() - g_lastStatusLog >= 3600)
     {
      LogStatus();
      g_lastStatusLog = TimeCurrent();
     }
  }

//+------------------------------------------------------------------+
//| Periodic status logging to console and file                      |
//+------------------------------------------------------------------+
void LogStatus(void)
  {
   string statusLine;
   StringConcatenate(statusLine,
                     "[STATUS] Day=", g_marketDay,
                     " | Blocks: ", g_blockManager.GetBlockCount(),
                     " | ActiveTrade: ", g_orderManager.HasActiveTrade() ? "YES" : "NO",
                     " | Pending: ", g_orderManager.CountMyPending(),
                     " | ATR: ", DoubleToString(g_blockManager.GetATR(), _Digits));
   Print(statusLine);
   if(g_fileHandle != INVALID_HANDLE)
     {
      FileWrite(g_fileHandle, TimeToString(TimeCurrent()), g_symbol, "STATUS", statusLine);
      FileFlush(g_fileHandle);
     }
  }

//+------------------------------------------------------------------+
//| Writes a line to the human-readable .txt trade journal            |
//+------------------------------------------------------------------+
void JournalWrite(string event, string details)
  {
   if(g_journalHandle == INVALID_HANDLE) return;
   string line = TimeToString(TimeCurrent()) + "  | " + event + "  | " + details;
   FileWriteString(g_journalHandle, line + "\n");
   FileFlush(g_journalHandle);
  }

//+------------------------------------------------------------------+
//| One-shot journal hooks for the EA's OnTick (counter-diff based)  |
//+------------------------------------------------------------------+
void JournalCheckEvents(void)
  {
   // --- NEW ORDER(S) PLACED ---
   long placed = g_orderManager.GetOrdersPlaced();
   if(placed > g_lastPlacedCount)
     {
      g_lastPlacedCount = placed;
      JournalWrite("ORDER PLACED", "pending count now " + IntegerToString((int)placed));
     }

   // --- FILLED ---
   long filled = g_orderManager.GetOrdersFilled();
   if(filled > g_lastFilledCount)
     {
      g_lastFilledCount = filled;
      JournalWrite("FILLED", "");
     }

   // --- REJECTED ---
   long rejected = g_orderManager.GetOrdersRejected();
   if(rejected > g_lastRejectedCount)
     {
      g_lastRejectedCount = rejected;
      JournalWrite("REJECTED", "");
     }

   // --- TRADE MANAGER STEP CHANGES ---
   int halfRisk = g_tradeManager.GetHalfRiskTriggers();
   if(halfRisk > g_lastHalfRisk)
     { g_lastHalfRisk = halfRisk; JournalWrite("SL -> HALF-RISK", "risk now -0.5R"); }

   int be = g_tradeManager.GetBreakevenTriggers();
   if(be > g_lastBE)
     { g_lastBE = be; JournalWrite("SL -> +0.75R PROFIT LOCK", ""); }

   int trail = g_tradeManager.GetTrailActivations();
   if(trail > g_lastTrail)
     { g_lastTrail = trail; JournalWrite("SL -> DYNAMIC TRAIL ACTIVE", ""); }

   // --- TRADE CLOSED (active->flat transition) ---
   bool nowActive = g_orderManager.HasActiveTrade();
   if(g_lastHadTrade && !nowActive)
     JournalWrite("TRADE CLOSED", "");
   g_lastHadTrade = nowActive;
  }

//+------------------------------------------------------------------+
//| OnTrade â€” re-sync active trade state on trade events             |
//+------------------------------------------------------------------+
void OnTrade(void)
  {
   if(g_initialized)
      g_orderManager.SyncActiveTrade();
  }

//+------------------------------------------------------------------+
//| OnTimer - High Table watchdog cadence                             |
//|                                                                   |
//| Deliberately OUTSIDE the OnTick guard chain: OnTick returns early |
//| when the EA is halted or daily-paused, and those are precisely the |
//| states that most need to be reported. RunAudit() reads terminal    |
//| state only and holds no reference to any trade module, so it can   |
//| run while the trade loop is stopped without touching it.           |
//+------------------------------------------------------------------+
void OnTimer(void)
  {
   if(!g_initialized) return;
   if(!InpEnableHighTable) return;
   HighTablePushFacts();       // v5.32: hand over the facts only we can see
   g_highTable.RunAudit();
  }

//+------------------------------------------------------------------+
//| High Table fact ingress (v5.32)                                   |
//|                                                                   |
//| Called from OnTimer immediately before RunAudit(). It hands the    |
//| auditor the one fact it cannot read for itself:                   |
//|                                                                   |
//|   1. The trade the order layer believes it is driving, so the      |
//|      auditor can test that belief against the real book.           |
//|
//| v5.69: the second fact -- the live drawdown anchors (daily reset  |
//| balance, equity high-water mark, permanent halt latch) -- is gone. |
//| Those anchors no longer exist anywhere in the tree, so there is   |
//| nothing to push and CHighTableAuditor::SetSafetyBaseline() is      |
//| deleted with the AuditDrawdown() body that consumed it.            |
//|                                                                   |
//| The push points that remain are read-only calls on the trade       |
//| modules: the auditor still holds no reference to them, which is    |
//| what keeps the decoupling contract intact (see the module header). |
//|                                                                   |
//| The counters are pushed as DELTAS because GetOrdersRejected() and  |
//| GetStopModifyFailures() are monotonic lifetime totals; the push    |
//| advances its own high-water mark so no failure is counted twice.   |
//+------------------------------------------------------------------+
void HighTablePushFacts(void)
  {
   // --- Order-reject delta since the previous push ---
   long rejects = g_orderManager.GetOrdersRejected();
   if(rejects > g_htPushedRejects)
     {
      g_highTable.NotifyOrderReject(0, "order placement", (int)(rejects - g_htPushedRejects));
      g_htPushedRejects = rejects;
     }

   // --- SL-modify failure delta since the previous push ---
   long stopFails = g_orderManager.GetStopModifyFailures();
   if(stopFails > g_htPushedStopFails)
     {
      g_highTable.NotifyStopModifyFailure(0, 0, (int)(stopFails - g_htPushedStopFails));
      g_htPushedStopFails = stopFails;
     }

   // --- The trade the order layer believes it is driving ---
   // The ticket is taken from the order layer rather than from the book on
   // purpose: the point of the check is to compare the manager's BELIEF
   // against reality, so both halves must come from independent sources.
   SActiveTrade active;
   ulong ticket  = 0;
   bool  adopted = false;
   if(g_orderManager.GetActiveTradeRef(active))
     {
      ticket = active.ticket;
      // v5.33: tell the auditor when the tracked primary is an ADOPTED
      // manual (magic-0) leg. The auditor's book-vs-tracked test is
      // intentionally magic-scoped -- CountBookLegs() and BookHasTicket()
      // both look only at positions carrying m_magic -- so an adopted
      // primary is invisible to it BY CONSTRUCTION. Without this flag the
      // auditor would latch its two-cycle "book/tracked state desync"
      // alert for the entire life of the adopted trade: a false CRITICAL
      // in the loudest channel the EA owns, which would in turn train the
      // operator to ignore it. The flag is read from the manager rather
      // than re-derived from POSITION_MAGIC here so the book is still read
      // in exactly one place.
      adopted = active.adoptedManual;
     }
   g_highTable.SetTrackedLegs(g_orderManager.CountOpenPositions(),
                              ticket, g_orderManager.HasActiveTrade(),
                              adopted);
  }

