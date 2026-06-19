#!/usr/bin/env python3
"""
持仓ETF雷达 - Portfolio Radar (CLI 入口)
======================================
每次运行：用星耀数智拉取持仓5只ETF的实时行情 + 近期K线 + 仓位状态，
生成 data/portfolio_radar.html 和 data/portfolio_radar.json。

用法：
    python run_portfolio_radar.py
    python run_portfolio_radar.py --portfolio portfolio.local.json
    python run_portfolio_radar.py --open

数据引擎：tools/portfolio_radar_engine.py
"""
import sys
from pathlib import Path

# 把项目根目录加入 sys.path，使 import tools 可行
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.portfolio_radar_engine import run_portfolio_radar_once


def main():
    import argparse
    parser = argparse.ArgumentParser(description="持仓ETF雷达 (星耀数智)")
    parser.add_argument("--portfolio", default=None, help="portfolio JSON文件路径")
    parser.add_argument("--open", action="store_true", help="生成后在浏览器打开")
    args = parser.parse_args()

    html_path = run_portfolio_radar_once(portfolio_path=args.portfolio)

    if html_path and args.open:
        import webbrowser
        webbrowser.open(html_path)

    return html_path is not None


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
