#!/usr/bin/env python3
"""
Mason signal layer for the portfolio radar.

This module keeps the Mason/梅森 action-card rules separate from Xingyao data
fetching and HTML rendering. It is decision support only; it never places orders.
"""

from __future__ import annotations

from typing import Any


SECURITY_THEME_MAP: dict[str, dict[str, Any]] = {
    "588000": {"name": "科创50ETF", "theme": "科技", "sub": "半导体/芯片", "is_main": True},
    "512100": {"name": "中证1000ETF", "theme": "科技", "sub": "中小盘成长", "is_main": True},
    "512760": {"name": "半导体ETF", "theme": "科技", "sub": "半导体", "is_main": True},
    "515050": {"name": "通信ETF", "theme": "科技", "sub": "AI光互联", "is_main": True},
    "600487": {"name": "亨通光电", "theme": "科技", "sub": "CPO/光纤光缆", "is_main": True},
    "600869": {"name": "远东股份", "theme": "电网", "sub": "线缆/智能电网", "is_main": False},
    "600460": {"name": "士兰微", "theme": "科技", "sub": "功率半导体", "is_main": True},
    "605376": {"name": "博迁新材", "theme": "小金属", "sub": "MLCC/电子金属粉体", "is_main": True},
    "600549": {"name": "厦门钨业", "theme": "小金属", "sub": "钨/稀土/新材料", "is_main": True},
    "000725": {"name": "京东方A", "theme": "电子", "sub": "面板/电子周期", "is_main": False},
    "603678": {"name": "火炬电子", "theme": "电子", "sub": "军工电子/元器件", "is_main": False},
    "510300": {"name": "沪深300ETF", "theme": "宽基", "sub": "大盘", "is_main": False},
    "510500": {"name": "中证500ETF", "theme": "宽基", "sub": "中盘", "is_main": False},
    "512000": {"name": "券商ETF", "theme": "金融", "sub": "券商", "is_main": False},
    "512880": {"name": "证券ETF", "theme": "金融", "sub": "券商", "is_main": False},
    "513130": {"name": "恒生科技ETF", "theme": "港股", "sub": "科技港股", "is_main": False},
    "513180": {"name": "恒生科技ETF", "theme": "港股", "sub": "科技港股", "is_main": False},
    "518880": {"name": "黄金ETF", "theme": "避险", "sub": "黄金", "is_main": False},
    "159870": {"name": "化工ETF", "theme": "周期", "sub": "化工", "is_main": False},
    "513310": {"name": "中韩半导体ETF", "theme": "科技", "sub": "半导体", "is_main": True},
}


ACCOUNT_PARAMS: dict[str, Any] = {
    "total_assets": 450000,
    "max_single_weight": 0.25,
    "max_theme_weight": {
        "科技": 0.50,
        "金融": 0.30,
        "港股": 0.20,
        "周期": 0.15,
        "小金属": 0.20,
        "电子": 0.20,
    },
    "stop_loss_single": -0.08,
    "stop_loss_clear": -0.12,
}


def base_code(code: str | None) -> str:
    """Return the six-digit security code without exchange suffix."""
    if not code:
        return ""
    return str(code).split(".", 1)[0].strip()


def security_theme(code: str | None) -> dict[str, Any]:
    """Return theme metadata for a security code."""
    return SECURITY_THEME_MAP.get(
        base_code(code),
        {"name": base_code(code), "theme": "未知", "sub": "", "is_main": False},
    )


def _same_theme_positions(code: str, portfolio: dict[str, Any], theme: str) -> list[str]:
    held: list[str] = []
    for pos in portfolio.get("positions", []):
        pos_code = pos.get("code", "")
        if base_code(pos_code) == base_code(code):
            continue
        if security_theme(pos_code).get("theme") == theme:
            held.append(str(pos_code))
    return held


