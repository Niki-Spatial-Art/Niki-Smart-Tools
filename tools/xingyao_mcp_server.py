"""
星耀 AmazingData MCP Server

将星耀 AmazingData Python SDK 封装为标准 MCP (Model Context Protocol) stdio 服务。
使 AI Agent 可以通过 MCP 工具直接调用星耀数据，无需编写 Python 代码。

## 提供的工具

| 工具名 | 功能 |
|--------|------|
| xingyao_health | 连接健康检查 |
| xingyao_calendar | 获取交易日历 |
| xingyao_kline | 获取历史 K 线 |
| xingyao_snapshot | 获取实时快照 |
| xingyao_income | 获取利润表 |
| xingyao_balance | 获取资产负债表 |
| xingyao_search_stocks | 搜索股票/ETF 代码 |
| xingyao_diagnostics | 运行完整诊断 |

## 使用方式

在 WorkBuddy / Claude Desktop 的 mcp.json 中添加：

```json
{
  "mcpServers": {
    "xingyao": {
      "command": "python",
      "args": ["tools/xingyao_mcp_server.py"],
      "env": {
        "AD_USERNAME": "你的账号",
        "AD_PASSWORD": "你的密码",
        "AD_HOST": "101.230.159.234",
        "AD_PORT": "8600",
        "XINGYAO_SDK_PATHS": "C:\\path\\to\\星耀数智;C:\\path\\to\\星耀数智\\AmazingData"
      }
    }
  }
}
```

依赖: mcp (pip install mcp)
"""

import os
import sys
import json
import logging
from typing import Any

# 将项目根目录加入 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING)


def _try_import_mcp():
    """尝试导入 MCP SDK。"""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
        return Server, stdio_server, Tool, TextContent
    except ImportError:
        print(
            "MCP SDK 未安装。请运行: pip install mcp",
            file=sys.stderr,
        )
        sys.exit(1)


Server, stdio_server, Tool, TextContent = _try_import_mcp()

# ---------------------------------------------------------------------------
# 工具定义
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="xingyao_health",
        description="检查星耀 AmazingData 连接状态：登录是否成功、数据源是否在线。",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="xingyao_calendar",
        description="获取 A 股交易日历列表。返回最近若干个交易日。",
        inputSchema={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "返回最近的交易日数量，默认 20",
                    "default": 20,
                },
            },
        },
    ),
    Tool(
        name="xingyao_kline",
        description="获取股票或 ETF 的历史 K 线数据。支持日/周/月/分钟级别。",
        inputSchema={
            "type": "object",
            "properties": {
                "codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "代码列表，如 ['510050.SH', '588000.SH']",
                },
                "begin_date": {
                    "type": "integer",
                    "description": "开始日期 YYYYMMDD，如 20260601",
                },
                "end_date": {
                    "type": "integer",
                    "description": "结束日期 YYYYMMDD，如 20260618",
                },
                "period": {
                    "type": "string",
                    "description": "周期: day/week/month/min1/min5/min15/min30/min60",
                    "default": "day",
                },
            },
            "required": ["codes", "begin_date", "end_date"],
        },
    ),
    Tool(
        name="xingyao_snapshot",
        description="获取股票或 ETF 的实时快照（最新价、涨跌幅、成交量等）。",
        inputSchema={
            "type": "object",
            "properties": {
                "codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "代码列表，如 ['510050.SH', '600519.SH']",
                },
            },
            "required": ["codes"],
        },
    ),
    Tool(
        name="xingyao_income",
        description="获取上市公司利润表。",
        inputSchema={
            "type": "object",
            "properties": {
                "codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "代码列表，如 ['600519.SH']",
                },
            },
            "required": ["codes"],
        },
    ),
    Tool(
        name="xingyao_balance",
        description="获取上市公司资产负债表。",
        inputSchema={
            "type": "object",
            "properties": {
                "codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "代码列表",
                },
            },
            "required": ["codes"],
        },
    ),
    Tool(
        name="xingyao_search_stocks",
        description="在 A 股或 ETF 代码列表中搜索匹配关键词的标的。",
        inputSchema={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，如 '科创50'、'茅台'、'恒生科技'",
                },
                "security_type": {
                    "type": "string",
                    "description": "证券类型: stock(A股) / etf(ETF) / all(全部)",
                    "default": "all",
                },
            },
            "required": ["keyword"],
        },
    ),
    Tool(
        name="xingyao_diagnostics",
        description="运行星耀 AmazingData 完整诊断：登录、交易日历、代码列表、K线采样。返回 JSON 状态报告。",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]

# ---------------------------------------------------------------------------
# 工具处理器
# ---------------------------------------------------------------------------

# 全局导入缓存
_xingyao = None


def _get_connector():
    """延迟导入星耀连接器。"""
    global _xingyao
    if _xingyao is None:
        from connectors import xingyao as _xingyao
    return _xingyao


