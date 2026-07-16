#!/usr/bin/env python3
"""
持仓雷达引擎 — Portfolio Radar Engine
======================================
核心逻辑抽取，供 monitor.py 和 run_portfolio_radar.py 共用。

用法（作为模块）：
    from tools.portfolio_radar_engine import run_portfolio_radar_once
    html_path = run_portfolio_radar_once()
"""

import contextlib
import io
import json
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── 重定向 tgw 证书/日志路径到用户目录 ──────────────────────────────────
_mdga = os.path.join(os.path.expanduser("~"), ".workbuddy", "mdga_file")
os.environ["TGW_MDGA_PATH"] = _mdga
os.makedirs(_mdga, exist_ok=True)
os.makedirs(os.path.join(_mdga, "log"), exist_ok=True)

# ─── 证书预处理 ────────────────────────────────────────────────────────────────
try:
    import tgw
    from tgw.cert_install import CpCert
    CpCert(_mdga)
    logger.info("tgw 证书已安装到: %s", _mdga)
except Exception as e:
    logger.warning("证书预处理失败（登录时可能自动处理）: %s", e)

ROOT = Path(__file__).resolve().parent.parent

try:
    from tools.mason_signal_engine import mason_analyze_position
except Exception:  # pragma: no cover - radar can still run without Mason layer
    mason_analyze_position = None

# 输出目录：优先用环境变量，其次 WorkBuddy 工作区，最后项目 data/
_wb = os.environ.get("WB_WORKSPACE", "")
if _wb and Path(_wb).exists():
    REPORTS_DIR = Path(_wb) / "reports"
else:
    REPORTS_DIR = Path(os.environ.get("PORTFOLIO_REPORT_DIR", str(ROOT / "data")))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# 如果上面的目录不可写，再 fallback 到用户家目录
try:
    _test_file = REPORTS_DIR / ".write_test"
    _test_file.write_text("test")
    _test_file.unlink()
except Exception:
    REPORTS_DIR = Path.home() / "Niki-Smart-Tools-reports"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    logger.warning("data/ 不可写，报告将保存到: %s", REPORTS_DIR)


# ─── 环境变量兼容 ──────────────────────────────────────────────────────────────

def _get_env(*keys, default=""):
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return default


def load_local_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


load_local_env()


# ─── AmazingData 导入 ─────────────────────────────────────────────────────────

def _import_amazingdata():
    try:
        import AmazingData as ad
        return ad
    except ImportError:
        pass
    venv_site = Path(r"C:\Users\Niki_Spatial\.workbuddy\binaries\python\envs\default\Lib\site-packages")
    if venv_site.exists() and str(venv_site) not in sys.path:
        sys.path.insert(0, str(venv_site))
    try:
        import AmazingData as ad
        return ad
    except ImportError as e:
        raise RuntimeError(f"AmazingData SDK not found: {e}")


def xingyao_login():
    ad = _import_amazingdata()
    username = _get_env("AD_USERNAME", "XINGYAO_USER")
    password = _get_env("AD_PASSWORD", "XINGYAO_PASSWORD")
    host     = _get_env("AD_HOST", "XINGYAO_HOST", default="101.230.159.234")
    port     = int(_get_env("AD_PORT", "XINGYAO_PORT", default="8600"))
    if not username or not password:
        raise RuntimeError("Missing credentials: set AD_USERNAME/AD_PASSWORD")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        ad.login(username=username, password=password, host=host, port=port)
    return ad


# ─── 数据获取 ─────────────────────────────────────────────────────────

def _norm_code(code: str) -> str:
    if "." in code:
        c, ex = code.split(".", 1)
        return f"{c}.{ex.upper()}"
    return f"{code}.SH" if code.startswith(("5", "6", "9")) else f"{code}.SZ"


