import os
import json
import traceback
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="pywencai 问财 Cookie 测试台",
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
        v = st.secrets.get(name, "")
        if v:
            return str(v).strip()
    except Exception:
        pass
    return default


def mask_cookie(cookie: str) -> str:
    if not cookie:
        return "未配置"
    if len(cookie) <= 30:
        return cookie[:8] + "..."
    return cookie[:16] + "..." + cookie[-12:]


def safe_import_pywencai():
    try:
        import pywencai
        return pywencai, None
    except Exception as e:
        return None, repr(e)


def normalize_result(res: Any):
    """把 pywencai 可能返回的 DataFrame / dict / list 转成便于展示的结构。"""
    if res is None:
        return {"kind": "none", "frames": [], "raw": None}

    if isinstance(res, pd.DataFrame):
        return {"kind": "dataframe", "frames": [res], "raw": None}

    frames = []
    raw = res

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

    return {"kind": type(res).__name__, "frames": frames, "raw": raw}


def render_raw(obj: Any):
    try:
        if isinstance(obj, (dict, list)):
            st.json(obj)
        else:
            st.code(str(obj)[:8000], language="text")
    except Exception:
        st.code(repr(obj)[:8000], language="text")


st.title("🧪 pywencai 问财 Cookie 测试台")
st.caption("用于验证 pywencai + Cookie 是否能在 Streamlit 云端返回数据。跑通后再作为低频备用接口接回量化终端。")

cookie = get_secret("WENCAI_COOKIE", "")
try:
    section = st.secrets.get("wencai", {})
    if isinstance(section, dict):
        cookie = str(section.get("cookie") or cookie).strip()
except Exception:
    pass

with st.sidebar:
    st.header("配置检查")
    st.write("Cookie：", mask_cookie(cookie))
    st.markdown("---")
    st.info(
        "Secrets 推荐：\n\n"
        'WENCAI_COOKIE = "从浏览器复制的 Cookie"\n\n'
        "或：\n\n"
        "[wencai]\n"
        'cookie = "从浏览器复制的 Cookie"'
    )
    st.warning("Cookie 等同于网页登录凭证，不要发到聊天、GitHub、截图里。失效后需要重新复制。")

pywencai, import_err = safe_import_pywencai()
if import_err:
    st.error("pywencai 导入失败。请检查 requirements.txt 是否安装 pywencai。")
    st.code(import_err)
    st.stop()

if not cookie:
    st.error("未读取到 WENCAI_COOKIE。请先在 Streamlit Secrets 中配置 Cookie。")
    st.stop()

tabs = st.tabs(["查询测试", "批量模板", "Cookie 获取说明", "诊断信息"])

with tabs[0]:
    st.subheader("单次查询测试")

    default_query = "今日A股行业板块资金流入排名，显示板块名称、涨跌幅、主力净流入、成交额、领涨股"
    query = st.text_area("问财查询语句", value=default_query, height=100)

    col1, col2, col3 = st.columns(3)
    with col1:
        query_type_label = st.selectbox("query_type", list(QUERY_TYPES.keys()), index=0)
        query_type = QUERY_TYPES[query_type_label]
    with col2:
        perpage = st.number_input("perpage", min_value=1, max_value=100, value=50)
    with col3:
        retry = st.number_input("retry", min_value=1, max_value=10, value=3)

    col4, col5, col6 = st.columns(3)
    with col4:
        loop_opt = st.selectbox("loop", ["False", "True", "2页", "3页"], index=0)
    with col5:
        no_detail = st.checkbox("no_detail", value=False)
    with col6:
        log = st.checkbox("打印 pywencai 日志", value=False)

    sort_key = st.text_input("sort_key 可选，留空即可", value="")
    sort_order = st.selectbox("sort_order", ["desc", "asc"], index=0)

    if st.button("🚀 执行 pywencai 查询", type="primary"):
        if loop_opt == "False":
            loop_value = False
        elif loop_opt == "True":
            loop_value = True
        elif loop_opt == "2页":
            loop_value = 2
        else:
            loop_value = 3

        kwargs = {
            "query": query,
            "query_type": query_type,
            "cookie": cookie,
            "perpage": int(perpage),
            "retry": int(retry),
            "loop": loop_value,
            "no_detail": no_detail,
            "log": log,
        }
        if sort_key.strip():
            kwargs["sort_key"] = sort_key.strip()
            kwargs["sort_order"] = sort_order

        st.markdown("#### 调用参数")
        safe_kwargs = dict(kwargs)
        safe_kwargs["cookie"] = mask_cookie(cookie)
        st.json(safe_kwargs)

        try:
            with st.spinner("正在请求问财..."):
                res = pywencai.get(**kwargs)

            normalized = normalize_result(res)
            st.success(f"查询完成，返回类型：{normalized['kind']}")

            if normalized["frames"]:
                for i, df in enumerate(normalized["frames"], start=1):
                    st.markdown(f"#### 表格 {i}：{df.shape[0]} 行 × {df.shape[1]} 列")
                    st.dataframe(df.head(200), width="stretch")
            else:
                st.warning("没有提取到 DataFrame。下面展示原始返回。")
                render_raw(normalized["raw"])

        except Exception:
            st.error("查询失败")
            st.code(traceback.format_exc(), language="text")

