#!/usr/bin/env python3
"""
梅森资料库索引脚本
扫描 D:/梅森/ 目录，建立文件名 → 题材/方向的映射索引。
索引保存在 data/mason_library/index.json
"""
import json, os, re
from pathlib import Path
from datetime import datetime

MASON_DIR = Path("D:/梅森")
OUTPUT = Path("data/mason_library/index.json")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# 从文件名推断题材方向
TOPIC_KEYWORDS = {
    "算力": ["算力", "CPO", "光互联", "光模块", "数据中心", "电源"],
    "AI应用": ["AI应用", "机器人", "人形", "智能"],
    "半导体": ["芯片", "半导体", "中芯", "集成电路"],
    "通信": ["通信", "光", "CPO", "亨通", "光纤"],
    "周期": ["有色", "稀土", "钨", "能源", "化工", "周期"],
    "策略": ["策略", "展望", "总结", "复盘", "盘前", "监管", "春节", "节后"],
    "宏观": ["宏观", "全球经济", "货币", "降息"],
    "PCB": ["PCB", "印刷电路"],
    "电力": ["电力", "电网", "电源"],
}

def detect_topics(filename: str) -> list:
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in filename for kw in keywords):
            topics.append(topic)
    return topics if topics else ["未分类"]

def detect_date(filename: str) -> str:
    m = re.search(r"(\d{4})[.\-]?(\d{1,2})[.\-]?(\d{1,2})?", filename)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2) if m.group(3) else '01'}"
    m2 = re.search(r"(\d{4})(\d{2})", filename)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}-01"
    return ""

def build_index():
    if not MASON_DIR.exists():
        print(f"[WARN] 梅森资料目录不存在: {MASON_DIR}")
        return {"files": [], "updated_at": datetime.now().isoformat()}

    files = []
    for f in sorted(MASON_DIR.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        topics = detect_topics(f.name)
        files.append({
            "filename": f.name,
            "path": str(f),
            "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
            "topics": topics,
            "date_hint": detect_date(f.name),
            "summary": "",  # 人工填写
        })

    result = {
        "source_dir": str(MASON_DIR),
        "file_count": len(files),
        "topics": sorted(set(t for f in files for t in f["topics"])),
        "files": files,
        "updated_at": datetime.now().isoformat(),
        "note": "topics 由文件名自动推断；summary 需人工补充；PDF 正文内容未提取",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 索引已更新: {OUTPUT}  ({len(files)} 个文件)")
    return result

if __name__ == "__main__":
    build_index()
