//+------------------------------------------------------------------+
//|                                            EvalPassMomentum.mq5  |
//|  Intraday momentum ("noise area" breakout) for US index CFDs     |
//|  with a prop-firm risk guard.                                     |
//|                                                                  |
//|  Idea (Zarattini, Aziz & Barbon 2024, "Beat the Market"):         |
//|  around the 09:30 New York open, the index usually wanders inside |
//|  a "noise area" whose width is the average absolute move from the |
//|  open at the same minute over the last N days. When price closes  |
//|  outside that area on a scheduled check, demand/supply imbalance  |
//|  tends to persist -> trade in that direction with a stop of one   |
//|  noise width, a fixed R target, break-even, flat before 16:00 NY. |
//+------------------------------------------------------------------+
#property copyright   "eval-pass"
#property version     "1.10"
#property description "NY-session intraday momentum for NAS100 / US500 with prop-firm guard"

#include <Trade/Trade.mqh>

enum ENUM_STOP_MODE
  {
   STOP_BAND  = 0,   // Band: stop at max(band,VWAP) (long) / min(band,VWAP) (short)
   STOP_SIGMA = 1    // Sigma: fixed multiple of the noise width
  };

enum ENUM_EXIT_MODE
  {
   EXIT_NONE     = 0, // Stop-loss / take-profit / break-even / session end only
   EXIT_BAND     = 1, // Also close when price is back behind the band (or VWAP)
   EXIT_OPPOSITE = 2  // Also close when price crosses the opposite band
  };

enum ENUM_SESSION_TZ
  {
   TZ_NEW_YORK = 0,  // New York (US index cash session, US daylight saving)
   TZ_TOKYO    = 1   // Tokyo (JP225 cash session, UTC+9, no daylight saving)
  };

enum ENUM_DST_MODE
  {
   DST_NONE = 0,     // Server has no daylight saving
   DST_US   = 1,     // US rules (typical GMT+2/+3 "New York close" brokers)
   DST_EU   = 2      // EU rules
  };

//--- strategy
input group "=== Strategy (noise-area momentum) ==="
input int            InpLookbackDays    = 30;         // Days averaged for the noise band
input double         InpBandMult        = 2.0;        // Band width multiplier
input int            InpCheckEveryMin   = 30;         // Signal check interval, minutes
input ENUM_EXIT_MODE InpExitMode        = EXIT_NONE;  // Signal exit at checks
input bool           InpUseVWAP         = false;      // Band exit/stop also uses session VWAP
input ENUM_STOP_MODE InpStopMode        = STOP_SIGMA; // Initial stop-loss placement
input double         InpStopSigma       = 1.0;        // Stop distance in noise widths (Sigma mode)
input double         InpMinStopSigma    = 0.25;       // Minimum stop in noise widths (Band mode)
input double         InpTakeProfitR     = 2.5;        // Take profit in R (0 = none)
input double         InpBETriggerR      = 1.5;        // Move stop to break-even at this R (0 = off)
input double         InpBEOffsetR       = 0.1;        // Break-even stop offset in R
input int            InpMaxTradesPerDay = 3;          // Max entries per New York day
input bool           InpAllowLong       = true;       // Allow long trades
input bool           InpAllowShort      = true;       // Allow short trades

//--- session in New York time (HHMM)
input group "=== Session, New York time (HHMM) ==="
input int            InpOpenHHMM        = 930;        // Cash open
input int            InpCloseHHMM       = 1600;       // Cash close
input int            InpFirstCheckHHMM  = 1000;       // First signal check
input int            InpLastEntryHHMM   = 1530;       // Last check that may open a trade
input int            InpFlatHHMM        = 1555;       // Close everything at/after

//--- broker clock
input group "=== Broker clock ==="
input bool           InpAutoGMTOffset   = true;       // Live: verify offset against TimeGMT()
input int            InpServerGMTWinter = 2;          // Server GMT offset in winter (hours)
input ENUM_DST_MODE  InpServerDST       = DST_US;     // Server daylight-saving rule

//--- risk
input group "=== Risk per trade ==="
input double         InpRiskPercent     = 0.75;       // Risk per trade, % of balance
input double         InpMaxLots         = 0.0;        // Lot cap (0 = none)
input double         InpMaxSpreadPoints = 0.0;        // Skip entries above this spread (0 = off)
input int            InpSlippagePoints  = 50;         // Max deviation for market orders

