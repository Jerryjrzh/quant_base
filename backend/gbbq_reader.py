"""
gbbq 除权除息数据解析模块
解析通达信本地 gbbq 文件，提取送股/配股/分红事件，计算复权因子。

gbbq category=1 字段说明（单位均为每10股）：
  hongli_panqianliutong  : 每10股红利（元），现金分红
  peigujia_qianzongguben : 配股价（元），单价，不需要除以10
  songgu_qianzongguben   : 每10股送股数（含转增）
  peigu_houzongguben     : 每10股配股数

复权因子（标准通达信算法）：
  每股红利 = hongli / 10
  每股送股 = songgu / 10
  每股配股 = peigu / 10
  除权价 = (前收盘 - 每股红利 + 配股价 * 每股配股) / (1 + 每股送股 + 每股配股)
  factor = 除权价 / 前收盘
"""

import os
import sys
import struct
import pandas as pd
from ctypes import c_uint32
from typing import Optional

DEFAULT_GBBQ_PATH = os.path.expanduser(
    "~/.local/share/tdxcfv/drive_c/tc/T0002/hq_cache/gbbq"
)

# 模块级全局缓存：整个 gbbq 文件只解密一次
_gbbq_cache = None
_gbbq_cache_path = None
# 按 code 建立的二级索引，O(1) 查找
_gbbq_index = {}

def _load_bin_keys():
    """从 pytdx 动态获取密钥，避免硬编码长字符串"""
    try:
        _pytdx_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'tdx', 'pytdx'
        )
        if os.path.isdir(_pytdx_path):
            sys.path.insert(0, os.path.abspath(_pytdx_path))
        from pytdx.reader.gbbq_reader import GbbqReader
        return bytes.fromhex(GbbqReader().hexdump_keys.replace(' ', ''))
    except Exception:
        return None


def _decrypt_gbbq(content: bytes, bin_keys: bytes):
    """解密 gbbq 文件内容，返回记录列表"""
    result = []
    pos = 0
    (count,) = struct.unpack("<I", content[pos:pos + 4])
    pos += 4
    data_offset = pos

    for _ in range(count):
        clear_data = bytearray()
        for _ in range(3):
            (eax,) = struct.unpack("<I", bin_keys[0x44:0x44 + 4])
            (ebx,) = struct.unpack("<I", content[data_offset:data_offset + 4])
            num = c_uint32(eax ^ ebx).value
            (numold,) = struct.unpack("<I", content[data_offset + 4:data_offset + 8])
            for j in reversed(range(4, 0x40 + 4, 4)):
                ebx = (num & 0xFF0000) >> 16
                (eax,) = struct.unpack("<I", bin_keys[ebx * 4 + 0x448:ebx * 4 + 0x448 + 4])
                ebx = num >> 24
                (eax_add,) = struct.unpack("<I", bin_keys[ebx * 4 + 0x48:ebx * 4 + 0x48 + 4])
                eax = c_uint32(eax + eax_add).value
                ebx = (num & 0xFF00) >> 8
                (eax_xor,) = struct.unpack("<I", bin_keys[ebx * 4 + 0x848:ebx * 4 + 0x848 + 4])
                eax = c_uint32(eax ^ eax_xor).value
                ebx = num & 0xFF
                (eax_add,) = struct.unpack("<I", bin_keys[ebx * 4 + 0xC48:ebx * 4 + 0xC48 + 4])
                eax = c_uint32(eax + eax_add).value
                (eax_xor,) = struct.unpack("<I", bin_keys[j:j + 4])
                eax = c_uint32(eax ^ eax_xor).value
                ebx = num
                num = c_uint32(numold ^ eax).value
                numold = ebx
            (numold_op,) = struct.unpack("<I", bin_keys[0:4])
            numold = c_uint32(numold ^ numold_op).value
            clear_data.extend(struct.pack("<II", numold, num))
            data_offset += 8

        clear_data.extend(content[data_offset:data_offset + 5])
        (v1, v2, v3, v4, v5, v6, v7, v8) = struct.unpack("<B7sIBffff", clear_data)
        result.append((
            v1,
            v2.rstrip(b"\x00").decode("utf-8", errors="ignore"),
            v3, v4, v5, v6, v7, v8
        ))
        data_offset += 5

    return result