with tabs[1]:
    st.subheader("批量模板测试")
    st.write("用于快速判断哪些类型的查询能返回数据。")

    templates = [
        ("行业板块资金", "今日A股行业板块资金流入排名，显示板块名称、涨跌幅、主力净流入、成交额、领涨股", "stock"),
        ("行业板块涨幅", "今日A股行业板块涨幅排名", "stock"),
        ("个股行情", "江海股份最新价、涨跌幅、总市值、换手率、市盈率、市净率", "stock"),
        ("公告", "江海股份最新公告", "stock"),
        ("研报", "江海股份最新研报和机构观点", "stock"),
        ("指数", "上证指数、深证成指、创业板指、沪深300今日行情", "zhishu"),
        ("宏观", "最近7天A股市场热点和宏观经济要闻", "stock"),
    ]

    if st.button("🧭 开始批量模板测试", type="primary"):
        records = []
        for name, q, qt in templates:
            try:
                res = pywencai.get(
                    query=q,
                    query_type=qt,
                    cookie=cookie,
                    perpage=20,
                    retry=2,
                    loop=False,
                    no_detail=False,
                )
                normalized = normalize_result(res)
                rows = 0
                cols = 0
                if normalized["frames"]:
                    rows = normalized["frames"][0].shape[0]
                    cols = normalized["frames"][0].shape[1]
                records.append({
                    "模板": name,
                    "query_type": qt,
                    "是否成功": True,
                    "返回类型": normalized["kind"],
                    "首表行数": rows,
                    "首表列数": cols,
                    "查询语句": q,
                    "错误": "",
                })
            except Exception as e:
                records.append({
                    "模板": name,
                    "query_type": qt,
                    "是否成功": False,
                    "返回类型": "",
                    "首表行数": 0,
                    "首表列数": 0,
                    "查询语句": q,
                    "错误": repr(e),
                })

        df = pd.DataFrame(records)
        st.dataframe(df, width="stretch")

with tabs[2]:
    st.subheader("Cookie 怎么获取")

    st.markdown(
        """
### 电脑浏览器获取方式

1. 用 Chrome / Edge 打开 **iwencai.com**，登录你的问财账号。
2. 打开问财页面，随便搜索一个问题，比如：`今日涨幅靠前的股票`。
3. 按 **F12** 打开开发者工具。
4. 进入 **Network / 网络**。
5. 刷新页面或重新搜索一次。
6. 在请求列表里点一个问财相关请求。
7. 在右侧 **Headers / 请求标头** 里找到：
   ```text
   Cookie: xxxxx
   ```
8. 只复制 `Cookie:` 后面的整段值，不要复制 `Cookie:` 这几个字。
9. 放到 Streamlit Secrets：

```toml
WENCAI_COOKIE = "复制来的整段 Cookie"
```

### 手机怎么弄

手机浏览器不方便复制完整 Cookie。更稳的方法是：

- 用电脑浏览器获取；
- 或在手机上用 Kiwi Browser / 支持开发者工具的浏览器；
- 或先在电脑复制 Cookie 保存到自己的密码管理器/备忘录，再粘到 Streamlit Secrets。

### 注意

Cookie 等同于你的网页登录状态，不要发给别人，不要传到 GitHub，不要发到聊天窗口。Cookie 失效后重新复制即可。
        """
    )

with tabs[3]:
    st.subheader("诊断信息")
    import sys
    st.write("Python：", sys.version)
    try:
        import py_mini_racer
        st.write("py_mini_racer：已安装")
    except Exception as e:
        st.write("py_mini_racer：", repr(e))
    st.write("pywencai：", getattr(pywencai, "__version__", "未知版本"))
    st.write("Cookie：", mask_cookie(cookie))