//--- prop-firm guard
input group "=== Prop-firm guard ==="
input double         InpChallengeBalance = 0.0;       // Initial challenge balance (0 = balance at first start)
input double         InpDailyStopPct     = 3.0;       // Stop for the day at this loss (% of initial)
input double         InpMaxLossStopPct   = 8.0;       // Halt EA at this total loss (% of initial)
input double         InpTargetPct        = 10.0;      // Halt once profit target reached (0 = off)
input bool           InpCloseOnGuard     = true;      // Close open trades when a guard triggers
input int            InpDayResetHour     = 0;         // Server hour when the prop "day" resets
input bool           InpResetGuard       = false;     // Clear saved guard state on start (new challenge)

input group "=== Session clock ==="
input ENUM_SESSION_TZ InpSessionTZ       = TZ_NEW_YORK; // Time zone of the session inputs above

input group "=== Sprint mode (opt-in: faster pass, much higher risk) ==="
input bool           InpSprintMode        = false;    // Size every trade toward the profit target
input double         InpSprintMaxRiskPct  = 4.0;      // Max risk per trade, % of initial balance
input double         InpSprintMinRiskPct  = 0.25;     // Skip a trade if less risk than this fits the budget
input double         InpSprintWinR        = 2.5;      // Size so one win of this many R reaches the target
input double         InpSprintDailyBudget = 4.0;      // Worst-case daily loss incl. open stops, % of initial (all charts)
input double         InpSprintTotalBudget = 9.5;      // Worst-case total loss incl. open stops, % of initial (all charts)

input group "=== Minimum trading days helper (opt-in) ==="
input int            InpMinTradingDays    = 0;        // After the target is hit, 1 micro trade per day until this many trading days (0 = off)
input int            InpHelperHHMM        = 1005;     // Session time for the micro trade (HHMM)

input group "=== Misc ==="
input long           InpMagic           = 26092501;   // Magic number
input string         InpComment         = "EvalPass"; // Order comment
input bool           InpShowPanel       = true;       // Show status on chart

//--- globals
CTrade   g_trade;
int      g_openMin, g_closeMin, g_firstCheck, g_lastEntry, g_flatMin, g_sessLen;
int      g_offsetAdjSec = 0;          // live correction to the rule-based server offset
datetime g_lastBarTime  = 0;

// per New York day state
long     g_dayId      = -1;           // NY date (days since 1970) the state belongs to
bool     g_dayReady   = false;
double   g_dayOpen    = 0.0;
double   g_prevClose  = 0.0;
double   g_sigma[];                   // per session minute
int      g_tradesToday = 0;

// guard state
double   g_initBalance = 0.0;
long     g_guardDay    = -1;
double   g_dayStartEq  = 0.0;
bool     g_haltDay     = false;
bool     g_haltAll     = false;
int      g_haltReason  = 0;           // 1 = profit target, 2 = max-loss guard
datetime g_startTime   = 0;           // challenge start (for trading-day counting)
ulong    g_helperTicket = 0;
datetime g_helperOpened = 0;
string   g_status      = "";

//+------------------------------------------------------------------+
//| Time helpers                                                     |
//+------------------------------------------------------------------+
int HHMMtoMin(const int hhmm) { return (hhmm / 100) * 60 + (hhmm % 100); }

datetime MakeTime(const int y, const int mon, const int d, const int h)
  {
   MqlDateTime s;
   ZeroMemory(s);
   s.year = y; s.mon = mon; s.day = d; s.hour = h; s.min = 0; s.sec = 0;
   return StructToTime(s);
  }

// n-th Sunday (n>=1) of a month, 00:00
datetime NthSunday(const int y, const int mon, const int n)
  {
   datetime first = MakeTime(y, mon, 1, 0);
   MqlDateTime s; TimeToStruct(first, s);
   int add = (7 - s.day_of_week) % 7;
   return first + (add + 7 * (n - 1)) * 86400;
  }

datetime LastSunday(const int y, const int mon)
  {
   int nm = (mon == 12) ? 1 : mon + 1;
   int ny = (mon == 12) ? y + 1 : y;
   datetime nextFirst = MakeTime(ny, nm, 1, 0);
   MqlDateTime s; TimeToStruct(nextFirst - 86400, s);
   return (nextFirst - 86400) - s.day_of_week * 86400;
  }

// US DST: 2nd Sunday March 07:00 UTC -> 1st Sunday November 06:00 UTC
bool IsUSDST(const datetime utc)
  {
   MqlDateTime s; TimeToStruct(utc, s);
   datetime a = NthSunday(s.year, 3, 2) + 7 * 3600;
   datetime b = NthSunday(s.year, 11, 1) + 6 * 3600;
   return (utc >= a && utc < b);
  }

// EU DST: last Sunday March 01:00 UTC -> last Sunday October 01:00 UTC
bool IsEUDST(const datetime utc)
  {
   MqlDateTime s; TimeToStruct(utc, s);
   datetime a = LastSunday(s.year, 3) + 3600;
   datetime b = LastSunday(s.year, 10) + 3600;
   return (utc >= a && utc < b);
  }