def fetch_radar_data(positions: list, ad, portfolio: dict | None = None) -> dict:
    base = ad.BaseData()
    calendar = base.get_calendar()
    market = ad.MarketData(calendar)

    codes_full = [_norm_code(p["code"]) for p in positions]
    today = int(datetime.now().strftime("%Y%m%d"))
    begin = int((datetime.now() - timedelta(days=40)).strftime("%Y%m%d"))

    # 1. 快照
    snapshot_map = {}
    try:
        snap = market.query_snapshot(codes_full, today, today)
        if snap:
            for code_full, val in snap.items():
                rows = val.to_dict("records") if hasattr(val, "to_dict") else (val if isinstance(val, list) else [])
                if rows:
                    snapshot_map[code_full] = rows[-1]
    except Exception as e:
        logger.warning("snapshot failed: %s", e)

    # 2. 日K线
    kline_map = {}
    try:
        klines = market.query_kline(
            code_list=codes_full,
            begin_date=begin,
            end_date=today,
            period=ad.constant.Period.day.value,
        )
        for code_full, df in klines.items():
            rows = df.to_dict("records") if hasattr(df, "to_dict") else (df if isinstance(df, list) else [])
            kline_map[code_full] = rows[-20:] if rows else []
    except Exception as e:
        logger.warning("kline failed: %s", e)

    # 3. 组合数据
    result = {}
    for pos in positions:
        cf = _norm_code(pos["code"])
        snap = snapshot_map.get(cf, {})
        krows = kline_map.get(cf, [])

        price = _pick(snap, ("last_price", "LAST_PRICE", "close_price", "CLOSE_PRICE", "close"))
        if price is None and krows:
            price = _pick(krows[-1], ("close", "CLOSE", "close_price"))

        prev_close = _pick(snap, ("pre_close_price", "PRE_CLOSE_PRICE", "pre_close", "preclose"))
        if prev_close is None and len(krows) >= 2:
            prev_close = _pick(krows[-2], ("close", "CLOSE", "close_price"))

        pct_change = _pick(snap, ("pct_change", "PCT_CHANGE", "change_rate", "chg_pct"))
        if pct_change is None and price and prev_close:
            pct_change = (price - prev_close) / prev_close * 100

        amount = _pick(snap, ("total_value_trade", "TOTAL_VALUE_TRADE", "amount"))

        closes = [_pick(row, ("close", "CLOSE", "close_price")) for row in krows]
        closes = [c for c in closes if c is not None]
        ma20 = sum(closes[-20:]) / len(closes[-20:]) if len(closes) >= 20 else (sum(closes) / len(closes) if closes else None)

        cost = pos.get("cost")
        shares = pos.get("shares", 0)
        valid_cost = cost is not None and cost > 0
        profit_pct = ((price - cost) / cost * 100) if price and valid_cost else pos.get("profit_pct")
        market_value = price * shares if price and shares else None
        cost_value = cost * shares if valid_cost and shares else None
        unrealized_pnl = (market_value - cost_value) if market_value and cost_value else None

        # 信号打分
        signal = "绿"
        reasons = []
        if pct_change is not None:
            if pct_change >= 2:
                reasons.append(f"今日涨幅 +{pct_change:.2f}%")
            elif pct_change <= -2:
                signal = "红"
                reasons.append(f"今日跌幅 {pct_change:.2f}%")
        if profit_pct is not None:
            if profit_pct < -20:
                if signal != "红":
                    signal = "黄"
                reasons.append(f"浮亏 {profit_pct:.1f}%")
            elif profit_pct < -10:
                if signal == "绿":
                    signal = "黄"
                reasons.append(f"浮亏 {profit_pct:.1f}%")
        if price and ma20:
            if price < ma20 * 0.97:
                if signal == "绿":
                    signal = "黄"
                reasons.append(f"价格低于MA20 {((price/ma20-1)*100):.1f}%")
        if "恒生科技" in pos.get("name", "") or "QDII" in pos.get("note", "").upper():
            reasons.append("QDII 溢价风险")

        result[pos["code"]] = {
            "code": pos["code"],
            "code_full": cf,
            "name": pos.get("name", ""),
            "shares": shares,
            "cost": cost,
            "price": price,
            "pct_change": pct_change,
            "prev_close": prev_close,
            "amount": amount,
            "ma20": round(ma20, 4) if ma20 else None,
            "market_value": round(market_value, 2) if market_value else None,
            "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl else None,
            "profit_pct": round(profit_pct, 2) if profit_pct is not None else None,
            "signal": signal,
            "signal_reasons": reasons,
            "target_weight": pos.get("target_weight"),
            "note": pos.get("note", ""),
            "kline_closes": closes[-20:],
            "kline_dates": [
                row.get("date") or row.get("trade_date") or row.get("TRADE_DATE", "")
                for row in krows[-20:]
            ],
        }

    # ─── 梅森分析层 ─────────────────────────────────────
    if mason_analyze_position:
        portfolio = portfolio or {"positions": positions}
        for code, item in result.items():
            try:
                mason = mason_analyze_position(item, portfolio)
                result[code].update(mason)
            except Exception as e:
                logger.warning("Mason analysis failed for %s: %s", code, e)

    return result


