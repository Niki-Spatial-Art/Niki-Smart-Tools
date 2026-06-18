import argparse
import csv
import datetime as dt
import re
from pathlib import Path


HIGH_RISK_FUNCS = {
    "BACKSET": "未来/回写风险",
    "ZIG": "转向函数，易重绘",
    "PEAK": "波峰函数，易重绘",
    "PEAKBARS": "波峰定位，易重绘",
    "TROUGH": "波谷函数，易重绘",
    "TROUGHBARS": "波谷定位，易重绘",
    "REFX": "向后引用，未来函数",
    "REFXV": "向后引用，未来函数",
    "DRAWLINE": "画线函数，条件确认后可能重绘",
    "FILTERX": "向后过滤，未来/重绘风险",
}

L2_FUNCS = {
    "L2_AMO",
    "L2_VOL",
    "L2_BS",
    "LARGEINTRDVOL",
    "ACTINVOL",
    "ACTOUTVOL",
    "DDX",
    "DDY",
    "DDZ",
}

DRAW_FUNCS = {
    "DRAWTEXT",
    "DRAWICON",
    "DRAWKLINE",
    "STICKLINE",
    "POLYLINE",
    "PARTLINE",
    "DRAWBAND",
    "DRAWGBK",
}

CORE_SIGNAL_FUNCS = {
    "CROSS",
    "COUNT",
    "EVERY",
    "EXIST",
    "BARSLAST",
    "HHV",
    "LLV",
    "MA",
    "EMA",
    "SMA",
    "MACD",
    "KDJ",
    "RSI",
    "BOLL",
    "VOL",
}

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "utf-16", "utf-16le")