int RuleOffsetSec(const datetime serverTime)
  {
   int off = InpServerGMTWinter * 3600;
   datetime approxUtc = serverTime - off;
   if(InpServerDST == DST_US && IsUSDST(approxUtc)) off += 3600;
   if(InpServerDST == DST_EU && IsEUDST(approxUtc)) off += 3600;
   return off + g_offsetAdjSec;
  }

datetime ServerToUTC(const datetime serverTime) { return serverTime - RuleOffsetSec(serverTime); }

datetime UTCToNY(const datetime utc) { return utc - 5 * 3600 + (IsUSDST(utc) ? 3600 : 0); }

datetime ServerToNY(const datetime serverTime) { return UTCToNY(ServerToUTC(serverTime)); }

// session-local clock used by all session logic (New York by default)
datetime ServerToSession(const datetime serverTime)
  {
   if(InpSessionTZ == TZ_TOKYO) return ServerToUTC(serverTime) + 9 * 3600;
   return ServerToNY(serverTime);
  }

string SessionName() { return (InpSessionTZ == TZ_TOKYO) ? "Tokyo" : "NY"; }

long DayId(const datetime t)    { return ((long)t) / 86400; }
int  MinOfDay(const datetime t) { return (int)((((long)t) % 86400) / 60); }

//+------------------------------------------------------------------+
//| Position helpers                                                 |
//+------------------------------------------------------------------+
int MyPosition(ulong &ticket)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      ticket = t;
      return (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
     }
   ticket = 0;
   return 0;
  }

void CloseMine(const string why)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(!g_trade.PositionClose(t))
         PrintFormat("Close %I64u failed (%s): %d %s", t, why, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
      else
         PrintFormat("Closed %I64u: %s", t, why);
     }
  }