def _pick(obj, keys):
    """从 dict 或 DataFrame row 中按顺序取第一个非空数值。"""
    if obj is None:
        return None
    for k in keys:
        v = obj.get(k) if isinstance(obj, dict) else None
        if v not in (None, "", "nan"):
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    return None


# ─── HTML 报告生成 ─────────────────────────────────────────────────────────────

SIGNAL_COLOR = {"绿": "#00c853", "黄": "#ffab00", "红": "#f44336"}
SIGNAL_BG    = {"绿": "#1b2b1b", "黄": "#2b2b00", "红": "#2b1010"}


def _fmt(v, fmt=".2f", fallback="—"):
    if v is None:
        return fallback
    try:
        return format(float(v), fmt)
    except (ValueError, TypeError):
        return fallback


def _pct_span(v):
    if v is None:
        return "<span>—</span>"
    color = "#f44336" if v < 0 else "#00c853"
    sign = "+" if v >= 0 else ""
    return f'<span style="color:{color};font-weight:bold">{sign}{v:.2f}%</span>'


def _sparkline(closes: list, code: str) -> str:
    if len(closes) < 2:
        return '<span style="color:#666">无K线</span>'
    mn, mx = min(closes), max(closes)
    span = mx - mn if mx != mn else 1
    w, h = 120, 36
    pts = []
    for i, c in enumerate(closes):
        x = int(i / (len(closes) - 1) * w)
        y = int((1 - (c - mn) / span) * (h - 4) + 2)
        pts.append(f"{x},{y}")
    polyline = " ".join(pts)
    last_color = "#f44336" if len(closes) >= 2 and closes[-1] < closes[-2] else "#00c853"
    return (
        f'<svg width="{w}" height="{h}" style="vertical-align:middle">'
        f'<polyline points="{polyline}" fill="none" stroke="{last_color}" stroke-width="1.5"/>'
        f'</svg>'
    )


