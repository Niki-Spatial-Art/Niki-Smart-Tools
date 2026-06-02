# GitHub Quant Source Triage

Date: 2026-06-02

This note records which pasted GitHub/news sources should enter the system and
which should stay out. The boundary is unchanged: research, paper-trade review,
data quality, and human-confirmed action cards only. No automatic live orders.

## Added To Learning Intake

| Source | Layer | Why |
| --- | --- | --- |
| CTBZStock | A-share paper/live architecture review | Study environment separation, Feishu notification, and broker/API risk boundaries. Do not copy auto-trading behavior. |
| Backtrader | Backtest layer | Useful event-driven pattern for action-card T+1, stop, take-profit, and sizing tests. |
| learn_backtrader | Backtest tutorial | Starter examples for converting simple rules into reproducible Backtrader experiments. |
| RQAlpha | A-share backtest reference | A-share-oriented account and risk simulation reference. |
| QUANTAXIS | China-market workflow reference | Useful ecosystem map, but freshness must be checked before adopting details. |
| TA-Lib | Indicator standardization | Reference for MACD, RSI, Bollinger, ATR, and volatility features. |
| TuShare | Data connector candidate | A-share/fundamental data source to compare with iFind, Eastmoney, AKShare. |
| yfinance | Overseas/QDII context | US ETF/global-market fallback for Nasdaq, S&P, AI/semiconductor context. |
| QuantLib | Option/risk modeling | Future option-simulation and Greeks/rates reference. |
| Freqtrade | Crypto architecture reference | Study config/backtest/risk-control design only. |
| Hummingbot | Connector/risk architecture reference | Crypto market-making architecture reference only. |
| FinGPT | AI research assistant | Useful for financial sentiment/RAG patterns; output must be evidence-ranked and never a direct trading signal. |
| Qbot | AI quant platform reference | Useful ecosystem reference for research/backtest/visualization flow; do not enable auto execution. |
| ai_quant_trade | Learning syllabus | Broad Chinese AI-quant map; use for study structure and example discovery, not as production code. |
| MilleXi stock_trading | AI/RL education sample | LSTM plus reinforcement learning and Gradio UI; use only for experiment design and learning. |
| czsc | Technical-analysis reference | Chan theory fractal/stroke/signal toolkit; validate every signal before use. |
| SmartStock-AI-Kit | Watch-terminal UX | Voice alert, hardware display, and compact watchlist interaction reference; observe only. |
| easytrader | Broker-boundary research | Study miniqmt/client automation boundaries only; paper-account or human-confirmed mode. |
| ths_trade | Execution risk sample | Useful queue/log/failure-mode ideas from Tonghuashun automation; do not run unattended live orders. |
| THSTrader | UI automation risk sample | Useful for understanding mobile/simulation UI-state risk; research/paper mode only. |
| AI Trading Journal | Review UX | Useful UI reference for AI conversation capture, trade journaling, and post-trade attribution. |
| CCXT | Crypto connector reference | Unified exchange API and market-data abstraction; useful only for connector design, not A-share execution. |
| BingoCrypto Binance Futures Dashboard | Dashboard UX | Filter, alert, table, and rule-highlighting reference for monitoring UX; do not copy futures signals. |
| TradeMatcher match-engine | Matching-engine architecture | Java orderbook/risk/accounting architecture reference; no direct integration. |
| lightning-engine | Matching-engine architecture | Go in-memory orderbook and settlement-boundary reference; no direct integration. |

## Already Covered

| Source | Existing Coverage |
| --- | --- |
| vn.py / VeighNa | Already in learning sources and execution roadmap. |
| Qlib | Already in learning sources and roadmap. |
| AKShare | Already in learning sources and data-source plan. |
| FinRL | Already in learning sources. |
| QuantConnect Lean | Already in learning sources and roadmap. |
| WonderTrader | Already in execution roadmap. |

## Do Not Add As Core Sources

| Source | Reason |
| --- | --- |
| weipan_qihuo | Old ThinkPHP micro-trading system; unrelated to the current read-only A-share radar and likely high security/quality risk. |
| huobi_intf | Old crypto quote server; can be replaced by CCXT/OKX/Freqtrade references already present. Not useful for A-share radar. |
| GridTradeSystem | Very small TSLA grid-trading plan; educational only and not useful enough for the main source list. |
| zhugege-BTC-ETH- | Crypto-exchange source package with operational/legal/security risk; not aligned with personal A-share/ETF decision support. |
| CoinExchange | Full crypto-exchange system source; study no code from it unless doing a separate security architecture review. |
| BKExchange | Mostly exchange/commercial demo material; not useful for current radar/backtest/journal stack. |
| stock-1 / wingfirefly stock | Old/forked Eastmoney auto-trading stack; keep out of the core system because of broker/API and maintenance risk. |
| AutoTrade | Very old Guangfa web automation framework; useful historically, but too stale and execution-risky for current use. |
| CtpSystem | Old SHFE/CTP learning project; useful background only, but too stale and execution-oriented for the current A-share/ETF radar. |
| PyTradingSystem | Early-stage trading-system skeleton with real-trading ambition; too small and stale for core intake. |
| nof1.ai-AI-trading-agent | Browser demo for crypto AI auto-trading; useful as UI/risk caution only, not a source of trading logic. |
| Forked czsc mirror | Do not track stale forks such as `gongxianshengjiadexiaohuihui/-`; track upstream `waditu/czsc` instead. |
| CryptocurrencyExchangeTechnology article | Matching-engine architecture idea is interesting, but the pasted repo path could not be verified through GitHub API; keep as unverified architecture reading only. |
| Alpaca-MCP / Freqtrade-MCP / Investor-Agent article claims | Treat as marketing until primary repos and claims are verified. Do not intake return claims or nanosecond/FPGA statements. |
| Unverified MCP/AI article claims | Claims like extreme returns, nanosecond parsing, or unnamed MCP projects need primary GitHub/source verification before intake. |

## News/Catalyst Handling

The Microsoft Build item is useful as a catalyst note for AI infrastructure
themes, not as a code source. It should influence watchlist review only through
fresh market data and sector confirmation:

- AI model/platform news: AI software, cloud, Windows ecosystem.
- GitHub/developer trust: developer tooling and Copilot ecosystem.
- Hardware adaptation: NVIDIA/AI PC/edge inference chain.
- A-share related observation buckets: CPO, PCB, MLCC, semiconductor, data-center hardware.

No trade should be generated from the news item alone.