// entries already made by this EA on this symbol since a server time (survives restarts)
int CountEntriesSince(const datetime serverFrom)
  {
   if(!HistorySelect(serverFrom, TimeCurrent() + 60)) return 0;
   int cnt = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
     {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      if(HistoryDealGetString(d, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(d, DEAL_MAGIC) != InpMagic) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      cnt++;
     }
   return cnt;
  }

//+------------------------------------------------------------------+
//| Prop-firm guard                                                  |
//+------------------------------------------------------------------+
string GVName(const string key) { return StringFormat("EvalPass_%I64d_%s", InpMagic, key); }

void GuardInit()
  {
   if(InpResetGuard && !MQLInfoInteger(MQL_TESTER))
     {
      int removed = GlobalVariablesDeleteAll(StringFormat("EvalPass_%I64d_", InpMagic));
      PrintFormat("Guard state reset (%d saved values removed)", removed);
     }
   string k = GVName("init_balance");
   if(InpChallengeBalance > 0)
      g_initBalance = InpChallengeBalance;
   else if(GlobalVariableCheck(k))
      g_initBalance = GlobalVariableGet(k);
   else
      g_initBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(!MQLInfoInteger(MQL_TESTER))
      GlobalVariableSet(k, g_initBalance);
   g_haltAll = (!MQLInfoInteger(MQL_TESTER) && GlobalVariableCheck(GVName("halt_all")) && GlobalVariableGet(GVName("halt_all")) > 0);
   if(g_haltAll)
      g_haltReason = (int)GlobalVariableGet(GVName("halt_all"));
   string ks = GVName("start_time");
   if(!MQLInfoInteger(MQL_TESTER) && GlobalVariableCheck(ks))
      g_startTime = (datetime)GlobalVariableGet(ks);
   else
     {
      g_startTime = TimeCurrent();
      if(!MQLInfoInteger(MQL_TESTER)) GlobalVariableSet(ks, (double)g_startTime);
     }
  }

// returns true when new entries are allowed
bool GuardCheck()
  {
   datetime now = TimeCurrent();
   long pday = DayId(now - InpDayResetHour * 3600);
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
   if(pday != g_guardDay)
     {
      g_guardDay = pday;
      string k = GVName(StringFormat("daystart_%I64d", pday));
      if(!MQLInfoInteger(MQL_TESTER) && GlobalVariableCheck(k))
         g_dayStartEq = GlobalVariableGet(k);
      else
        {
         g_dayStartEq = MathMax(bal, eq);
         if(!MQLInfoInteger(MQL_TESTER)) GlobalVariableSet(k, g_dayStartEq);
        }
      g_haltDay = false;
     }
   // another chart of this EA (same magic) may have halted the account
   if(!g_haltAll && !MQLInfoInteger(MQL_TESTER) && GlobalVariableCheck(GVName("halt_all")) &&
      GlobalVariableGet(GVName("halt_all")) > 0)
     {
      g_haltAll = true;
      g_haltReason = (int)GlobalVariableGet(GVName("halt_all"));
      CloseMine("halted by another instance");
     }
   if(g_haltAll) return false;

   if(InpMaxLossStopPct > 0 && eq <= g_initBalance * (1.0 - InpMaxLossStopPct / 100.0))
     {
      g_haltAll = true;
      g_haltReason = 2;
      if(!MQLInfoInteger(MQL_TESTER)) GlobalVariableSet(GVName("halt_all"), 2);
      PrintFormat("GUARD: max-loss stop hit (equity %.2f). EA halted.", eq);
      if(InpCloseOnGuard) CloseMine("max-loss guard");
      return false;
     }
   if(InpTargetPct > 0 && eq >= g_initBalance * (1.0 + InpTargetPct / 100.0))
     {
      g_haltAll = true;
      g_haltReason = 1;
      if(!MQLInfoInteger(MQL_TESTER)) GlobalVariableSet(GVName("halt_all"), 1);
      PrintFormat("GUARD: profit target reached (equity %.2f). EA halted.", eq);
      CloseMine("profit target");
      return false;
     }
   if(!g_haltDay && InpDailyStopPct > 0 && eq <= g_dayStartEq - g_initBalance * InpDailyStopPct / 100.0)
     {
      g_haltDay = true;
      PrintFormat("GUARD: daily stop hit (equity %.2f, day start %.2f). No new trades today.", eq, g_dayStartEq);
      if(InpCloseOnGuard) CloseMine("daily guard");
     }
   return !g_haltDay;
  }

//+------------------------------------------------------------------+
//| Session model                                                    |
//+------------------------------------------------------------------+
// Rebuild open, previous close and the per-minute noise width for NY day `today`.
bool BuildDay(const long today)
  {
   int need = (InpLookbackDays + 12) * 1440;
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M1, 0, need, r);
   if(n <= 0)
     {
      Print("BuildDay: CopyRates failed ", GetLastError());
      return false;
     }
   // collect RTH closes per NY day (chronological)
   long   days[];
   double opens[];
   double closes[];      // days x sessLen, forward-filled
   int    nd = -1;
   long   curDay = -1;
   double todayOpen = 0.0;
   for(int i = 0; i < n; i++)
     {
      datetime ny = ServerToSession(r[i].time);
      int m = MinOfDay(ny) - g_openMin;
      if(m < 0 || m >= g_sessLen) continue;
      long d = DayId(ny);
      if(d > today) continue;
      if(d == today)
        {
         if(todayOpen == 0.0) todayOpen = r[i].close;
         continue;
        }
      if(d != curDay)
        {
         curDay = d; nd++;
         ArrayResize(days, nd + 1);
         ArrayResize(opens, nd + 1);
         ArrayResize(closes, (nd + 1) * g_sessLen);
         for(int k = 0; k < g_sessLen; k++) closes[nd * g_sessLen + k] = 0.0;
         days[nd] = d;
         opens[nd] = r[i].close;          // close of the first RTH bar
        }
      closes[nd * g_sessLen + m] = r[i].close;
     }
   int ndays = nd + 1;
   if(todayOpen == 0.0 || ndays < InpLookbackDays)
     {
      if(ndays < InpLookbackDays)
         PrintFormat("BuildDay: only %d past sessions in history, need %d", ndays, InpLookbackDays);
      return false;
     }
   // forward-fill missing minutes inside each day
   for(int d = 0; d < ndays; d++)
     {
      double last = opens[d];
      for(int k = 0; k < g_sessLen; k++)
        {
         int idx = d * g_sessLen + k;
         if(closes[idx] == 0.0) closes[idx] = last;
         else last = closes[idx];
        }
     }
   ArrayResize(g_sigma, g_sessLen);
   for(int k = 0; k < g_sessLen; k++)
     {
      double sum = 0.0;
      for(int d = ndays - InpLookbackDays; d < ndays; d++)
         sum += MathAbs(closes[d * g_sessLen + k] / opens[d] - 1.0);
      g_sigma[k] = sum / InpLookbackDays;
     }
   g_prevClose = closes[(ndays - 1) * g_sessLen + g_sessLen - 1];
   g_dayOpen   = todayOpen;
   g_dayId     = today;
   g_dayReady  = true;
   // trades already taken today (e.g. after a terminal restart)
   datetime nyNow = ServerToSession(TimeCurrent());
   datetime sessStartServer = TimeCurrent() - (datetime)(((long)nyNow % 86400) - (long)g_openMin * 60);
   g_tradesToday = CountEntriesSince(sessStartServer);
   int k30 = (g_sessLen > 29) ? 29 : g_sessLen - 1;
   PrintFormat("Day %s ready: open %.2f prev close %.2f noise(+30min) %.4f%%, %d sessions",
               TimeToString((datetime)(today * 86400), TIME_DATE), g_dayOpen, g_prevClose,
               100.0 * g_sigma[k30], ndays);
   return true;
  }