def render_html(radar: dict, portfolio: dict, run_time: str, source_ok: bool) -> str:
    total_mv = sum(v.get("market_value") or 0 for v in radar.values())
    total_capital = portfolio.get("total_capital", 0)
    cash = portfolio.get("cash", 0)
    total_pnl = sum(v.get("unrealized_pnl") or 0 for v in radar.values())

    order = {"红": 0, "黄": 1, "绿": 2}
    sorted_items = sorted(radar.values(), key=lambda x: order.get(x["signal"], 2))

    rows_html = ""
    for item in sorted_items:
        sig = item["signal"]
        color = SIGNAL_COLOR[sig]
        bg = SIGNAL_BG[sig]
        pct_span = _pct_span(item.get("pct_change"))
        profit_span = _pct_span(item.get("profit_pct"))
        spark = _sparkline(item.get("kline_closes", []), item["code"])
        reasons_html = ""
        for r in item.get("signal_reasons", []):
            reasons_html += f'<span style="background:#333;border-radius:3px;padding:1px 6px;margin:1px;font-size:11px;color:#ccc">{r}</span>'
        if not reasons_html:
            reasons_html = '<span style="color:#555;font-size:11px">无异常信号</span>'

        # ── 梅森判断列 ─────────────────────────────────────
        mason_action = item.get("mason_action", "—")
        mason_theme  = item.get("mason_main_theme", "")
        mason_dev    = item.get("mason_deviation", "")
        mason_same   = item.get("mason_same_dir", "")
        # 动作颜色
        _act_color = "#00c853" if "吸" in mason_action or "持" in mason_action else ("#f44336" if "清" in mason_action or "减" in mason_action else "#ffab00")
        mason_html = (
            f'<div style="font-weight:bold;font-size:13px;color:{_act_color}">{mason_action}</div>'
            f'<div style="color:#999;font-size:11px;margin-top:2px">{mason_theme}</div>'
            f'<div style="color:#888;font-size:11px;margin-top:3px">{mason_dev}</div>'
            f'<div style="color:#888;font-size:11px;margin-top:2px">{mason_same}</div>'
        )

        mv = _fmt(item.get("market_value"), ",.0f") if item.get("market_value") else "—"
        pnl = item.get("unrealized_pnl")
        pnl_str = f'<span style="color:{"#f44336" if pnl and pnl<0 else "#00c853"}">{("+" if pnl and pnl>=0 else "")}{_fmt(pnl,",.0f")}</span>' if pnl is not None else "—"

        rows_html += f"""
        <tr style="background:{bg};border-bottom:1px solid #222">
          <td style="padding:10px 8px">
            <div style="font-weight:bold;font-size:15px;color:#eee">{item['name']}</div>
            <div style="color:#666;font-size:12px">{item['code']}</div>
          </td>
          <td style="text-align:center;padding:8px">
            <span style="background:{color};color:#000;font-weight:bold;padding:3px 10px;border-radius:12px;font-size:13px">{sig}</span>
          </td>
          <td style="text-align:right;padding:8px;font-size:16px;color:#eee;font-weight:bold">{_fmt(item.get('price'),",.4f") if item.get('price') else '—'}</td>
          <td style="text-align:right;padding:8px">{pct_span}</td>
          <td style="text-align:center;padding:8px">{spark}</td>
          <td style="text-align:right;padding:8px;color:#aaa;font-size:13px">{_fmt(item.get('cost'),",.4f") if item.get('cost') else '—'}</td>
          <td style="text-align:right;padding:8px">{profit_span}</td>
          <td style="text-align:right;padding:8px;color:#bbb;font-size:13px">¥{mv}</td>
          <td style="text-align:right;padding:8px">{pnl_str}</td>
          <td style="padding:8px;font-size:12px">{reasons_html}</td>
          <td style="padding:10px 8px;min-width:180px">{mason_html}</td>
        </tr>
        """

    total_pnl_color = "#f44336" if total_pnl < 0 else "#00c853"
    total_pnl_str = f'{"+" if total_pnl >= 0 else ""}¥{total_pnl:,.0f}'
    source_badge = (
        '<span style="background:#1a3a1a;color:#00c853;padding:2px 8px;border-radius:4px;font-size:12px">★ 星耀数智实时</span>'
        if source_ok else
        '<span style="background:#3a1a1a;color:#f44336;padding:2px 8px;border-radius:4px;font-size:12px">⚠ 数据获取异常</span>'
    )

    # ── 梅森摘要卡片 ─────────────────────────────────────
    _buy_cnt   = sum(1 for v in radar.values() if "吸" in (v.get("mason_action") or "") or "持" in (v.get("mason_action") or ""))
    _sell_cnt  = sum(1 for v in radar.values() if "清" in (v.get("mason_action") or "") or "减" in (v.get("mason_action") or ""))
    _warn_cnt   = len(radar) - _buy_cnt - _sell_cnt
    _main_themes = set(v.get("mason_theme","") for v in radar.values() if v.get("mason_is_main"))
    _summary_note = (
        f"主线方向：{'、'.join(_main_themes) if _main_themes else '暂无'}"
        f"｜建议买入/持有 {_buy_cnt} 只，减/清 {_sell_cnt} 只，观察 {_warn_cnt} 只"
    )
    mason_summary_html = f"""
<div class="mason-grid">
  <div class="mason-card {'buy' if _buy_cnt >= _sell_cnt else 'warn'}">
    <div style="color:#999;font-size:12px">梅森动作概览</div>
    <div style="font-size:18px;font-weight:bold;color:#eee;margin:6px 0">{_summary_note.split('｜')[-1]}</div>
    <div style="color:#888;font-size:11px">基于顺大势逆小势 + 账户纪律</div>
  </div>
  <div class="mason-card {'buy' if _buy_cnt > 0 else 'warn'}">
    <div style="color:#999;font-size:12px">主线判断</div>
    <div style="font-size:14px;color:#eee;margin:6px 0">{'、'.join(_main_themes) if _main_themes else '暂无主线数据'}</div>
    <div style="color:#888;font-size:11px">主线可操作，支线只观察</div>
  </div>
  <div class="mason-card {'sell' if _sell_cnt > 0 else 'buy'}">
    <div style="color:#999;font-size:12px">账户风险提示</div>
    <div style="font-size:14px;color:#eee;margin:6px 0">{'⚠ 有 {_sell_cnt} 只需处理' if _sell_cnt > 0 else '✅ 无紧急风险'}</div>
    <div style="color:#888;font-size:11px">止损线 -8% 减仓、-12% 清仓</div>
  </div>
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>持仓雷达 — {run_time}</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0 }}
  body {{ background:#111; color:#ddd; font-family:'PingFang SC','Microsoft YaHei',sans-serif; padding:20px }}
  h1 {{ font-size:22px; color:#eee; margin-bottom:4px }}
  .meta {{ color:#555; font-size:12px; margin-bottom:20px }}
  .summary-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:24px }}
  .card {{ background:#1a1a1a; border-radius:8px; padding:14px 16px }}
  .card-label {{ color:#666; font-size:12px; margin-bottom:4px }}
  .card-value {{ font-size:20px; font-weight:bold; color:#eee }}
  .card-sub {{ color:#555; font-size:11px; margin-top:2px }}
  .mason-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:20px }}
  .mason-card {{ background:#1a1a2a; border-radius:8px; padding:14px 16px; border-left:4px solid #666 }}
  .mason-card.buy   {{ border-left-color:#00c853 }}
  .mason-card.warn  {{ border-left-color:#ffab00 }}
  .mason-card.sell {{ border-left-color:#f44336 }}
  table {{ width:100%; border-collapse:collapse }}
  th {{ background:#1a1a1a; color:#666; font-size:12px; padding:8px; text-align:left; white-space:nowrap }}
  tr:hover td {{ filter:brightness(1.2) }}
  .footer {{ margin-top:20px; color:#444; font-size:11px; text-align:center }}
  @media(max-width:768px){{.summary-grid{{grid-template-columns:repeat(2,1fr)}}.mason-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<h1>📊 持仓ETF雷达</h1>
<div class="meta">
  更新时间：{run_time} &nbsp;|&nbsp; {source_badge}
</div>

<div class="summary-grid">
  <div class="card">
    <div class="card-label">总资产估算</div>
    <div class="card-value">¥{(total_mv + cash):,.0f}</div>
    <div class="card-sub">市值 ¥{total_mv:,.0f} + 现金 ¥{cash:,.0f}</div>
  </div>
  <div class="card">
    <div class="card-label">浮动盈亏</div>
    <div class="card-value" style="color:{total_pnl_color}">{total_pnl_str}</div>
    <div class="card-sub">持仓合计未实现PnL</div>
  </div>
  <div class="card">
    <div class="card-label">仓位数量</div>
    <div class="card-value">{len(radar)}</div>
    <div class="card-sub">ETF持仓只数</div>
  </div>
  <div class="card">
    <div class="card-label">信号概况</div>
    <div class="card-value">
      <span style="color:#f44336">{sum(1 for v in radar.values() if v['signal']=='红')}红</span>
      <span style="color:#555"> / </span>
      <span style="color:#ffab00">{sum(1 for v in radar.values() if v['signal']=='黄')}黄</span>
      <span style="color:#555"> / </span>
      <span style="color:#00c853">{sum(1 for v in radar.values() if v['signal']=='绿')}绿</span>
    </div>
    <div class="card-sub">红=需关注, 黄=观察, 绿=正常</div>
  </div>
</div>

{mason_summary_html}

<table>
  <thead>
    <tr>
      <th>标的</th><th>信号</th><th>当前价</th><th>今日涨跌</th>
      <th>20日走势</th><th>成本</th><th>持仓盈亏</th>
      <th>市值</th><th>浮盈/亏</th><th>信号原因</th>
      <th>🧠 梅森判断</th>
    </tr>
  </thead>
  <tbody>
{rows_html}
  </tbody>
</table>

<div class="footer">
  Niki-Smart-Tools 持仓雷达 · 数据来源：星耀数智 AmazingData · 仅供参考，不构成投资建议<br>
  每次运行覆盖更新 data/portfolio_radar.html
</div>
</body>
</html>
"""


