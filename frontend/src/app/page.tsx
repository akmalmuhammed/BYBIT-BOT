"use client";

import { useState, useEffect, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface StrategyComparison {
  strategy_id: string;
  cooldown: number;
  atr_tf: string;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
}

interface Trade {
  id: string;
  symbol: string;
  strategy_id: string;
  side: string;
  entry_price: number;
  entry_time: string;
  trade_size_usd: number;
  exit_price: number | null;
  exit_time: string | null;
  pnl_pct: number | null;
  pnl_usd: number | null;
  status: string;
}

interface Position {
  symbol: string;
  strategy_id: string;
  side: string;
  entry_price: number;
  current_sl: number;
  take_profit_1: number;
  take_profit_2: number;
  take_profit_3: number;
  take_profit_4: number;
  take_profit_5: number;
  take_profit_6: number;
  tp1_hit: boolean;
  tp2_hit: boolean;
  tp3_hit: boolean;
  tp4_hit: boolean;
  tp5_hit: boolean;
  tp6_hit: boolean;
  current_price: number | null;
  unrealized_pnl_pct: number | null;
  unrealized_pnl_usd: number | null;
  trade_size_usd: number | null;
}

interface Account {
  starting_capital: number;
  current_balance: number;
  total_pnl_usd: number;
  next_trade_size: number;
  max_trades: number;
  open_positions: number;
}

interface HACandle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  trend: string;
  flip: string | null;
}