// session VWAP (tick-volume weighted typical price) from the open up to the closed bar at shift 1
double SessionVWAP(const long today)
  {
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M1, 1, g_sessLen + 60, r);
   if(n <= 0) return 0.0;
   double pv = 0.0, v = 0.0;
   for(int i = 0; i < n; i++)
     {
      datetime ny = ServerToSession(r[i].time);
      if(DayId(ny) != today) continue;
      int m = MinOfDay(ny) - g_openMin;
      if(m < 0 || m >= g_sessLen) continue;
      double w = (double)r[i].tick_volume;
      pv += (r[i].high + r[i].low + r[i].close) / 3.0 * w;
      v  += w;
     }
   return (v > 0) ? pv / v : 0.0;
  }

//+------------------------------------------------------------------+
//| Order sizing / entry                                             |
//+------------------------------------------------------------------+
// money still at risk on all positions of this EA (every symbol) if every stop is hit from here
double OpenRiskMoney()
  {
   double total = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      string sym = PositionGetString(POSITION_SYMBOL);
      double sl  = PositionGetDouble(POSITION_SL);
      if(sl <= 0)
        {
         total += AccountInfoDouble(ACCOUNT_BALANCE);   // unknown risk -> no budget left
         continue;
        }
      bool   buy = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
      double pnl = 0.0;
      if(OrderCalcProfit(buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, sym, PositionGetDouble(POSITION_VOLUME),
                         PositionGetDouble(POSITION_PRICE_CURRENT), sl, pnl) && pnl < 0)
         total -= pnl;
     }
   return total;
  }

// money to risk on the next trade
double RiskMoneyForTrade()
  {
   if(!InpSprintMode || InpTargetPct <= 0)
      return AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
   // sprint: size so that one win of InpSprintWinR reaches the target ...
   double init      = g_initBalance;
   double profitPct = 100.0 * (AccountInfoDouble(ACCOUNT_BALANCE) / init - 1.0);
   double pct       = (InpTargetPct - profitPct) / InpSprintWinR;
   pct = MathMax(InpSprintMinRiskPct, MathMin(InpSprintMaxRiskPct, pct));
   double money = init * pct / 100.0;
   // ... but never more than the room left before the daily / total budgets,
   // counting what every open position could still lose down to its stop
   double worstEq   = AccountInfoDouble(ACCOUNT_EQUITY) - OpenRiskMoney();
   double dailyRoom = worstEq - (g_dayStartEq - init * InpSprintDailyBudget / 100.0);
   double totalRoom = worstEq - init * (1.0 - InpSprintTotalBudget / 100.0);
   money = MathMin(money, MathMin(dailyRoom, totalRoom));
   if(money < init * InpSprintMinRiskPct / 100.0)
     {
      PrintFormat("Sprint: risk budget exhausted (daily room %.2f, total room %.2f) -> skip", dailyRoom, totalRoom);
      return 0.0;
     }
   return money;
  }

double LotsForRisk(const int dir, const double stopDist)
  {
   double price = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double slPx  = price - dir * stopDist;
   double pnl1  = 0.0;
   ENUM_ORDER_TYPE ot = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!OrderCalcProfit(ot, _Symbol, 1.0, price, slPx, pnl1) || pnl1 >= 0.0)
     {
      Print("LotsForRisk: OrderCalcProfit failed ", GetLastError());
      return 0.0;
     }
   double riskMoney = RiskMoneyForTrade();
   if(riskMoney <= 0) return 0.0;
   double lots = riskMoney / MathAbs(pnl1);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(InpMaxLots > 0) vmax = MathMin(vmax, InpMaxLots);
   lots = MathFloor(lots / step) * step;
   if(lots > vmax) lots = MathFloor(vmax / step) * step;
   // shrink to the free margin if needed
   double margin = 0.0;
   while(lots >= vmin && OrderCalcMargin(ot, _Symbol, lots, price, margin) &&
         margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.95)
      lots -= step;
   if(lots < vmin)
     {
      PrintFormat("LotsForRisk: computed %.4f lots < min volume %.4f -> skip", lots, vmin);
      return 0.0;
     }
   return NormalizeDouble(lots, 8);
  }