# ─── 主入口（供外部调用） ─────────────────────────────────────────────────────

def run_portfolio_radar_once(portfolio_path: str = None) -> str:
    """
    执行一次持仓雷达数据获取和报告生成。
    返回生成的 HTML 文件路径（字符串），失败时返回空字符串。
    """
    # 加载持仓
    if portfolio_path:
        pf_path = Path(portfolio_path)
    else:
        pf_path = ROOT / "portfolio.local.json"
        if not pf_path.exists():
            pf_path = ROOT / "portfolio.json"
    if not pf_path.exists():
        logger.error("Portfolio file not found: %s", pf_path)
        return ""

    portfolio = json.loads(pf_path.read_text(encoding="utf-8"))
    positions = portfolio.get("positions", [])
    logger.info("Portfolio radar: loaded %d positions from %s", len(positions), pf_path)

    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_ok = False
    radar = {}

    try:
        logger.info("Portfolio radar: logging in to Xingyao...")
        ad = xingyao_login()
        logger.info("Portfolio radar: login OK, fetching data...")
        radar = fetch_radar_data(positions, ad, portfolio=portfolio)
        source_ok = any(v.get("price") is not None for v in radar.values())
        logger.info("Portfolio radar: data fetched, source_ok=%s", source_ok)
        with contextlib.suppress(Exception), contextlib.redirect_stdout(io.StringIO()):
            ad.logout()
    except Exception as e:
        logger.error("Portfolio radar: Xingyao connection failed: %s", e)
        # 生成空结构
        for pos in positions:
            radar[pos["code"]] = {
                "code": pos["code"], "code_full": pos["code"],
                "name": pos.get("name", ""), "shares": pos.get("shares"),
                "cost": pos.get("cost"), "price": None, "pct_change": None,
                "prev_close": None, "amount": None, "ma20": None,
                "market_value": None, "unrealized_pnl": None,
                "profit_pct": pos.get("profit_pct"), "signal": "黄",
                "signal_reasons": [f"数据获取失败: {e}"],
                "target_weight": pos.get("target_weight"), "note": pos.get("note", ""),
                "kline_closes": [], "kline_dates": [],
            }

    # 保存 JSON
    json_out = REPORTS_DIR / "portfolio_radar.json"
    json_data = {
        "run_time": run_time, "source_ok": source_ok,
        "portfolio_file": str(pf_path), "positions": list(radar.values()),
    }
    json_out.write_text(json.dumps(json_data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.info("Portfolio radar: JSON saved: %s", json_out)

    # 生成 HTML
    html_out = REPORTS_DIR / "portfolio_radar.html"
    html_content = render_html(radar, portfolio, run_time, source_ok)
    html_out.write_text(html_content, encoding="utf-8")
    logger.info("Portfolio radar: HTML saved: %s", html_out)

    # 打印摘要
    print("\n" + "=" * 60)
    print(f"  持仓ETF雷达  |  {run_time}")
    print("=" * 60)
    for item in sorted(radar.values(), key=lambda x: {"红": 0, "黄": 1, "绿": 2}.get(x["signal"], 2)):
        sig = item["signal"]
        price_str = f"{item['price']:.4f}" if item.get("price") else "N/A"
        pct_str = f"{item['pct_change']:+.2f}%" if item.get("pct_change") is not None else "N/A"
        pnl_str = f"浮亏{item['profit_pct']:.1f}%" if item.get("profit_pct") is not None and item["profit_pct"] < 0 else (f"浮盈{item['profit_pct']:.1f}%" if item.get("profit_pct") is not None else "")
        print(f"  [{sig}] {item['name']:12s}  价格:{price_str}  今日:{pct_str}  {pnl_str}")
    print("=" * 60)
    print(f"  报告已保存: {html_out}")
    print()

    return str(html_out)


if __name__ == "__main__":
    html_path = run_portfolio_radar_once()
    if html_path:
        import webbrowser
        webbrowser.open(html_path)