def _safe_json(obj: Any) -> str:
    """安全地序列化为 JSON 字符串。"""
    try:
        if hasattr(obj, "to_dict"):
            return json.dumps(obj.to_dict(), ensure_ascii=False, default=str)
        if hasattr(obj, "to_json"):
            return obj.to_json(force_ascii=False)
        return json.dumps(obj, ensure_ascii=False, default=str, indent=2)
    except Exception:
        return str(obj)


def handle_health() -> str:
    """处理健康检查。"""
    xq = _get_connector()
    result = {
        "configured": xq.is_configured(),
        "enabled": xq.is_enabled(),
        "sdk_paths": xq.xingyao_sdk_paths(),
    }
    if not result["configured"]:
        result["status"] = "unconfigured"
        return json.dumps(result, ensure_ascii=False, indent=2)
    try:
        xq.login()
        result["status"] = "healthy"
        result["message"] = "星耀 AmazingData 连接正常"
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    return json.dumps(result, ensure_ascii=False, indent=2)


def handle_calendar(count: int = 20) -> str:
    """处理交易日历查询。"""
    xq = _get_connector()
    calendar = xq.get_calendar()
    recent = calendar[-count:] if count > 0 else calendar
    return json.dumps(
        {"total": len(calendar), "recent": recent, "latest": calendar[-1]},
        ensure_ascii=False,
    )


def handle_kline(codes: list, begin_date: int, end_date: int, period: str = "day") -> str:
    """处理 K 线查询。"""
    xq = _get_connector()
    try:
        result = xq.get_kline(codes, begin_date, end_date, period)
        output = {}
        for code, df in result.items():
            if df is not None and len(df) > 0:
                # 只返回最后 5 条避免过大
                rows = df.tail(5).to_dict(orient="records")
                output[code] = {
                    "count": len(df),
                    "latest_rows": rows,
                }
            else:
                output[code] = {"count": 0, "latest_rows": []}
        return json.dumps(output, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def handle_snapshot(codes: list) -> str:
    """处理快照查询。"""
    xq = _get_connector()
    try:
        result = xq.get_snapshot(codes)
        output = {}
        for code, data in result.items():
            if data is not None:
                if hasattr(data, "to_dict"):
                    output[code] = data.to_dict()
                elif hasattr(data, "iloc"):
                    output[code] = data.iloc[-1].to_dict() if len(data) > 0 else {}
                else:
                    output[code] = str(data)
            else:
                output[code] = None
        return json.dumps(output, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def handle_income(codes: list) -> str:
    """处理利润表查询。"""
    xq = _get_connector()
    try:
        result = xq.get_income(codes)
        output = {}
        for code, df in result.items():
            if df is not None and len(df) > 0:
                output[code] = {
                    "count": len(df),
                    "latest": df.iloc[-1].to_dict() if len(df) > 0 else {},
                }
            else:
                output[code] = {"count": 0}
        return json.dumps(output, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def handle_balance(codes: list) -> str:
    """处理资产负债表查询。"""
    xq = _get_connector()
    try:
        result = xq.get_balance(codes)
        output = {}
        for code, df in result.items():
            if df is not None and len(df) > 0:
                output[code] = {
                    "count": len(df),
                    "latest": df.iloc[-1].to_dict() if len(df) > 0 else {},
                }
            else:
                output[code] = {"count": 0}
        return json.dumps(output, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def handle_search_stocks(keyword: str, security_type: str = "all") -> str:
    """处理代码搜索。"""
    xq = _get_connector()
    results = []
    if security_type in ("stock", "all"):
        stocks = xq.get_stock_list()
        results.extend([c for c in stocks if keyword in c])
    if security_type in ("etf", "all"):
        etfs = xq.get_etf_list()
        results.extend([c for c in etfs if keyword in c])
    return json.dumps(
        {"keyword": keyword, "type": security_type, "matches": results[:30], "total": len(results)},
        ensure_ascii=False,
    )


def handle_diagnostics() -> str:
    """处理完整诊断。"""
    xq = _get_connector()
    return json.dumps(xq.diagnostics(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# MCP Server 主循环
# ---------------------------------------------------------------------------

TOOL_HANDLERS = {
    "xingyao_health": lambda args: handle_health(),
    "xingyao_calendar": lambda args: handle_calendar(args.get("count", 20)),
    "xingyao_kline": lambda args: handle_kline(
        args["codes"], args["begin_date"], args["end_date"], args.get("period", "day")
    ),
    "xingyao_snapshot": lambda args: handle_snapshot(args["codes"]),
    "xingyao_income": lambda args: handle_income(args["codes"]),
    "xingyao_balance": lambda args: handle_balance(args["codes"]),
    "xingyao_search_stocks": lambda args: handle_search_stocks(
        args["keyword"], args.get("security_type", "all")
    ),
    "xingyao_diagnostics": lambda args: handle_diagnostics(),
}


async def main():
    """启动 MCP Server。"""
    server = Server("xingyao-amazingdata")

    @server.list_tools()
    async def list_tools():
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            result = handler(arguments)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
