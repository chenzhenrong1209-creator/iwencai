import os
import re
import json
import traceback
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="pywencai 问财测试台 v2",
    page_icon="🧪",
    layout="wide",
)

QUERY_TYPES = {
    "A股/股票 stock": "stock",
    "指数 zhishu": "zhishu",
    "基金 fund": "fund",
    "港股 hkstock": "hkstock",
    "美股 usstock": "usstock",
    "可转债 conbond": "conbond",
    "期货 futures": "futures",
    "外汇 foreign_exchange": "foreign_exchange",
}


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value).strip()
    except Exception:
        pass
    return default


def get_secret_cookie() -> str:
    cookie = get_secret("WENCAI_COOKIE", "")
    try:
        section = st.secrets.get("wencai", {})
        if isinstance(section, dict):
            cookie = str(section.get("cookie") or cookie).strip()
    except Exception:
        pass
    return cookie


def mask_text(text: str, head: int = 16, tail: int = 10) -> str:
    if not text:
        return "未配置"
    if len(text) <= head + tail + 5:
        return text[:8] + "..."
    return text[:head] + "..." + text[-tail:]


def extract_cookie_from_curl_or_headers(raw: str) -> str:
    """支持粘贴 Copy as cURL、完整 request headers、或只有 Cookie 值。"""
    if not raw:
        return ""

    text = raw.strip()

    # 1. cURL: -H 'Cookie: xxx' 或 -H "Cookie: xxx"
    patterns = [
        r"-H\s+'Cookie:\s*([^']+)'",
        r'-H\s+"Cookie:\s*([^"]+)"',
        r"--header\s+'Cookie:\s*([^']+)'",
        r'--header\s+"Cookie:\s*([^"]+)"',
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.I | re.S)
        if m:
            return m.group(1).strip()

    # 2. Request Headers: Cookie: xxx
    m = re.search(r"(?im)^cookie:\s*(.+)$", text)
    if m:
        return m.group(1).strip()

    # 3. 如果本身就是 Cookie 值
    if "=" in text and ";" in text and "curl " not in text.lower():
        return text.replace("\n", " ").strip()

    return ""


def safe_import_pywencai():
    try:
        import pywencai
        return pywencai, None
    except Exception as exc:
        return None, repr(exc)


def normalize_result(res: Any):
    if res is None:
        return {"kind": "none", "frames": [], "raw": None}

    if isinstance(res, pd.DataFrame):
        return {"kind": "dataframe", "frames": [res], "raw": None}

    frames = []

    def walk(x: Any):
        if isinstance(x, pd.DataFrame):
            frames.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            if x and all(isinstance(i, dict) for i in x):
                try:
                    frames.append(pd.DataFrame(x))
                except Exception:
                    pass
            for i in x:
                walk(i)

    walk(res)
    return {"kind": type(res).__name__, "frames": frames, "raw": res}


def render_result(res: Any):
    normalized = normalize_result(res)
    st.success(f"查询完成，返回类型：{normalized['kind']}")

    if normalized["frames"]:
        for i, df in enumerate(normalized["frames"], start=1):
            st.markdown(f"#### 表格 {i}：{df.shape[0]} 行 × {df.shape[1]} 列")
            st.dataframe(df.head(200), width="stretch")
    else:
        st.warning("没有提取到 DataFrame，下面展示原始返回。")
        try:
            if isinstance(normalized["raw"], (dict, list)):
                st.json(normalized["raw"])
            else:
                st.code(str(normalized["raw"])[:10000], language="text")
        except Exception:
            st.code(repr(normalized["raw"])[:10000], language="text")


def cookie_quality_check(cookie: str) -> List[str]:
    issues = []
    if not cookie:
        return ["没有 Cookie。"]
    if "Cookie:" in cookie:
        issues.append("Cookie 里还包含了 `Cookie:` 字段名，建议只保留后面的值。")
    if "\n" in cookie:
        issues.append("Cookie 中有换行，建议清理成一整行。")
    if len(cookie) < 80:
        issues.append("Cookie 看起来太短，可能没有复制完整。")
    important = ["other_uid", "u_dpass", "u_did", "user"]
    found = [k for k in important if k in cookie]
    if len(found) < 2:
        issues.append("Cookie 中没有看到常见登录字段，可能复制的不是问财查询请求的 Cookie。")
    return issues


st.title("🧪 pywencai 问财测试台 v2")
st.caption("v2 支持直接粘贴浏览器 `Copy as cURL`，自动提取 Cookie，减少手动复制错误。")

secret_cookie = get_secret_cookie()

with st.sidebar:
    st.header("Secrets 检查")
    st.write("WENCAI_COOKIE：", mask_text(secret_cookie))
    st.markdown("---")
    st.info(
        "可选 Secrets：\n\n"
        'WENCAI_COOKIE = "完整 Cookie"\n\n'
        "也可以不填 Secrets，直接在页面粘贴 Copy as cURL 临时测试。"
    )

pywencai, import_error = safe_import_pywencai()
if import_error:
    st.error("pywencai 导入失败。请检查 requirements.txt。")
    st.code(import_error, language="text")
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["一键 cURL 测试", "Secrets Cookie 测试", "批量模板", "获取说明"])

