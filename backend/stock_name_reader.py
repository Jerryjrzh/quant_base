"""
从通达信本地 .tnf 文件读取股票名称。
.tnf 文件格式：文件头(50字节) + 记录(360字节/条)
每条记录：代码(6字节 ASCII) + 填充(25字节) + 名称(8字节 GBK) + 其他
"""
import os
import threading
from typing import Dict, List

try:
    from pypinyin import lazy_pinyin, Style
    _pinyin_available = True
except ImportError:
    _pinyin_available = False

TNF_FILES = {
    'sh': os.path.expanduser('~/.local/share/tdxcfv/drive_c/tc/T0002/hq_cache/shs.tnf'),
    'sz': os.path.expanduser('~/.local/share/tdxcfv/drive_c/tc/T0002/hq_cache/szs.tnf'),
    'bj': os.path.expanduser('~/.local/share/tdxcfv/drive_c/tc/T0002/hq_cache/bjs.tnf'),
}

HEADER_SIZE = 50
RECORD_SIZE = 360
NAME_OFFSET = 31
NAME_LEN = 8

_cache: Dict[str, str] = {}
_pinyin_cache: Dict[str, str] = {}       # 首字母，如 "gzmt"
_full_pinyin_cache: Dict[str, str] = {}  # 全拼，如 "guizhoumoutai"
_cache_lock = threading.Lock()
_cache_ready = threading.Event()         # 缓存构建完成标志


def _read_tnf(market: str) -> Dict[str, str]:
    path = TNF_FILES.get(market)
    if not path or not os.path.isfile(path):
        return {}
    result = {}
    try:
        with open(path, 'rb') as f:
            data = f.read()
        pos = HEADER_SIZE
        while pos + RECORD_SIZE <= len(data):
            code_bytes = data[pos:pos + 6]
            code = code_bytes.rstrip(b'\x00').decode('ascii', errors='ignore')
            if len(code) == 6 and code.isdigit():
                name_bytes = data[pos + NAME_OFFSET: pos + NAME_OFFSET + NAME_LEN]
                name = name_bytes.rstrip(b'\x00').decode('gbk', errors='ignore').strip()
                if name:
                    result[code] = name
            pos += RECORD_SIZE
    except Exception:
        pass
    return result


def _build_cache():
    """在后台线程中构建完整缓存（含拼音），只执行一次。"""
    with _cache_lock:
        if _cache:          # 双重检查，避免重复构建
            _cache_ready.set()
            return
        tmp_cache: Dict[str, str] = {}
        tmp_pinyin: Dict[str, str] = {}
        tmp_full: Dict[str, str] = {}

        for market in ('sh', 'sz', 'bj'):
            for code, name in _read_tnf(market).items():
                full_code = f'{market}{code}'
                tmp_cache[full_code] = name
                if _pinyin_available and name:
                    try:
                        tmp_pinyin[full_code] = ''.join(
                            lazy_pinyin(name, style=Style.FIRST_LETTER)
                        ).lower()
                        tmp_full[full_code] = ''.join(
                            lazy_pinyin(name)
                        ).lower()
                    except Exception:
                        tmp_pinyin[full_code] = ''
                        tmp_full[full_code] = ''

        _cache.update(tmp_cache)
        _pinyin_cache.update(tmp_pinyin)
        _full_pinyin_cache.update(tmp_full)
        _cache_ready.set()
        print(f"✅ 股票名称缓存构建完成，共 {len(_cache)} 条")


def _ensure_cache():
    """确保缓存已构建，若未完成则等待（最多 30s）。"""
    if _cache_ready.is_set():
        return
    # 触发构建（若尚未启动）
    if not _cache and not _cache_ready.is_set():
        t = threading.Thread(target=_build_cache, daemon=True, name='stock-name-cache')
        t.start()
    _cache_ready.wait(timeout=30)


# 模块导入时立即在后台开始构建，不阻塞启动
threading.Thread(target=_build_cache, daemon=True, name='stock-name-cache-init').start()


# ── 公开 API ──────────────────────────────────────────────────────────────────

def get_stock_name(stock_code: str) -> str:
    _ensure_cache()
    if stock_code in _cache:
        return _cache[stock_code]
    pure = stock_code.replace('sh', '').replace('sz', '').replace('bj', '')
    for prefix in ('sh', 'sz', 'bj'):
        key = f'{prefix}{pure}'
        if key in _cache:
            return _cache[key]
    return stock_code


def get_stock_names(stock_codes: list) -> Dict[str, str]:
    _ensure_cache()
    return {code: get_stock_name(code) for code in stock_codes}


def reload_cache():
    _cache.clear()
    _pinyin_cache.clear()
    _full_pinyin_cache.clear()
    _cache_ready.clear()
    _build_cache()


def search_stocks(query: str, limit: int = 20) -> List[Dict[str, str]]:
    """
    按股票代码、名称、拼音首字母或全拼搜索。
    缓存未就绪时等待，不返回 500。
    """
    _ensure_cache()
    if not query:
        return []

    q = query.strip().lower()
    results = []

    for full_code, name in _cache.items():
        pure_code = full_code[2:]
        matched = False
        priority = 99

        if pure_code.startswith(q) or full_code.lower().startswith(q):
            matched, priority = True, 0
        elif name and q in name:
            matched, priority = True, 1
        elif _pinyin_available:
            initials = _pinyin_cache.get(full_code, '')
            full_py  = _full_pinyin_cache.get(full_code, '')
            if initials and initials.startswith(q):
                matched, priority = True, 2
            elif full_py and full_py.startswith(q):
                matched, priority = True, 3

        if matched:
            results.append({
                'code':   full_code,
                'name':   name,
                'pinyin': _pinyin_cache.get(full_code, ''),
                '_p':     priority,
            })

    results.sort(key=lambda x: (x['_p'], x['code']))
    for r in results:
        del r['_p']

    return results[:limit]
