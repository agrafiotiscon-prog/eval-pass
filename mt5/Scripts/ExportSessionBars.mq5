//+------------------------------------------------------------------+
//|                                           ExportSessionBars.mq5  |
//|  Exports M1 bars (bid OHLC, tick volume, spread) of several       |
//|  symbols to CSV files in <Data folder>\MQL5\Files, one file per   |
//|  symbol and year, keeping only the server hours that contain the  |
//|  symbol's cash session so the files stay small enough to upload.  |
//+------------------------------------------------------------------+
#property copyright   "eval-pass"
#property version     "1.00"
#property script_show_inputs

// symbol:startHour-endHour (server time, end exclusive); hours cover each cash session with margin
input string InpSymbols = "NDX100:15-24,SPX500:15-24,DJI30:15-24,GER40:8-20,JP225:0-11";
input int    InpYears   = 3;      // how many years back from today

void ExportSymbol(const string sym, const int h0, const int h1)
  {
   if(!SymbolSelect(sym, true))
     {
      PrintFormat("%s: symbol not found", sym);
      return;
     }
   datetime to   = TimeCurrent();
   datetime from = to - (datetime)InpYears * 365 * 86400;
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(sym, PERIOD_M1, from, to, r);
   if(n <= 0)
     {
      PrintFormat("%s: no M1 history (error %d). Open an M1 chart of it, press Home a few times, then rerun.", sym, GetLastError());
      return;
     }
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   int handle = INVALID_HANDLE, curYear = -1, rows = 0;
   for(int i = 0; i < n; i++)
     {
      MqlDateTime t;
      TimeToStruct(r[i].time, t);
      if(t.hour < h0 || t.hour >= h1) continue;
      if(t.year != curYear)
        {
         if(handle != INVALID_HANDLE) FileClose(handle);
         curYear = t.year;
         string fn = StringFormat("export_%s_%d.csv", sym, curYear);
         handle = FileOpen(fn, FILE_WRITE | FILE_ANSI | FILE_TXT);
         if(handle == INVALID_HANDLE)
           {
            PrintFormat("cannot open %s (error %d)", fn, GetLastError());
            return;
           }
         FileWriteString(handle, "time,open,high,low,close,tick_volume,spread_points\n");
        }
      FileWriteString(handle, StringFormat("%I64d,%s,%s,%s,%s,%I64d,%d\n", (long)r[i].time,
                      DoubleToString(r[i].open, digits), DoubleToString(r[i].high, digits),
                      DoubleToString(r[i].low, digits), DoubleToString(r[i].close, digits),
                      r[i].tick_volume, r[i].spread));
      rows++;
     }
   if(handle != INVALID_HANDLE) FileClose(handle);
   PrintFormat("%s: %d of %d M1 bars exported (first %s)", sym, rows, n, TimeToString(r[0].time, TIME_DATE));
  }

void OnStart()
  {
   string items[];
   int k = StringSplit(InpSymbols, ',', items);
   for(int i = 0; i < k; i++)
     {
      string parts[];
      if(StringSplit(items[i], ':', parts) != 2) continue;
      string hrs[];
      if(StringSplit(parts[1], '-', hrs) != 2) continue;
      string sym = parts[0];
      StringTrimLeft(sym);
      StringTrimRight(sym);
      ExportSymbol(sym, (int)StringToInteger(hrs[0]), (int)StringToInteger(hrs[1]));
     }
   Print("Export finished. Files are in File > Open Data Folder > MQL5 > Files");
  }