interface MarketData {
  symbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  timestamp: string;
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<"trading" | "market" | "chart">("trading");
  const [strategies, setStrategies] = useState<StrategyComparison[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [account, setAccount] = useState<Account | null>(null);
  const [marketData, setMarketData] = useState<MarketData[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Chart state
  const [selectedSymbol, setSelectedSymbol] = useState("BTCUSDT");
  const [haCandles, setHaCandles] = useState<HACandle[]>([]);
  const [loadingChart, setLoadingChart] = useState(false);
  const chartRef = useRef<HTMLDivElement>(null);

  const fetchData = async () => {
    try {
      const [compRes, tradesRes, posRes, accountRes, symbolsRes] = await Promise.all([
        fetch(`${API_URL}/api/comparison`),
        fetch(`${API_URL}/api/trades?limit=50`),
        fetch(`${API_URL}/api/positions`),
        fetch(`${API_URL}/api/account`),
        fetch(`${API_URL}/api/symbols`),
      ]);

      if (!compRes.ok || !tradesRes.ok || !posRes.ok) {
        throw new Error("Failed to fetch data");
      }

      const compData = await compRes.json();
      const tradesData = await tradesRes.json();
      const posData = await posRes.json();
      const accountData = accountRes.ok ? await accountRes.json() : null;
      const symbolsData = symbolsRes.ok ? await symbolsRes.json() : { symbols: [] };

      setStrategies(compData.comparison || []);
      setTrades(tradesData || []);
      setPositions(posData || []);
      setAccount(accountData);
      setSymbols(symbolsData.symbols || []);
      setError(null);
    } catch (err) {
      setError("Failed to connect to backend. Make sure the server is running.");
    } finally {
      setLoading(false);
    }
  };

  const fetchHACandles = async (symbol: string) => {
    setLoadingChart(true);
    try {
      const res = await fetch(`${API_URL}/api/ha-candles/${symbol}?timeframe=240`);
      if (res.ok) {
        const data = await res.json();
        setHaCandles(data.candles || []);
      }
    } catch (err) {
      console.error("Failed to fetch HA candles:", err);
    } finally {
      setLoadingChart(false);
    }
  };

  const fetchMarketData = async () => {
    try {
      const limitedSymbols = symbols.slice(0, 20);
      const candlePromises = limitedSymbols.map(async (symbol: string) => {
        try {
          const res = await fetch(`${API_URL}/api/candles/${symbol}?timeframe=5`);
          if (res.ok) {
            const candleData = await res.json();
            const candles = candleData.candles || [];
            if (candles.length > 0) {
              const latest = candles[candles.length - 1];
              return {
                symbol,
                open: latest.open,
                high: latest.high,
                low: latest.low,
                close: latest.close,
                volume: latest.volume,
                timestamp: latest.timestamp,
              };
            }
          }
        } catch {
          return null;
        }
        return null;
      });
      
      const results = await Promise.all(candlePromises);
      const validResults = results.filter((r): r is MarketData => r !== null);
      setMarketData(validResults);
    } catch (err) {
      console.error("Failed to fetch market data:", err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activeTab === "market" && symbols.length > 0 && marketData.length === 0) {
      fetchMarketData();
    }
    if (activeTab === "chart") {
      fetchHACandles(selectedSymbol);
    }
  }, [activeTab, selectedSymbol]);

  // Simple candlestick chart renderer
  const renderChart = () => {
    if (haCandles.length === 0) return null;
    
    const minPrice = Math.min(...haCandles.map(c => c.low));
    const maxPrice = Math.max(...haCandles.map(c => c.high));
    const priceRange = maxPrice - minPrice;
    const chartHeight = 400;
    const chartWidth = Math.max(haCandles.length * 12, 800);
    
    const priceToY = (price: number) => {
      return chartHeight - ((price - minPrice) / priceRange) * (chartHeight - 40) - 20;
    };

    return (
      <div className="overflow-x-auto">
        <svg width={chartWidth} height={chartHeight} className="bg-slate-800/50 rounded-lg">
          {/* Price grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
            const price = minPrice + priceRange * pct;
            const y = priceToY(price);
            return (
              <g key={pct}>
                <line x1="50" y1={y} x2={chartWidth - 10} y2={y} stroke="#334155" strokeWidth="1" />
                <text x="5" y={y + 4} fill="#64748b" fontSize="10">
                  {price.toFixed(price > 100 ? 0 : 4)}
                </text>
              </g>
            );
          })}
          
          {/* Candles */}
          {haCandles.map((candle, i) => {
            const x = 60 + i * 12;
            const isBullish = candle.trend === "bullish";
            const color = isBullish ? "#22c55e" : "#ef4444";
            
            const openY = priceToY(candle.open);
            const closeY = priceToY(candle.close);
            const highY = priceToY(candle.high);
            const lowY = priceToY(candle.low);
            
            const bodyTop = Math.min(openY, closeY);
            const bodyHeight = Math.max(Math.abs(closeY - openY), 1);
            
            return (
              <g key={i}>
                {/* Wick */}
                <line x1={x + 4} y1={highY} x2={x + 4} y2={lowY} stroke={color} strokeWidth="1" />
                
                {/* Body */}
                <rect 
                  x={x} 
                  y={bodyTop} 
                  width="8" 
                  height={bodyHeight} 
                  fill={isBullish ? color : color}
                  stroke={color}
                  strokeWidth="1"
                />
                
                {/* Flip signal marker */}
                {candle.flip && (
                  <>
                    <circle 
                      cx={x + 4} 
                      cy={candle.flip === "bullish" ? lowY + 15 : highY - 15} 
                      r="6" 
                      fill={candle.flip === "bullish" ? "#22c55e" : "#ef4444"}
                      stroke="#fff"
                      strokeWidth="1"
                    />
                    <text 
                      x={x + 4} 
                      y={(candle.flip === "bullish" ? lowY + 19 : highY - 11)} 
                      fill="#fff" 
                      fontSize="8" 
                      textAnchor="middle"
                    >
                      {candle.flip === "bullish" ? "▲" : "▼"}
                    </text>
                  </>
                )}
              </g>
            );
          })}
          
          {/* Legend */}
          <g>
            <circle cx={chartWidth - 120} cy={20} r="6" fill="#22c55e" />
            <text x={chartWidth - 110} y={24} fill="#fff" fontSize="11">Bullish Flip</text>
            <circle cx={chartWidth - 120} cy={40} r="6" fill="#ef4444" />
            <text x={chartWidth - 110} y={44} fill="#fff" fontSize="11">Bearish Flip</text>
          </g>
        </svg>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <header className="border-b border-slate-700 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              Paper Trading Dashboard
            </h1>
            <p className="text-slate-400 text-sm">4H HA Flip Strategy • 8x Leverage • Multi-Variation A/B Testing</p>
          </div>
          <div className="flex items-center gap-4">
            {account && (
              <div className="flex items-center gap-4 px-4 py-2 bg-slate-800/50 rounded-lg border border-slate-700">
                <div className="text-right">
                  <div className="text-xs text-slate-400">Balance</div>
                  <div className={`font-semibold ${account.total_pnl_usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${account.current_balance.toFixed(2)}
                  </div>
                </div>
                <div className="w-px h-8 bg-slate-600"></div>
                <div className="text-right">
                  <div className="text-xs text-slate-400">PnL</div>
                  <div className={`font-semibold ${account.total_pnl_usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {account.total_pnl_usd >= 0 ? '+' : ''}${account.total_pnl_usd.toFixed(2)}
                  </div>
                </div>
                <div className="w-px h-8 bg-slate-600"></div>
                <div className="text-right">
                  <div className="text-xs text-slate-400">Next Trade</div>
                  <div className="font-semibold text-cyan-400">${account.next_trade_size.toFixed(2)}</div>
                </div>
              </div>
            )}
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
              <span className="text-sm text-slate-400">Live</span>
            </div>
            <button 
              onClick={() => { fetchData(); if (activeTab === "chart") fetchHACandles(selectedSymbol); }}
              className="px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded-lg transition-all"
            >
              Refresh
            </button>
          </div>
        </div>
        
        {/* Tabs */}
        <div className="container mx-auto px-6">
          <div className="flex gap-1">
            <button
              onClick={() => setActiveTab("trading")}
              className={`px-4 py-2 rounded-t-lg transition-all ${
                activeTab === "trading" 
                  ? "bg-slate-800 text-cyan-400 border-t border-l border-r border-slate-700" 
                  : "text-slate-400 hover:text-white"
              }`}
            >
              📊 Trading
            </button>
            <button
              onClick={() => setActiveTab("chart")}
              className={`px-4 py-2 rounded-t-lg transition-all ${
                activeTab === "chart" 
                  ? "bg-slate-800 text-cyan-400 border-t border-l border-r border-slate-700" 
                  : "text-slate-400 hover:text-white"
              }`}
            >
              🕯️ HA Chart
            </button>
            <button
              onClick={() => setActiveTab("market")}
              className={`px-4 py-2 rounded-t-lg transition-all ${
                activeTab === "market" 
                  ? "bg-slate-800 text-cyan-400 border-t border-l border-r border-slate-700" 
                  : "text-slate-400 hover:text-white"
              }`}
            >
              📈 Market Data
            </button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-6 py-8">
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
        )}

        {error && (
          <div className="bg-red-500/20 border border-red-500/50 rounded-lg p-4 mb-6">
            <p className="text-red-400">{error}</p>
            <p className="text-slate-400 text-sm mt-2">
              Run: <code className="bg-slate-800 px-2 py-1 rounded">cd backend && uvicorn app.main:app --reload</code>
            </p>
          </div>
        )}

        {/* HA Chart Tab */}
        {!loading && activeTab === "chart" && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <span className="w-1 h-6 bg-orange-500 rounded"></span>
                Heikin-Ashi 4H Chart with Flip Signals
              </h2>
              <select 
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-white"
              >
                {(symbols.length > 0 ? symbols.slice(0, 20) : ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            
            <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700" ref={chartRef}>
              {loadingChart ? (
                <div className="flex items-center justify-center py-20">
                  <div className="w-8 h-8 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
                  <span className="ml-3 text-slate-400">Loading {selectedSymbol} chart...</span>
                </div>
              ) : haCandles.length === 0 ? (
                <div className="text-center py-20 text-slate-500">
                  No candle data available for {selectedSymbol}
                </div>
              ) : (
                <>
                  {renderChart()}
                  <div className="mt-4 flex items-center gap-4 text-sm text-slate-400">
                    <span>Total candles: {haCandles.length}</span>
                    <span>•</span>
                    <span>Flips detected: {haCandles.filter(c => c.flip).length}</span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <span className="w-3 h-3 bg-green-500 rounded-full"></span> Bullish
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-3 h-3 bg-red-500 rounded-full"></span> Bearish
                    </span>
                  </div>
                </>
              )}
            </div>
            
            {/* Recent flips table */}
            {haCandles.filter(c => c.flip).length > 0 && (
              <div className="mt-6">
                <h3 className="text-lg font-semibold mb-3">Recent Flip Signals</h3>
                <div className="bg-slate-800/50 rounded-xl overflow-hidden border border-slate-700">
                  <table className="w-full">
                    <thead className="bg-slate-700/50">
                      <tr>
                        <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Time</th>
                        <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Flip Direction</th>
                        <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Price (HA Close)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700">
                      {haCandles.filter(c => c.flip).slice(-10).reverse().map((c, i) => (
                        <tr key={i} className="hover:bg-slate-700/30">
                          <td className="px-4 py-3 text-sm text-slate-300">
                            {new Date(c.timestamp).toLocaleString()}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                              c.flip === "bullish" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                            }`}>
                              {c.flip === "bullish" ? "🟢 BULLISH" : "🔴 BEARISH"}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-white">
                            ${c.close.toFixed(c.close > 100 ? 2 : 6)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>
        )}

        {!loading && activeTab === "trading" && (
          <>
            {/* Strategy Comparison */}
            <section className="mb-10">
              <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <span className="w-1 h-6 bg-cyan-500 rounded"></span>
                Strategy Comparison
              </h2>
              <div className="bg-slate-800/50 rounded-xl overflow-hidden border border-slate-700">
                <table className="w-full">
                  <thead className="bg-slate-700/50">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Strategy</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Cooldown</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">ATR TF</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Trades</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Wins</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Losses</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Win Rate</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Total PnL</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700">
                    {strategies.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                          No strategies running yet. Waiting for first scan...
                        </td>
                      </tr>
                    ) : (
                      strategies.map((s, i) => (
                        <tr key={s.strategy_id} className="hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-3">
                            <span className={`font-medium ${i === 0 ? 'text-yellow-400' : 'text-white'}`}>
                              {i === 0 && '🏆 '}
                              {s.strategy_id.toUpperCase()}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center text-slate-300">{s.cooldown}m</td>
                          <td className="px-4 py-3 text-center text-slate-300">{s.atr_tf}m</td>
                          <td className="px-4 py-3 text-center text-slate-300">{s.total_trades}</td>
                          <td className="px-4 py-3 text-center text-green-400">{s.wins}</td>
                          <td className="px-4 py-3 text-center text-red-400">{s.losses}</td>
                          <td className="px-4 py-3 text-center">
                            <span className={`px-2 py-1 rounded-full text-sm ${
                              s.win_rate >= 60 ? 'bg-green-500/20 text-green-400' :
                              s.win_rate >= 50 ? 'bg-yellow-500/20 text-yellow-400' :
                              'bg-red-500/20 text-red-400'
                            }`}>
                              {s.win_rate.toFixed(1)}%
                            </span>
                          </td>
                          <td className={`px-4 py-3 text-center font-medium ${
                            s.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                          }`}>
                            {s.total_pnl >= 0 ? '+' : ''}{s.total_pnl.toFixed(2)}%
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Open Positions */}
            <section className="mb-10">
              <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <span className="w-1 h-6 bg-purple-500 rounded"></span>
                Open Positions ({positions.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {positions.length === 0 ? (
                  <div className="col-span-full bg-slate-800/50 rounded-xl p-6 border border-slate-700 text-center text-slate-500">
                    No open positions
                  </div>
                ) : (
                  positions.map((p, i) => (
                    <div key={i} className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
                      {/* Header with Symbol, Side, and Unrealized PnL */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-lg">{p.symbol}</span>
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            p.side === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                          }`}>
                            {p.side}
                          </span>
                        </div>
                        {p.unrealized_pnl_usd !== null && (
                          <div className={`text-right ${p.unrealized_pnl_usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            <div className="text-lg font-bold">
                              {p.unrealized_pnl_usd >= 0 ? '+' : ''}${p.unrealized_pnl_usd.toFixed(2)}
                            </div>
                            <div className="text-xs opacity-75">
                              {p.unrealized_pnl_pct !== null && `${p.unrealized_pnl_pct >= 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(2)}%`}
                            </div>
                          </div>
                        )}
                      </div>
                      
                      {/* Price Info */}
                      <div className="space-y-1.5 text-sm mb-3">
                        <div className="flex justify-between items-center">
                          <span className="text-slate-400">Entry</span>
                          <span className="font-mono">${p.entry_price.toFixed(p.entry_price > 100 ? 2 : 6)}</span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-slate-400">Current</span>
                          <span className={`font-mono font-semibold ${
                            p.current_price !== null ? 
                              ((p.side === 'LONG' && p.current_price > p.entry_price) || 
                               (p.side === 'SHORT' && p.current_price < p.entry_price) ? 'text-green-400' : 'text-red-400') 
                              : 'text-white'
                          }`}>
                            {p.current_price !== null ? `$${p.current_price.toFixed(p.current_price > 100 ? 2 : 6)}` : 'Loading...'}
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-slate-400">Stop Loss</span>
                          <span className="font-mono text-red-400">${p.current_sl.toFixed(p.current_sl > 100 ? 2 : 6)}</span>
                        </div>
                      </div>
                      
                      {/* Take Profit Levels */}
                      <div className="border-t border-slate-700 pt-3 space-y-1.5">
                        <div className="text-xs text-slate-500 mb-2">Take Profit Levels</div>
                        <div className="flex justify-between items-center text-sm">
                          <span className={`flex items-center gap-1 ${p.tp1_hit ? 'text-green-400' : 'text-slate-400'}`}>
                            {p.tp1_hit ? '✓' : '○'} TP1
                          </span>
                          <span className={`font-mono ${p.tp1_hit ? 'text-green-400' : 'text-slate-500'}`}>
                            ${p.take_profit_1?.toFixed(p.take_profit_1 > 100 ? 2 : 6)}
                          </span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                          <span className={`flex items-center gap-1 ${p.tp2_hit ? 'text-green-400' : 'text-slate-400'}`}>
                            {p.tp2_hit ? '✓' : '○'} TP2
                          </span>
                          <span className={`font-mono ${p.tp2_hit ? 'text-green-400' : 'text-slate-500'}`}>
                            ${p.take_profit_2?.toFixed(p.take_profit_2 > 100 ? 2 : 6)}
                          </span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                          <span className={`flex items-center gap-1 ${p.tp3_hit ? 'text-green-400' : 'text-slate-400'}`}>
                            {p.tp3_hit ? '✓' : '○'} TP3
                          </span>
                          <span className={`font-mono ${p.tp3_hit ? 'text-green-400' : 'text-slate-500'}`}>
                            ${p.take_profit_3?.toFixed(p.take_profit_3 > 100 ? 2 : 6)}
                          </span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                          <span className={`flex items-center gap-1 ${p.tp4_hit ? 'text-green-400' : 'text-slate-400'}`}>
                            {p.tp4_hit ? '✓' : '○'} TP4
                          </span>
                          <span className={`font-mono ${p.tp4_hit ? 'text-green-400' : 'text-slate-500'}`}>
                            ${p.take_profit_4?.toFixed(p.take_profit_4 > 100 ? 2 : 6)}
                          </span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                          <span className={`flex items-center gap-1 ${p.tp5_hit ? 'text-green-400' : 'text-slate-400'}`}>
                            {p.tp5_hit ? '✓' : '○'} TP5
                          </span>
                          <span className={`font-mono ${p.tp5_hit ? 'text-green-400' : 'text-slate-500'}`}>
                            ${p.take_profit_5?.toFixed(p.take_profit_5 > 100 ? 2 : 6)}
                          </span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                          <span className={`flex items-center gap-1 ${p.tp6_hit ? 'text-green-400' : 'text-slate-400'}`}>
                            {p.tp6_hit ? '✓' : '○'} TP6
                          </span>
                          <span className={`font-mono ${p.tp6_hit ? 'text-green-400' : 'text-slate-500'}`}>
                            ${p.take_profit_6?.toFixed(p.take_profit_6 > 100 ? 2 : 6)}
                          </span>
                        </div>
                      </div>
                      
                      {/* Footer with Strategy and Size */}
                      <div className="border-t border-slate-700 pt-3 mt-3 flex justify-between text-xs">
                        <span className="text-cyan-400">{p.strategy_id}</span>
                        <span className="text-slate-500">${p.trade_size_usd?.toFixed(0) || '100'} • 8x</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* Recent Trades */}
            <section>
              <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <span className="w-1 h-6 bg-amber-500 rounded"></span>
                Recent Trades
              </h2>
              <div className="bg-slate-800/50 rounded-xl overflow-hidden border border-slate-700">
                <table className="w-full">
                  <thead className="bg-slate-700/50">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Time</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Symbol</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Side</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Strategy</th>
                      <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Size</th>
                      <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Entry</th>
                      <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Exit</th>
                      <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">PnL</th>
                      <th className="px-4 py-3 text-center text-sm font-medium text-slate-400">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700">
                    {trades.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                          No trades yet. Waiting for signals...
                        </td>
                      </tr>
                    ) : (
                      trades.slice().reverse().map((t) => (
                        <tr key={t.id} className="hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-3 text-sm text-slate-400">
                            {new Date(t.entry_time).toLocaleString()}
                          </td>
                          <td className="px-4 py-3 font-medium">{t.symbol}</td>
                          <td className="px-4 py-3 text-center">
                            <span className={`px-2 py-1 rounded text-xs font-medium ${
                              t.side === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                            }`}>
                              {t.side}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center text-cyan-400 text-sm">{t.strategy_id}</td>
                          <td className="px-4 py-3 text-right text-slate-300">${t.trade_size_usd?.toFixed(2) || '100.00'}</td>
                          <td className="px-4 py-3 text-right text-slate-300">${t.entry_price.toFixed(4)}</td>
                          <td className="px-4 py-3 text-right text-slate-300">
                            {t.exit_price ? `$${t.exit_price.toFixed(4)}` : '-'}
                          </td>
                          <td className={`px-4 py-3 text-right font-medium ${
                            t.pnl_usd === null ? 'text-slate-500' :
                            t.pnl_usd >= 0 ? 'text-green-400' : 'text-red-400'
                          }`}>
                            {t.pnl_usd !== null ? `$${t.pnl_usd >= 0 ? '+' : ''}${t.pnl_usd.toFixed(2)}` : '-'}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`px-2 py-1 rounded text-xs ${
                              t.status === 'OPEN' ? 'bg-blue-500/20 text-blue-400' :
                              t.status === 'CLOSED' ? 'bg-slate-600/50 text-slate-400' :
                              'bg-red-500/20 text-red-400'
                            }`}>
                              {t.status}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}

        {!loading && activeTab === "market" && (
          <section>
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <span className="w-1 h-6 bg-green-500 rounded"></span>
              OHLCV Market Data (5-min candles)
              <span className="text-sm text-slate-400 font-normal ml-2">
                ({symbols.length} symbols scanned)
              </span>
            </h2>
            
            <div className="bg-slate-800/50 rounded-xl overflow-hidden border border-slate-700">
              <table className="w-full">
                <thead className="bg-slate-700/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">Symbol</th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Open</th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">High</th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Low</th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Close</th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Volume</th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Change %</th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">Last Update</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700">
                  {marketData.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                        Loading market data...
                      </td>
                    </tr>
                  ) : (
                    marketData.map((m) => {
                      const change = ((m.close - m.open) / m.open) * 100;
                      return (
                        <tr key={m.symbol} className="hover:bg-slate-700/30 transition-colors">
                          <td className="px-4 py-3 font-medium text-white">{m.symbol}</td>
                          <td className="px-4 py-3 text-right text-slate-300">{m.open.toFixed(4)}</td>
                          <td className="px-4 py-3 text-right text-green-400">{m.high.toFixed(4)}</td>
                          <td className="px-4 py-3 text-right text-red-400">{m.low.toFixed(4)}</td>
                          <td className="px-4 py-3 text-right text-white font-medium">{m.close.toFixed(4)}</td>
                          <td className="px-4 py-3 text-right text-slate-300">
                            {m.volume >= 1000000 ? `${(m.volume / 1000000).toFixed(2)}M` :
                             m.volume >= 1000 ? `${(m.volume / 1000).toFixed(2)}K` :
                             m.volume.toFixed(2)}
                          </td>
                          <td className={`px-4 py-3 text-right font-medium ${change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {change >= 0 ? '+' : ''}{change.toFixed(2)}%
                          </td>
                          <td className="px-4 py-3 text-right text-slate-400 text-sm">
                            {m.timestamp ? new Date(m.timestamp).toLocaleTimeString() : '-'}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-700 py-6 mt-10">
        <div className="container mx-auto px-6 text-center text-slate-500 text-sm">
          Bybit Paper Trading System • 8x Leverage • Scans {symbols.length || 20} futures every 5 minutes
        </div>
      </footer>
    </div>
  );
}