def mason_analyze_position(item: dict[str, Any], portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Build a Mason-style action card for one holding/watchlist row.

    The input `portfolio` must be the same portfolio object that produced the
    radar rows. This avoids accidentally analyzing a local/private portfolio
    with the public example portfolio.
    """
    portfolio = portfolio or {"positions": []}
    code = item.get("code", "")
    price = item.get("price")
    ma20 = item.get("ma20")
    pct = item.get("pct_change", 0) or 0
    kline_closes = item.get("kline_closes", [])
    shares = item.get("shares", 0) or 0
    already_held = shares > 0

    theme_info = security_theme(code)
    theme = theme_info["theme"]
    is_main = bool(theme_info["is_main"])

    trend_ok = False
    if price and ma20:
        if price > ma20:
            trend_ok = True
            trend_note = f"价格站上MA20（{price:.4f} > {ma20:.4f}）✅"
        else:
            trend_note = f"价格低于MA20（{price:.4f} < {ma20:.4f}）⚠"
    else:
        trend_note = "MA20数据缺失，无法判断趋势"

    deviation = None
    if price and ma20:
        deviation = (price - ma20) / ma20 * 100
        if deviation > 5:
            deviation_note = f"乖离率+{deviation:.1f}%，偏离过大，不追高 ❌"
        elif deviation < -3:
            deviation_note = f"乖离率{deviation:.1f}%，超跌区，可关注双跌买点 🔍"
        else:
            deviation_note = f"乖离率{deviation:+.1f}%，正常区间 ✅"
    else:
        deviation_note = "乖离率数据不足"

    double_drop = False
    double_drop_note = "K线数据不足，无法判断双跌买点"
    if len(kline_closes) >= 5:
        recent = kline_closes[-5:]
        lows = []
        for i in range(1, len(recent) - 1):
            if recent[i] < recent[i - 1] and recent[i] < recent[i + 1]:
                lows.append((i, recent[i]))
        if len(lows) >= 2:
            _, first_val = lows[-2]
            _, second_val = lows[-1]
            if second_val >= first_val * 0.98:
                double_drop = True
                double_drop_note = f"近5日出现双跌买点（第二跌{second_val:.4f} ≥ 第一跌{first_val:.4f}）✅"
            else:
                double_drop_note = "近5日有两次回跌，但第二跌破位 ⚠"
        else:
            double_drop_note = "近5日未出现明显双跌形态"

    same_theme_held = _same_theme_positions(code, portfolio, theme)
    if same_theme_held:
        same_dir_note = f"账户已有同方向（{theme}）：{', '.join(same_theme_held)} ⚠ 谨慎加仓"
    else:
        same_dir_note = f"账户无同方向（{theme}）持仓 ✅"

    action = "持有，不加" if already_held else "观察"
    if pct > 3:
        chase_note = f"今日涨幅+{pct:.1f}%，追高风险 ❌"
        action = "持有，不加" if already_held else "不买，等回踩"
    elif pct < -2:
        chase_note = f"今日跌幅{pct:.1f}%，关注承接"
        if double_drop and trend_ok:
            action = "可低吸（核心仓1/3）" if not already_held else "可小T，不追满"
    else:
        chase_note = ""
        if trend_ok and not same_theme_held:
            action = "持有观察" if already_held else "可关注"
        elif trend_ok and same_theme_held:
            action = "持有，不加" if already_held else "不买，同向已够"

    profit_pct = item.get("profit_pct")
    if profit_pct is not None:
        if profit_pct < -12:
            stop_note = f"浮亏{profit_pct:.1f}%，已达清仓线 ❌ 建议清仓"
            action = "清仓"
        elif profit_pct < -8:
            stop_note = f"浮亏{profit_pct:.1f}%，已达减仓线 ⚠ 建议减仓"
            action = "减仓"
        elif profit_pct > 20:
            stop_note = f"浮盈{profit_pct:.1f}%，可考虑止盈 ✅"
        else:
            stop_note = f"浮盈/亏{profit_pct:+.1f}%，在正常区间"
    else:
        stop_note = ""

    main_theme_note = f"{theme_info['sub']} {'是主线 ✅' if is_main else '是支线，脉冲行情 ⚠'}"

    return {
        "mason_action": action,
        "mason_trend": trend_note,
        "mason_deviation": deviation_note,
        "mason_double_drop": double_drop_note,
        "mason_same_dir": same_dir_note,
        "mason_chase": chase_note,
        "mason_stop": stop_note,
        "mason_main_theme": main_theme_note,
        "mason_deviation_pct": round(deviation, 2) if deviation is not None else None,
        "mason_theme": theme,
        "mason_is_main": is_main,
    }