def read_gbbq(gbbq_path: str = None) -> pd.DataFrame:
    """读取 gbbq 文件，返回完整除权除息记录 DataFrame。结果全局缓存，只解密一次。"""
    global _gbbq_cache, _gbbq_cache_path, _gbbq_index
    path = gbbq_path or DEFAULT_GBBQ_PATH

    if _gbbq_cache is not None and _gbbq_cache_path == path:
        return _gbbq_cache

    if not os.path.isfile(path):
        raise FileNotFoundError(f"gbbq 文件不存在: {path}")

    bin_keys = _load_bin_keys()
    if bin_keys is None:
        raise RuntimeError("无法加载 gbbq 解密密钥，请确认 tdx/pytdx 路径正确")

    with open(path, 'rb') as f:
        content = f.read()

    records = _decrypt_gbbq(content, bin_keys)
    df = pd.DataFrame(records, columns=[
        'market', 'code', 'datetime', 'category',
        'hongli_panqianliutong', 'peigujia_qianzongguben',
        'songgu_qianzongguben', 'peigu_houzongguben'
    ])
    df['date'] = pd.to_datetime(df['datetime'].astype(str), format='%Y%m%d', errors='coerce')

    _gbbq_cache = df
    _gbbq_cache_path = path
    _gbbq_index = {code: grp for code, grp in df.groupby('code')}
    return df


def clear_gbbq_cache():
    """清除全局 gbbq 缓存（文件更新后调用）"""
    global _gbbq_cache, _gbbq_cache_path, _gbbq_index
    _gbbq_cache = None
    _gbbq_cache_path = None
    _gbbq_index = {}


def get_xdxr_for_stock(code: str, gbbq_path: str = None) -> pd.DataFrame:
    """
    获取单只股票的除权除息记录（仅 category=1），按日期排序。
    返回列：date, hongli(每10股红利), songgu(每10股送股), peigu(每10股配股), peigujia(配股价单价)
    使用全局索引，O(1) 查找，无需全表过滤。
    """
    read_gbbq(gbbq_path)  # 确保缓存已加载
    clean_code = code.replace('sh', '').replace('sz', '').replace('bj', '').strip()

    if clean_code not in _gbbq_index:
        return pd.DataFrame(columns=['date', 'hongli', 'songgu', 'peigu', 'peigujia'])

    stock_df = _gbbq_index[clean_code]
    stock_df = stock_df[stock_df['category'] == 1].copy()
    stock_df = stock_df.sort_values('date').reset_index(drop=True)
    stock_df = stock_df.rename(columns={
        'hongli_panqianliutong': 'hongli',
        'peigujia_qianzongguben': 'peigujia',
        'songgu_qianzongguben': 'songgu',
        'peigu_houzongguben': 'peigu',
    })
    return stock_df[['date', 'hongli', 'songgu', 'peigu', 'peigujia']]


def calc_adjust_factors(xdxr_df: pd.DataFrame, price_series: pd.Series) -> pd.Series:
    """
    根据除权除息记录和收盘价序列，计算每个除权日的复权因子。
    gbbq 字段 hongli/songgu/peigu 单位为每10股，内部除以10换算为每股。
    peigujia 为配股单价，不需要除以10。
    """
    factors = {}
    for _, row in xdxr_df.iterrows():
        ex_date = row['date']
        prev_prices = price_series[price_series.index < ex_date]
        if prev_prices.empty:
            continue
        prev_close = float(prev_prices.iloc[-1])
        if prev_close <= 0:
            continue

        # gbbq 字段单位均为每10股，除以10换算为每股
        hongli   = float(row['hongli'])   / 10.0
        songgu   = float(row['songgu'])   / 10.0
        peigu    = float(row['peigu'])    / 10.0
        peigujia = float(row['peigujia'])          # 配股价单价，不需除以10

        divisor = 1.0 + songgu + peigu
        if divisor <= 0:
            continue

        ex_price = (prev_close - hongli + peigujia * peigu) / divisor
        factor = ex_price / prev_close
        if factor > 0:
            factors[ex_date] = factor

    return pd.Series(factors, name='factor').sort_index()
