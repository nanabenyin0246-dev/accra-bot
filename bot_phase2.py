import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
bot_phase2.py — Accra Bot Phase 2 Upgrades
Four modules: Backtest, Metrics, NN Fine-tune, Mode Manager
"""
import os, json, time, math, sqlite3, requests, logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("accra_bot")

class ModeManager:
    LIVE = "live"; PAPER = "paper"; BACKTEST = "backtest"
    def __init__(self):
        raw = os.getenv("MODE", "live").lower().strip()
        if raw not in (self.LIVE, self.PAPER, self.BACKTEST):
            raw = self.PAPER
        self._mode = raw
        print(f"[MODE] Trading mode: {self._mode.upper()}")
    @property
    def mode(self): return self._mode
    @property
    def is_live(self): return self._mode == self.LIVE
    @property
    def is_paper(self): return self._mode == self.PAPER
    @property
    def is_backtest(self): return self._mode == self.BACKTEST
    def can_execute(self):
        if self.is_live: return True, "LIVE mode"
        if self.is_paper: return False, "PAPER mode"
        return False, "BACKTEST mode"
    def tag(self):
        return {"live":"[LIVE] LIVE","paper":"📄 PAPER","backtest":"📊 BACKTEST"}.get(self._mode,"?")
    def status(self):
        return {"mode":self._mode,"tag":self.tag(),"can_execute":self.is_live,"real_money":self.is_live}

mode_manager = ModeManager()

class BacktestResult:
    def __init__(self, symbol, trades, equity_curve, initial_capital):
        self.symbol=symbol; self.trades=trades
        self.equity_curve=equity_curve; self.initial_capital=initial_capital
        self.final_equity=equity_curve[-1] if equity_curve else initial_capital
    @property
    def total_return_pct(self): return (self.final_equity-self.initial_capital)/self.initial_capital*100
    @property
    def n_trades(self): return len(self.trades)
    @property
    def wins(self): return [t for t in self.trades if t.get("pnl_pct",0)>0]
    @property
    def losses(self): return [t for t in self.trades if t.get("pnl_pct",0)<=0]
    @property
    def win_rate(self): return len(self.wins)/len(self.trades) if self.trades else 0
    @property
    def sharpe(self):
        returns=[t.get("pnl_pct",0)/100 for t in self.trades]
        if len(returns)<2: return 0
        mean=sum(returns)/len(returns)
        std=math.sqrt(sum((r-mean)**2 for r in returns)/len(returns))
        return (mean/std*math.sqrt(252)) if std>0 else 0
    @property
    def max_drawdown(self):
        peak=dd=0; equity=self.initial_capital
        for t in self.trades:
            equity*=(1+t.get("pnl_pct",0)/100)
            if equity>peak: peak=equity
            dd=max(dd,(peak-equity)/peak*100) if peak>0 else 0
        return dd
    @property
    def expectancy(self):
        if not self.trades: return 0
        aw=sum(t["pnl_pct"] for t in self.wins)/len(self.wins) if self.wins else 0
        al=sum(t["pnl_pct"] for t in self.losses)/len(self.losses) if self.losses else 0
        return self.win_rate*aw+(1-self.win_rate)*al
    def summary(self):
        return {"symbol":self.symbol,"n_trades":self.n_trades,
                "win_rate_pct":round(self.win_rate*100,1),
                "total_return":round(self.total_return_pct,2),
                "sharpe":round(self.sharpe,2),
                "max_drawdown":round(self.max_drawdown,2),
                "expectancy":round(self.expectancy,3),
                "final_equity":round(self.final_equity,2)}
    def print_summary(self):
        s=self.summary()
        print(f"\n{'='*50}\n  BACKTEST: {s['symbol']}\n{'='*50}")
        print(f"  Trades:       {s['n_trades']}")
        print(f"  Win rate:     {s['win_rate_pct']}%")
        print(f"  Total return: {s['total_return']:+.2f}%")
        print(f"  Sharpe:       {s['sharpe']:.2f}")
        print(f"  Max DD:       {s['max_drawdown']:.2f}%")
        print(f"  Expectancy:   {s['expectancy']:.3f}%")
        print(f"  Final equity: ${s['final_equity']:.2f}\n{'='*50}\n")

class BacktestEngine:
    def __init__(self,initial_capital=15.0,sl_pct=0.10,tp_pct=0.10,min_score=25,fee_pct=0.001):
        self.initial_capital=initial_capital; self.sl_pct=sl_pct
        self.tp_pct=tp_pct; self.min_score=min_score; self.fee_pct=fee_pct
    def _fetch_candles(self,symbol,days):
        limit=min(days*24,1000)
        try:
            r=requests.get("https://api.binance.com/api/v3/klines",
                params={"symbol":symbol,"interval":"1h","limit":limit},timeout=15)
            r.raise_for_status(); return r.json()
        except Exception as e:
            print(f"[BACKTEST] Fetch error: {e}"); return []
    def _score_window(self,closes):
        if len(closes)<35: return 0
        def rsi(c,p=14):
            if len(c)<p+1: return 50.0
            g=l=0.0
            for i in range(1,p+1):
                d=c[i]-c[i-1]
                if d>0: g+=d
                else: l-=d
            ag,al=g/p,l/p
            for i in range(p+1,len(c)):
                d=c[i]-c[i-1]
                ag=(ag*(p-1)+(d if d>0 else 0))/p
                al=(al*(p-1)+(-d if d<0 else 0))/p
            return 100-100/(1+ag/al) if al!=0 else 100.0
        def ema(c,p):
            if len(c)<p: return []
            k=2/(p+1); r=[sum(c[:p])/p]
            for v in c[p:]: r.append(v*k+r[-1]*(1-k))
            return r
        score=0; r=rsi(closes)
        if r<28: score+=35
        elif r<35: score+=20
        elif r>72: score-=35
        elif r>65: score-=20
        e9=ema(closes,9); e21=ema(closes,21)
        if e9 and e21:
            if e9[-1]>e21[-1]: score+=10
            else: score-=10
        if len(closes)>=5:
            mom=(closes[-1]-closes[-5])/closes[-5]*100
            if mom>3: score+=15
            elif mom>1: score+=8
            elif mom<-3: score-=15
        if len(closes)>=20:
            mean=sum(closes[-20:])/20; dev=(closes[-1]-mean)/mean*100
            if dev<-8: score+=20
            elif dev<-4: score+=10
            elif dev>8: score-=20
            elif dev>4: score-=10
        return max(-100,min(100,score))
    def run(self,symbol,days=30):
        print(f"[BACKTEST] Running {symbol} over {days} days...")
        candles=self._fetch_candles(symbol,days)
        if len(candles)<50:
            print(f"[BACKTEST] Insufficient data"); return BacktestResult(symbol,[],[],self.initial_capital)
        closes=[float(k[4]) for k in candles]
        equity=self.initial_capital; equity_curve=[equity]
        trades=[]; position=None; min_window=35
        for i in range(min_window,len(closes)):
            window=closes[:i]; price=closes[i]
            if position:
                entry=position["entry"]
                if price<=position["sl"]:
                    pnl=(price-entry)/entry*100-self.fee_pct*100
                    trades.append({"type":"STOP","entry":entry,"exit":price,"pnl_pct":round(pnl,3)})
                    equity*=(1+pnl/100); position=None
                elif price>=position["tp"]:
                    pnl=(price-entry)/entry*100-self.fee_pct*100
                    trades.append({"type":"TP","entry":entry,"exit":price,"pnl_pct":round(pnl,3)})
                    equity*=(1+pnl/100); position=None
            if not position:
                score=self._score_window(window)
                if score>=self.min_score:
                    position={"entry":price,"sl":price*(1-self.sl_pct),"tp":price*(1+self.tp_pct),"score":score}
            equity_curve.append(max(0.01,equity))
        if position and closes:
            last=closes[-1]; pnl=(last-position["entry"])/position["entry"]*100
            trades.append({"type":"EOD","entry":position["entry"],"exit":last,"pnl_pct":round(pnl,3)})
            equity*=(1+pnl/100)
        result=BacktestResult(symbol,trades,equity_curve,self.initial_capital)
        result.print_summary(); return result
    def run_multi(self,symbols,days=30):
        return {sym:self.run(sym,days) for sym in symbols}
    def save_results(self,results,path=None):
        if path is None: path=os.path.expanduser("~/accra-bot/backtest_results.json")
        data={sym:r.summary() for sym,r in results.items()}
        data["run_at"]=datetime.now(timezone.utc).isoformat()
        with open(path,"w") as f: json.dump(data,f,indent=2)
        print(f"[BACKTEST] Saved to {path}"); return data

class MetricsDashboard:
    def __init__(self,db_path="trades.db"): self.db_path=db_path
    def _query(self,sql,params=()):
        try:
            con=sqlite3.connect(self.db_path)
            rows=con.execute(sql,params).fetchall(); con.close(); return rows
        except: return []
    def compute(self):
        rows=self._query("SELECT symbol,action,market,pnl_pct,won,ts,strategy FROM trades WHERE won IS NOT NULL ORDER BY ts")
        if not rows: return {"status":"no_data","message":"No closed trades yet"}
        total=len(rows); wins=[r for r in rows if r[4]==1]; losses=[r for r in rows if r[4]==0]
        pnls=[r[3] for r in rows if r[3] is not None]
        win_rate=len(wins)/total if total>0 else 0
        avg_win=sum(r[3] for r in wins)/len(wins) if wins else 0
        avg_loss=sum(r[3] for r in losses)/len(losses) if losses else 0
        profit_factor=abs(avg_win*len(wins))/abs(avg_loss*len(losses)) if losses and avg_loss!=0 else 999
        expectancy=win_rate*avg_win+(1-win_rate)*avg_loss
        sharpe=0
        if len(pnls)>=2:
            mean_p=sum(pnls)/len(pnls); var=sum((p-mean_p)**2 for p in pnls)/len(pnls)
            std_p=math.sqrt(var) if var>0 else 1; sharpe=(mean_p/std_p)*math.sqrt(252)
        cum=peak=dd=0
        for p in pnls:
            cum+=p
            if cum>peak: peak=cum
            dd=max(dd,peak-cum)
        asset_stats={}
        for r in rows:
            sym=r[0]
            if sym not in asset_stats: asset_stats[sym]={"wins":0,"losses":0,"pnl":0}
            if r[4]==1: asset_stats[sym]["wins"]+=1
            else: asset_stats[sym]["losses"]+=1
            if r[3]: asset_stats[sym]["pnl"]+=r[3]
        for sym in asset_stats:
            s=asset_stats[sym]; t=s["wins"]+s["losses"]
            s["win_rate"]=round(s["wins"]/t*100,1) if t>0 else 0; s["pnl"]=round(s["pnl"],2)
        cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
        week_rows=[r for r in rows if r[5] and r[5]>cutoff]; week_wins=[r for r in week_rows if r[4]==1]
        week_wr=len(week_wins)/len(week_rows)*100 if week_rows else 0
        week_pnl=sum(r[3] for r in week_rows if r[3])
        streak=streak_type=0
        for r in reversed(rows):
            outcome=r[4]
            if streak==0: streak_type=outcome; streak=1
            elif outcome==streak_type: streak+=1
            else: break
        return {"status":"ok","total_trades":total,"win_rate":round(win_rate*100,1),
                "profit_factor":round(profit_factor,2),"expectancy":round(expectancy,3),
                "sharpe":round(sharpe,2),"max_drawdown":round(dd,2),
                "avg_win_pct":round(avg_win,2),"avg_loss_pct":round(avg_loss,2),
                "week_win_rate":round(week_wr,1),"week_pnl":round(week_pnl,2),
                "week_trades":len(week_rows),"streak":streak,
                "streak_type":"WIN" if streak_type==1 else "LOSS",
                "per_asset":asset_stats,"updated_at":datetime.now(timezone.utc).isoformat()}
    def print_report(self):
        m=self.compute()
        if m.get("status")=="no_data": print(f"\n[METRICS] {m['message']}"); return
        print(f"\n{'='*55}\n  ACCRA BOT PERFORMANCE METRICS\n{'='*55}")
        print(f"  Total trades:   {m['total_trades']}")
        print(f"  Win rate:       {m['win_rate']}%")
        print(f"  Profit factor:  {m['profit_factor']}")
        print(f"  Expectancy:     {m['expectancy']:+.3f}%")
        print(f"  Sharpe ratio:   {m['sharpe']:.2f}")
        print(f"  Max drawdown:   {m['max_drawdown']:.2f}%")
        print(f"  Avg win:        {m['avg_win_pct']:+.2f}%  Avg loss: {m['avg_loss_pct']:+.2f}%")
        print(f"\n  Last 7 days: {m['week_trades']} trades, WR:{m['week_win_rate']}%, PnL:{m['week_pnl']:+.2f}%")
        arrow="🟢" if m['streak_type']=="WIN" else "[LIVE]"
        print(f"  {arrow} {m['streak']} consecutive {m['streak_type']}S")
        if m["per_asset"]:
            print(f"\n  Per asset (top 5):")
            for sym,s in sorted(m["per_asset"].items(),key=lambda x:x[1]["pnl"],reverse=True)[:5]:
                print(f"  {sym:<12} WR:{s['win_rate']}% PnL:{s['pnl']:+.2f}%")
        print(f"{'='*55}\n")
    def should_adjust_strategy(self):
        m=self.compute()
        if m.get("status")=="no_data" or m["total_trades"]<10: return {}
        adjustments={}
        if m["win_rate"]<35: adjustments={"min_confidence":50,"reason":f"Win rate {m['win_rate']}% < 35%"}
        if m["streak_type"]=="LOSS" and m["streak"]>=3: adjustments={"mode":"conservative","reason":f"{m['streak']} consecutive losses"}
        if m["max_drawdown"]>15: adjustments["sl_multiplier"]=0.7
        return adjustments

class NNFineTuner:
    RETRAIN_EVERY=50
    def __init__(self,db_path="trades.db"):
        self.db_path=db_path; self._last_count=self._get_closed_count(); self._nn_available=False
        try:
            from neural_signal import resolve_trade_outcome,record_trade_outcome,_finetune,nn_status
            self._resolve=resolve_trade_outcome; self._record=record_trade_outcome
            self._finetune=_finetune; self._nn_status=nn_status; self._nn_available=True
            print(f"[NN TUNER] Ready. Closed trades: {self._last_count}")
        except Exception as e:
            print(f"[NN TUNER] neural_signal.py not found: {e}")
    def _get_closed_count(self):
        try:
            con=sqlite3.connect(self.db_path)
            n=con.execute("SELECT COUNT(*) FROM trades WHERE won IS NOT NULL").fetchone()[0]
            con.close(); return n
        except: return 0
    def check_and_finetune(self):
        if not self._nn_available: return False
        current=self._get_closed_count()
        if current<10: return False
        prev_ms=(self._last_count//self.RETRAIN_EVERY)*self.RETRAIN_EVERY
        curr_ms=(current//self.RETRAIN_EVERY)*self.RETRAIN_EVERY
        if curr_ms>prev_ms and current>=self.RETRAIN_EVERY:
            print(f"[NN TUNER] Fine-tune triggered at {current} trades")
            self._last_count=current; return True
        self._last_count=current; return False
    def status(self):
        current=self._get_closed_count()
        next_ft=((current//self.RETRAIN_EVERY)+1)*self.RETRAIN_EVERY
        return {"nn_available":self._nn_available,"closed_trades":current,
                "next_finetune_at":next_ft,"trades_until_tune":max(0,next_ft-current)}

def print_phase2_status():
    print(f"\n{'='*55}\n  ACCRA BOT PHASE 2 UPGRADES\n{'='*55}")
    print(f"  [OK] Mode Manager    — {mode_manager.tag()}")
    print(f"  [OK] Backtest Engine — BacktestEngine().run('BTCUSDT', days=30)")
    print(f"  [OK] Metrics Dashboard — MetricsDashboard().print_report()")
    print(f"  [OK] NN Fine-tuner   — auto-triggers every 50 real trades")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    print_phase2_status()
    MetricsDashboard().print_report()
