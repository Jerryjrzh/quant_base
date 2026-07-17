"""
通达信板块文件解析模块（文本格式）

infoharbor_block.dat 是主要概念板块数据（546个板块）
格式：#板块名[,股票数,...] 后跟 市场#代码 列表
"""

import os
import re
import pandas as pd
from typing import Dict, List, Optional

DEFAULT_HQ_CACHE = os.path.expanduser(
    "~/.local/share/tdxcfv/drive_c/tc/T0002/hq_cache"
)

MARKET_PREFIX = {"0": "sz", "1": "sh", "2": "bj"}

BLOCK_FILES = {
    "concept": "infoharbor_block.dat",
    "special": "spblock.dat",
}


def _parse_text_block_file(data: bytes) -> List[dict]:
    text = data.decode("gbk", errors="ignore")
    lines = [l.strip() for l in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    blocks = []
    current_name = None
    current_codes = []

    for line in lines:
        if not line:
            continue
        if line.startswith("#"):
            if current_name is not None:
                blocks.append({"blockname": current_name, "codes": current_codes, "stock_count": len(current_codes)})
            raw_name = line[1:].split(",")[0].strip()
            current_name = raw_name.replace("GN_", "").strip()
            current_codes = []
        else:
            for part in line.split(","):
                code = _normalize_code(part.strip())
                if code:
                    current_codes.append(code)

    if current_name is not None and current_codes:
        blocks.append({"blockname": current_name, "codes": current_codes, "stock_count": len(current_codes)})
    return blocks


def _normalize_code(raw: str) -> Optional[str]:
    raw = raw.strip()
    if not raw:
        return None
    if "#" in raw:
        parts = raw.split("#", 1)
        market_id, code = parts[0].strip(), parts[1].strip()
        prefix = MARKET_PREFIX.get(market_id, "")
        if prefix and re.match(r"^\d{6}$", code):
            return f"{prefix}{code}"
        return None
    if re.match(r"^\d{7}$", raw):
        prefix = MARKET_PREFIX.get(raw[0], "")
        return f"{prefix}{raw[1:]}" if prefix else None
    if re.match(r"^\d{6}$", raw):
        return _infer_market(raw)
    return None


def _infer_market(code: str) -> str:
    if code.startswith(("60", "68", "51", "11")):
        return f"sh{code}"
    elif code.startswith(("00", "30", "15", "16")):
        return f"sz{code}"
    elif code.startswith(("43", "83", "87", "92")):
        return f"bj{code}"
    return f"sz{code}"


def read_block_file(file_path: str) -> pd.DataFrame:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"板块文件不存在: {file_path}")
    with open(file_path, "rb") as f:
        data = f.read()
    blocks = _parse_text_block_file(data)
    rows = [{"blockname": b["blockname"], "code": c} for b in blocks for c in b["codes"]]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["blockname", "code"])


def read_block_file_grouped(file_path: str) -> pd.DataFrame:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"板块文件不存在: {file_path}")
    with open(file_path, "rb") as f:
        data = f.read()
    blocks = _parse_text_block_file(data)
    return pd.DataFrame([{"blockname": b["blockname"], "stock_count": b["stock_count"]} for b in blocks])


def get_stock_blocks(stock_code: str, block_type: str = "concept", hq_cache_path: str = None) -> List[str]:
    cache_dir = hq_cache_path or DEFAULT_HQ_CACHE
    fname = BLOCK_FILES.get(block_type, block_type)
    fpath = os.path.join(cache_dir, fname)
    if not os.path.isfile(fpath):
        return []
    normalized = stock_code.lower() if len(stock_code) > 6 and stock_code[:2].isalpha() else _infer_market(stock_code)
    try:
        df = read_block_file(fpath)
        if df.empty or "code" not in df.columns:
            return []
        return df[df["code"] == normalized]["blockname"].unique().tolist()
    except Exception as e:
        print(f"[block_reader] 查询板块失败 {block_type}: {e}")
        return []


def get_stock_all_blocks(stock_code: str, hq_cache_path: str = None) -> Dict[str, List[str]]:
    result = {}
    for block_type in BLOCK_FILES:
        blocks = get_stock_blocks(stock_code, block_type, hq_cache_path)
        if blocks:
            result[block_type] = blocks
    return result


def get_block_stocks(block_name: str, block_type: str = "concept", hq_cache_path: str = None) -> List[str]:
    cache_dir = hq_cache_path or DEFAULT_HQ_CACHE
    fname = BLOCK_FILES.get(block_type, block_type)
    fpath = os.path.join(cache_dir, fname)
    if not os.path.isfile(fpath):
        return []
    try:
        df = read_block_file(fpath)
        if df.empty or "code" not in df.columns:
            return []
        return df[df["blockname"] == block_name]["code"].tolist()
    except Exception as e:
        print(f"[block_reader] 获取板块股票失败: {e}")
        return []


def list_all_blocks(block_type: str = "concept", hq_cache_path: str = None) -> pd.DataFrame:
    cache_dir = hq_cache_path or DEFAULT_HQ_CACHE
    fname = BLOCK_FILES.get(block_type, block_type)
    fpath = os.path.join(cache_dir, fname)
    if not os.path.isfile(fpath):
        return pd.DataFrame(columns=["blockname", "stock_count"])
    try:
        return read_block_file_grouped(fpath)
    except Exception as e:
        print(f"[block_reader] 列出板块失败: {e}")
        return pd.DataFrame(columns=["blockname", "stock_count"])


def get_all_block_memberships(block_type: str = "concept", hq_cache_path: str = None) -> Dict[str, List[str]]:
    cache_dir = hq_cache_path or DEFAULT_HQ_CACHE
    fname = BLOCK_FILES.get(block_type, block_type)
    fpath = os.path.join(cache_dir, fname)
    if not os.path.isfile(fpath):
        return {}
    try:
        with open(fpath, "rb") as f:
            data = f.read()
        blocks = _parse_text_block_file(data)
        return {b["blockname"]: b["codes"] for b in blocks if b["blockname"]}
    except Exception as e:
        print(f"[block_reader] 加载板块映射失败: {e}")
        return {}