// Sprint mode: charts share one risk budget, so only one chart may size and open a trade at a time
// (atomic GlobalVariableSetOnCondition; a lock older than 10 s is treated as stale).
bool AcquireEntryLock()
  {
   if(!InpSprintMode || MQLInfoInteger(MQL_TESTER)) return true;
   string nm = GVName("entry_lock");
   if(!GlobalVariableCheck(nm)) GlobalVariableSet(nm, 0);
   for(int i = 0; i < 300; i++)
     {
      double cur = GlobalVariableGet(nm);
      double now = (double)TimeLocal();
      if((cur == 0 || now - cur > 10) && GlobalVariableSetOnCondition(nm, now, cur)) return true;
      Sleep(10);
     }
   return false;
  }

void ReleaseEntryLock()
  {
   if(!InpSprintMode || MQLInfoInteger(MQL_TESTER)) return;
   // keep the lock until the new position is visible, so the next chart's budget includes it
   ulong t;
   for(int i = 0; i < 50 && MyPosition(t) == 0; i++) Sleep(20);
   GlobalVariableSet(GVName("entry_lock"), 0);
  }

bool OpenTradeLocked(const int dir, const double stopDist)
  {
   if(stopDist <= 0) return false;
   long spreadPts = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(InpMaxSpreadPoints > 0 && spreadPts > InpMaxSpreadPoints)
     {
      PrintFormat("Entry skipped: spread %I64d > %.0f points", spreadPts, InpMaxSpreadPoints);
      return false;
     }
   double lots = LotsForRisk(dir, stopDist);
   if(lots <= 0) return false;
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0) tick = _Point;
   double minDist = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double dist = MathMax(stopDist, minDist + tick);
   bool ok = false;
   if(dir > 0)
     {
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double sl  = NormalizeDouble(MathRound((ask - dist) / tick) * tick, _Digits);
      double tp  = (InpTakeProfitR > 0) ? NormalizeDouble(MathRound((ask + InpTakeProfitR * dist) / tick) * tick, _Digits) : 0.0;
      ok = g_trade.Buy(lots, _Symbol, 0.0, sl, tp, InpComment);
     }
   else
     {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double sl  = NormalizeDouble(MathRound((bid + dist) / tick) * tick, _Digits);
      double tp  = (InpTakeProfitR > 0) ? NormalizeDouble(MathRound((bid - InpTakeProfitR * dist) / tick) * tick, _Digits) : 0.0;
      ok = g_trade.Sell(lots, _Symbol, 0.0, sl, tp, InpComment);
     }
   if(!ok || (g_trade.ResultRetcode() != TRADE_RETCODE_DONE && g_trade.ResultRetcode() != TRADE_RETCODE_PLACED))
     {
      PrintFormat("Entry failed: %d %s", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
      return false;
     }
   PrintFormat("%s %.2f lots, stop distance %.2f", dir > 0 ? "BUY" : "SELL", lots, dist);
   return true;
  }

bool OpenTrade(const int dir, const double stopDist)
  {
   if(!AcquireEntryLock())
     {
      Print("Sprint: entry lock busy -> skip");
      return false;
     }
   bool done = OpenTradeLocked(dir, stopDist);
   ReleaseEntryLock();
   return done;
  }