def read_text(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for enc in ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("latin1", errors="ignore"), "latin1"


def normalize_formula_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return (
        text.replace("：", ":")
        .replace("；", ";")
        .replace("，", ",")
        .replace("（", "(")
        .replace("）", ")")
    )


def looks_like_formula(text: str) -> bool:
    upper = text.upper()
    funcs = CORE_SIGNAL_FUNCS | set(HIGH_RISK_FUNCS) | DRAW_FUNCS
    return (
        (":=" in text or re.search(r"^[A-Z0-9_\u4e00-\u9fff]+:", text, re.M))
        and any(func + "(" in upper for func in funcs)
    )


def split_formula_blocks(text: str, fallback_name: str) -> list[dict]:
    text = normalize_formula_text(text)
    lines = [line.rstrip() for line in text.split("\n")]
    blocks: list[dict] = []
    name_patterns = [
        re.compile(r"^\s*(?:公式名称|指标名称|名称|公式名)\s*[:=]\s*(.+?)\s*$", re.I),
        re.compile(r"^\s*#{2,}\s*(.+?)\s*$"),
    ]

    current_name = fallback_name
    current: list[str] = []
    saw_named_block = False

    for line in lines:
        name = None
        for pat in name_patterns:
            match = pat.match(line)
            if match:
                name = match.group(1).strip()
                break
        if name:
            if current:
                blocks.append({"name": current_name, "code": "\n".join(current).strip()})
                current = []
            current_name = re.sub(r"[;{}]+$", "", name).strip() or fallback_name
            saw_named_block = True
            continue
        current.append(line)

    if current:
        blocks.append({"name": current_name, "code": "\n".join(current).strip()})

    if saw_named_block:
        return [b for b in blocks if looks_like_formula(b["code"])]
    if looks_like_formula(text):
        return [{"name": fallback_name, "code": text.strip()}]
    return []


def find_funcs(code: str, funcs: set[str]) -> list[str]:
    upper = code.upper()
    found = []
    for func in sorted(funcs):
        if re.search(rf"\b{re.escape(func)}\s*\(", upper):
            found.append(func)
    return found


def count_outputs(code: str) -> int:
    outputs = 0
    for line in code.splitlines():
        clean = re.sub(r"\{.*?\}", "", line).strip()
        if not clean or ":=" in clean:
            continue
        if re.match(r"^[A-Z0-9_\u4e00-\u9fff]+\s*:", clean):
            outputs += 1
    return outputs


def infer_logic(name: str, code: str, core: list[str], draw: list[str]) -> str:
    text = name + "\n" + code
    tags = []
    if re.search(r"资金|主力|流入|DDX|DDY|L2_", text, re.I):
        tags.append("资金/主力")
    if re.search(r"MACD|DIF|DEA", text, re.I):
        tags.append("MACD趋势")
    if re.search(r"KDJ|RSV|J[:=]|SMA", text, re.I):
        tags.append("KDJ/摆动")
    if re.search(r"MA\(|EMA\(|均线|上穿|金叉|CROSS", text, re.I):
        tags.append("均线/交叉")
    if re.search(r"VOL|量|放量|换手|成交", text, re.I):
        tags.append("量价")
    if re.search(r"底|低位|超跌|反弹", text, re.I):
        tags.append("低位反弹")
    if re.search(r"突破|平台|主升|第三浪|起爆", text, re.I):
        tags.append("突破/主升")
    if draw and not tags:
        tags.append("视觉画线")
    if not tags and core:
        tags.append("技术指标")
    return "/".join(dict.fromkeys(tags)) or "待人工识别"


def classify(block: dict, source: Path, encoding: str) -> dict:
    code = block["code"]
    upper = code.upper()
    risky = find_funcs(code, set(HIGH_RISK_FUNCS))
    l2 = find_funcs(code, L2_FUNCS)
    draw = find_funcs(code, DRAW_FUNCS)
    core = find_funcs(code, CORE_SIGNAL_FUNCS)
    outputs = count_outputs(code)

    combined = block["name"] + code
    has_buy_words = bool(re.search(r"买|进|底|启动|突破|起爆|主升|反转|金叉|上穿|尾盘|XG|选股", combined, re.I))
    has_sell_words = bool(re.search(r"卖|逃|顶|风险|减仓|死叉|下穿", combined, re.I))
    has_condition = bool(re.search(r"\bCROSS\s*\(|\bCOUNT\s*\(|\bEVERY\s*\(|\bEXIST\s*\(|\bBARSLAST\s*\(", upper))
    can_convert = has_condition and not risky and outputs <= 8

    score = 50
    score += 15 if has_condition else 0
    score += 12 if has_buy_words else 0
    score += 6 if any(f in core for f in ("MA", "EMA", "MACD", "KDJ", "RSI", "BOLL")) else 0
    score -= 35 if risky else 0
    score -= 18 if l2 else 0
    score -= 10 if outputs > 10 else 0
    score -= 8 if draw and not has_condition else 0
    score -= 5 if has_sell_words and not has_buy_words else 0

    if risky:
        grade = "D-淘汰/仅学习"
        action = "含高风险/重绘函数，先不用于实盘选股"
    elif l2:
        grade = "C-条件受限"
        action = "依赖L2/资金函数，确认权限和字段后再评估"
    elif score >= 75 and can_convert:
        grade = "A-优先研究"
        action = "优先转成XG选股公式，并做样本验证"
    elif score >= 62:
        grade = "B-可学习/可改造"
        action = "保留源码，提炼逻辑后再决定是否改选股"
    else:
        grade = "C-低优先级"
        action = "可暂存，先不占用盘中注意力"

    risks = "; ".join(f"{f}:{HIGH_RISK_FUNCS[f]}" for f in risky)
    if l2:
        risks = (risks + "; " if risks else "") + "L2依赖:" + ",".join(l2)

    return {
        "formula_name": block["name"],
        "grade": grade,
        "score": score,
        "logic": infer_logic(block["name"], code, core, draw),
        "can_convert_to_xg": "Y" if can_convert else "N",
        "risk_flags": risks,
        "core_functions": ",".join(core),
        "draw_functions": ",".join(draw),
        "output_lines": outputs,
        "action": action,
        "source_file": str(source),
        "encoding": encoding,
        "chars": len(code),
    }


def write_outputs(rows: list[dict], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "tdx_formula_screen.csv"
    md_path = out_dir / "tdx_formula_screen.md"
    fields = [
        "formula_name",
        "grade",
        "score",
        "logic",
        "can_convert_to_xg",
        "risk_flags",
        "core_functions",
        "draw_functions",
        "output_lines",
        "action",
        "source_file",
        "encoding",
        "chars",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    counts = {}
    for row in rows:
        counts[row["grade"]] = counts.get(row["grade"], 0) + 1

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# 通达信公式第一轮筛选报告\n\n")
        f.write(f"生成时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## 分档统计\n\n")
        for grade, count in sorted(counts.items()):
            f.write(f"- {grade}: {count}\n")
        f.write("\n## 使用规则\n\n")
        f.write("- A档：优先研究，下一步转成 `XG:` 条件选股并回看样本。\n")
        f.write("- B档：适合学习/改造，先提炼逻辑，不急着实盘。\n")
        f.write("- C档：低优先级或依赖权限，暂不占用盘中注意力。\n")
        f.write("- D档：含未来/重绘风险，先不用于实盘选股。\n\n")
        f.write("## 明细\n\n")
        f.write("|公式|分档|分数|逻辑|可转选股|风险|建议|\n")
        f.write("|---|---:|---:|---|---:|---|---|\n")
        for row in rows:
            risk = row["risk_flags"].replace("|", "/") or "-"
            name = row["formula_name"].replace("|", "/")
            f.write(
                f"|{name}|{row['grade']}|{row['score']}|{row['logic']}|"
                f"{row['can_convert_to_xg']}|{risk}|{row['action']}|\n"
            )
    return csv_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen exported TongDaXin formula files.")
    parser.add_argument("--input", required=True, help="TDX exported formula file or folder")
    parser.add_argument("--output", required=True, help="Output folder")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.output)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    files = [input_path] if input_path.is_file() else [
        p for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".tn6", ".tne", ".csv", ".md"}
    ]

    rows = []
    unreadable = []
    for path in files:
        try:
            text, enc = read_text(path)
            for block in split_formula_blocks(text, path.stem):
                rows.append(classify(block, path, enc))
        except Exception as exc:
            unreadable.append({"file": str(path), "error": str(exc)})

    rows.sort(key=lambda r: (r["grade"], -int(r["score"]), r["formula_name"]))
    csv_path, md_path = write_outputs(rows, out_dir)

    if unreadable:
        bad_path = out_dir / "tdx_formula_unreadable.csv"
        with bad_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "error"])
            writer.writeheader()
            writer.writerows(unreadable)

    print(f"scanned_files={len(files)}")
    print(f"formula_blocks={len(rows)}")
    print(f"csv={csv_path}")
    print(f"md={md_path}")
    if unreadable:
        print(f"unreadable={len(unreadable)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