with tab1:
    st.subheader("一键 cURL 测试")
    st.write("在问财网页 Network 里选中真正的查询请求，右键 `Copy → Copy as cURL`，整段粘到下面。系统会自动提取 Cookie。")

    raw_curl = st.text_area("粘贴 Copy as cURL 或完整 Request Headers", height=220)
    extracted_cookie = extract_cookie_from_curl_or_headers(raw_curl)

    if extracted_cookie:
        st.success("已从内容中提取到 Cookie。")
        st.write("Cookie 预览：", mask_text(extracted_cookie))
        issues = cookie_quality_check(extracted_cookie)
        if issues:
            st.warning("Cookie 检查提示：\n\n" + "\n".join([f"- {i}" for i in issues]))
    else:
        st.info("尚未提取到 Cookie。请粘贴 Copy as cURL，或完整 Request Headers。")

    query = st.text_area(
        "查询语句",
        value="今日A股行业板块资金流入排名，显示板块名称、涨跌幅、主力净流入、成交额、领涨股",
        height=90,
        key="curl_query",
    )
    query_type = QUERY_TYPES[st.selectbox("query_type", list(QUERY_TYPES.keys()), index=0, key="curl_qt")]
    perpage = st.number_input("perpage", min_value=1, max_value=100, value=30, key="curl_perpage")

    if st.button("🚀 使用提取到的 Cookie 查询", type="primary"):
        if not extracted_cookie:
            st.error("没有提取到 Cookie。")
        else:
            try:
                with st.spinner("正在请求问财..."):
                    res = pywencai.get(
                        query=query,
                        query_type=query_type,
                        cookie=extracted_cookie,
                        perpage=int(perpage),
                        retry=3,
                        loop=False,
                        no_detail=False,
                    )
                render_result(res)
            except Exception:
                st.error("查询失败")
                st.code(traceback.format_exc(), language="text")

with tab2:
    st.subheader("Secrets Cookie 测试")
    cookie = secret_cookie
    st.write("Cookie 预览：", mask_text(cookie))
    if cookie:
        issues = cookie_quality_check(cookie)
        if issues:
            st.warning("Cookie 检查提示：\n\n" + "\n".join([f"- {i}" for i in issues]))
    else:
        st.error("Secrets 中没有 WENCAI_COOKIE。")

    query = st.text_area(
        "问财查询语句",
        value="江海股份最新价、涨跌幅、总市值、换手率、市盈率、市净率",
        height=90,
        key="secret_query",
    )
    query_type = QUERY_TYPES[st.selectbox("query_type", list(QUERY_TYPES.keys()), index=0, key="secret_qt")]
    perpage = st.number_input("perpage", min_value=1, max_value=100, value=30, key="secret_perpage")

    if st.button("🚀 使用 Secrets Cookie 查询", type="primary"):
        if not cookie:
            st.error("没有 Cookie。")
        else:
            try:
                with st.spinner("正在请求问财..."):
                    res = pywencai.get(
                        query=query,
                        query_type=query_type,
                        cookie=cookie,
                        perpage=int(perpage),
                        retry=3,
                        loop=False,
                        no_detail=False,
                    )
                render_result(res)
            except Exception:
                st.error("查询失败")
                st.code(traceback.format_exc(), language="text")

with tab3:
    st.subheader("批量模板测试")
    cookie_source = st.radio("Cookie 来源", ["cURL 提取", "Secrets"], horizontal=True)
    test_cookie = extracted_cookie if cookie_source == "cURL 提取" else secret_cookie

    templates = [
        ("行业板块资金", "今日A股行业板块资金流入排名，显示板块名称、涨跌幅、主力净流入、成交额、领涨股", "stock"),
        ("行业板块涨幅", "今日A股行业板块涨幅排名", "stock"),
        ("个股行情", "江海股份最新价、涨跌幅、总市值、换手率、市盈率、市净率", "stock"),
        ("公告", "江海股份最新公告", "stock"),
        ("研报", "江海股份最新研报和机构观点", "stock"),
        ("指数", "上证指数、深证成指、创业板指、沪深300今日行情", "zhishu"),
    ]

    if st.button("🧭 开始批量模板测试"):
        if not test_cookie:
            st.error("没有可用 Cookie。")
        else:
            records = []
            for name, q, qt in templates:
                try:
                    res = pywencai.get(
                        query=q,
                        query_type=qt,
                        cookie=test_cookie,
                        perpage=20,
                        retry=2,
                        loop=False,
                        no_detail=False,
                    )
                    normalized = normalize_result(res)
                    rows = normalized["frames"][0].shape[0] if normalized["frames"] else 0
                    cols = normalized["frames"][0].shape[1] if normalized["frames"] else 0
                    records.append({
                        "模板": name,
                        "成功": True,
                        "返回类型": normalized["kind"],
                        "首表行数": rows,
                        "首表列数": cols,
                        "查询语句": q,
                        "错误": "",
                    })
                except Exception as exc:
                    records.append({
                        "模板": name,
                        "成功": False,
                        "返回类型": "",
                        "首表行数": 0,
                        "首表列数": 0,
                        "查询语句": q,
                        "错误": repr(exc),
                    })
            st.dataframe(pd.DataFrame(records), width="stretch")

with tab4:
    st.subheader("最简单获取 Cookie 的办法")
    st.markdown(
        """
### 推荐方式：直接复制 cURL，不用自己找 Cookie

1. 电脑打开问财网页并登录。
2. 搜索一句真实问题，比如：`今日A股行业板块资金流入排名`。
3. 按 F12 打开开发者工具。
4. 点 Network / 网络。
5. 重新搜索一次。
6. 在请求列表里找一个真正查询数据的请求。
7. 右键这个请求。
8. 选择：
   ```text
   Copy → Copy as cURL
   ```
   中文一般是：
   ```text
   复制 → 复制为 cURL
   ```
9. 回到本测试台，粘到“一键 cURL 测试”里。
10. 系统会自动从 cURL 里提取 Cookie。

### 注意

- 不要把 cURL 或 Cookie 发给别人。
- 不要上传到 GitHub。
- Cookie 失效后，重新复制一次 cURL 即可。
        """
    )