//+------------------------------------------------------------------+
//| Break-even: once price has moved InpBETriggerR x the initial      |
//| risk in favour, lock the stop at entry + InpBEOffsetR x risk.     |
//+------------------------------------------------------------------+
void ManageBreakEven()
  {
   if(InpBETriggerR <= 0) return;
   double stopsLvl = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl    = PositionGetDouble(POSITION_SL);
      double tp    = PositionGetDouble(POSITION_TP);
      if(sl <= 0) continue;
      if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
        {
         double risk = entry - sl;              // <= 0 once the stop is at/above entry
         if(risk <= 0) continue;
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(bid - entry < InpBETriggerR * risk) continue;
         double nsl = NormalizeDouble(entry + InpBEOffsetR * risk, _Digits);
         if(nsl > sl && nsl < bid - stopsLvl && !g_trade.PositionModify(t, nsl, tp))
            PrintFormat("Break-even modify failed: %d %s", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
        }
      else
        {
         double risk = sl - entry;
         if(risk <= 0) continue;
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         if(entry - ask < InpBETriggerR * risk) continue;
         double nsl = NormalizeDouble(entry - InpBEOffsetR * risk, _Digits);
         if(nsl < sl && nsl > ask + stopsLvl && !g_trade.PositionModify(t, nsl, tp))
            PrintFormat("Break-even modify failed: %d %s", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
        }
     }
  }

//+------------------------------------------------------------------+
//| Minimum-trading-days helper (opt-in)                             |
//| Prop firms count a day when at least one trade is opened. Once    |
//| the target is reached the EA halts; if the firm still needs more  |
//| trading days, open one minimum-lot trade per day and close it     |
//| about a minute later (cost: roughly one spread on the min lot).   |
//+------------------------------------------------------------------+
int TradingDaysSinceStart(bool &todayTraded)
  {
   todayTraded = false;
   if(!HistorySelect(g_startTime, TimeCurrent() + 60)) return 0;
   long today = DayId(TimeCurrent() - InpDayResetHour * 3600);
   long days[];
   int  nd = 0;
   for(int i = 0; i < HistoryDealsTotal(); i++)
     {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      long type = HistoryDealGetInteger(d, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      long day = DayId((datetime)HistoryDealGetInteger(d, DEAL_TIME) - InpDayResetHour * 3600);
      if(day == today) todayTraded = true;
      bool seen = false;
      for(int j = 0; j < nd; j++)
         if(days[j] == day) { seen = true; break; }
      if(!seen)
        {
         ArrayResize(days, nd + 1);
         days[nd] = day;
         nd++;
        }
     }
   return nd;
  }

void MinDaysHelper()
  {
   if(InpMinTradingDays <= 0 || !g_haltAll || g_haltReason != 1) return;
   if(g_helperTicket != 0)
     {
      if(PositionSelectByTicket(g_helperTicket))
        {
         if(TimeCurrent() - g_helperOpened >= 60 && !g_trade.PositionClose(g_helperTicket))
            PrintFormat("Helper close failed: %d %s", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
         return;
        }
      g_helperTicket = 0;
     }
   int clk = MinOfDay(ServerToSession(TimeCurrent()));
   if(clk < HHMMtoMin(InpHelperHHMM) || clk >= g_flatMin) return;
   long pday = DayId(TimeCurrent() - InpDayResetHour * 3600);
   string lock = GVName(StringFormat("helper_%I64d", pday));
   if(GlobalVariableCheck(lock)) return;             // already handled today (this or another chart)
   GlobalVariableSet(lock, 1);
   bool todayTraded = false;
   int nd = TradingDaysSinceStart(todayTraded);
   if(nd >= InpMinTradingDays || todayTraded) return;
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0) tick = _Point;
   double ask  = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl   = NormalizeDouble(MathRound(ask * 0.99 / tick) * tick, _Digits);
   if(!g_trade.Buy(vmin, _Symbol, 0.0, sl, 0.0, InpComment + " day"))
     {
      PrintFormat("Helper trade failed: %d %s", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
      return;
     }
   ulong t;
   if(MyPosition(t) != 0)
     {
      g_helperTicket = t;
      g_helperOpened = TimeCurrent();
     }
   PrintFormat("Minimum-days helper: micro trade opened (trading day %d of %d)", nd + 1, InpMinTradingDays);
  }

//+------------------------------------------------------------------+
//| Signal evaluation on the bar that just closed                    |
//+------------------------------------------------------------------+
void OnNewBar(const bool entriesAllowed)
  {
   MqlRates b[];
   if(CopyRates(_Symbol, PERIOD_M1, 1, 1, b) != 1) return;
   datetime ny = ServerToSession(b[0].time);
   long today = DayId(ny);
   int  clk   = MinOfDay(ny);
   int  m     = clk - g_openMin;
   if(m < 0 || m >= g_sessLen) return;

   if(today != g_dayId)
     {
      g_dayReady = false;
      g_tradesToday = 0;
      g_dayId = today;
     }
   bool isCheck = ((clk + 1) % InpCheckEveryMin == 0) && (clk + 1 >= g_firstCheck);
   if(!isCheck) return;
   if(!g_dayReady && !BuildDay(today)) return;

   double c     = b[0].close;
   double sig   = g_sigma[m] * InpBandMult;
   double upper = MathMax(g_dayOpen, g_prevClose) * (1.0 + sig);
   double lower = MathMin(g_dayOpen, g_prevClose) * (1.0 - sig);
   double vwap  = InpUseVWAP ? SessionVWAP(today) : 0.0;
   double longStop  = (InpUseVWAP && vwap > 0) ? MathMax(upper, vwap) : upper;
   double shortStop = (InpUseVWAP && vwap > 0) ? MathMin(lower, vwap) : lower;

   // exits first
   ulong ticket;
   int pos = MyPosition(ticket);
   bool closedNow = false;
   bool exitLong  = (InpExitMode == EXIT_BAND && c < longStop)  || (InpExitMode == EXIT_OPPOSITE && c < lower);
   bool exitShort = (InpExitMode == EXIT_BAND && c > shortStop) || (InpExitMode == EXIT_OPPOSITE && c > upper);
   if(pos > 0 && exitLong)  { CloseMine("signal exit"); closedNow = true; }
   if(pos < 0 && exitShort) { CloseMine("signal exit"); closedNow = true; }
   if(closedNow) pos = 0;

   g_status = StringFormat("%s %s  close %.2f  upper %.2f  lower %.2f  vwap %.2f  sigma %.3f%%",
                           SessionName(), TimeToString(ny + 60, TIME_MINUTES), c, upper, lower, vwap, 100.0 * sig);

   if(pos != 0 || closedNow || !entriesAllowed) return;
   if(clk + 1 > g_lastEntry) return;
   if(g_tradesToday >= InpMaxTradesPerDay) return;

   double sigPx = g_sigma[m] * g_dayOpen;
   if(c > upper && InpAllowLong)
     {
      double dist = (InpStopMode == STOP_SIGMA) ? InpStopSigma * sigPx : MathMax(c - longStop, InpMinStopSigma * sigPx);
      if(OpenTrade(1, dist)) g_tradesToday++;
     }
   else if(c < lower && InpAllowShort)
     {
      double dist = (InpStopMode == STOP_SIGMA) ? InpStopSigma * sigPx : MathMax(shortStop - c, InpMinStopSigma * sigPx);
      if(OpenTrade(-1, dist)) g_tradesToday++;
     }
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpCheckEveryMin <= 0 || InpLookbackDays <= 0 || InpRiskPercent <= 0)
      return INIT_PARAMETERS_INCORRECT;
   g_openMin    = HHMMtoMin(InpOpenHHMM);
   g_closeMin   = HHMMtoMin(InpCloseHHMM);
   g_firstCheck = HHMMtoMin(InpFirstCheckHHMM);
   g_lastEntry  = HHMMtoMin(InpLastEntryHHMM);
   g_flatMin    = HHMMtoMin(InpFlatHHMM);
   g_sessLen    = g_closeMin - g_openMin;
   if(g_sessLen <= 0) return INIT_PARAMETERS_INCORRECT;

   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   g_trade.SetTypeFillingBySymbol(_Symbol);

   g_offsetAdjSec = 0;
   if(InpAutoGMTOffset && !MQLInfoInteger(MQL_TESTER))
     {
      datetime srv = TimeTradeServer();
      int detected = (int)MathRound((double)(srv - TimeGMT()) / 900.0) * 900;
      int rule = RuleOffsetSec(srv);
      if(detected != rule)
        {
         g_offsetAdjSec = detected - rule;
         PrintFormat("Server GMT offset detected %+.2fh differs from inputs (%+.2fh); correcting by %+.2fh",
                     detected / 3600.0, rule / 3600.0, g_offsetAdjSec / 3600.0);
        }
     }
   GuardInit();
   PrintFormat("EvalPassMomentum on %s: server %s = %s %s (check this matches reality!)",
               _Symbol, TimeToString(TimeTradeServer(), TIME_DATE | TIME_MINUTES), SessionName(),
               TimeToString(ServerToSession(TimeTradeServer()), TIME_DATE | TIME_MINUTES));
   if(InpSprintMode)
      PrintFormat("SPRINT MODE: up to %.2f%% risk per trade (target %.1f%%, budgets %.1f%% daily / %.1f%% total)",
                  InpSprintMaxRiskPct, InpTargetPct, InpSprintDailyBudget, InpSprintTotalBudget);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { Comment(""); }

void OnTick()
  {
   bool entriesAllowed = GuardCheck();
   MinDaysHelper();

   // hard flat before the close
   datetime nyNow = ServerToSession(TimeCurrent());
   int clkNow = MinOfDay(nyNow);
   ulong ticket;
   if(MyPosition(ticket) != 0 && ticket != g_helperTicket && (clkNow >= g_flatMin || clkNow < g_openMin))
      CloseMine("session flat");

   ManageBreakEven();

   datetime bt = iTime(_Symbol, PERIOD_M1, 0);
   if(bt != 0 && bt != g_lastBarTime)
     {
      g_lastBarTime = bt;
      OnNewBar(entriesAllowed && !g_haltAll);
     }

   if(InpShowPanel && !MQLInfoInteger(MQL_OPTIMIZATION))
     {
      double eq = AccountInfoDouble(ACCOUNT_EQUITY);
      Comment(StringFormat("EvalPassMomentum%s  |  %s time %s\n%s\nTrades today %d/%d  |  Equity %.2f  (%.2f%% vs initial, %.2f%% today)\n%s",
                           InpSprintMode ? " [SPRINT]" : "", SessionName(), TimeToString(nyNow, TIME_DATE | TIME_MINUTES), g_status, g_tradesToday, InpMaxTradesPerDay,
                           eq, 100.0 * (eq / g_initBalance - 1.0), 100.0 * (eq - g_dayStartEq) / g_initBalance,
                           g_haltAll ? "HALTED (target reached or max-loss guard)" : (g_haltDay ? "Daily stop active - no new trades today" : "Active")));
     }
  }
//+------------------------------------------------------------------+
