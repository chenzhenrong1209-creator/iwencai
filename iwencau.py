import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="爱问财 SkillHub 独立测试台",
    page_icon="🧪",
    layout="wide",
)

DEFAULT_BASE_URL = "https://openapi.iwencai.com"

OFFICIAL_SKILLS = {
    "问财选板块": "hithink-sector-selector",
    "行业数据查询": "hithink-industry-query",
    "研报搜索": "report-search",
    "公告搜索": "announcement-search",
    "指数数据查询": "hithink-zhishu-query",
    "行情数据查询": "hithink-market-query",
    "宏观数据查询": "hithink-macro-query",
}


def get_secret_value(*names: str, default: str = "") -> str:
    for name in names:
        try:
            value = st.secrets.get(name, "")
            if value:
                return str(value).strip()
        except Exception:
            pass
    return default


def get_iwencai_config() -> Tuple[str, str]:
    base_url = get_secret_value("IWENCAI_BASE_URL", "IWENCAI_URL", default=DEFAULT_BASE_URL)
    api_key = get_secret_value("IWENCAI_API_KEY", default="")

    try:
        section = st.secrets.get("iwencai", {})
        if isinstance(section, dict):
            base_url = str(section.get("base_url") or section.get("url") or base_url).strip()
            api_key = str(section.get("api_key") or api_key).strip()
    except Exception:
        pass

    return (base_url or DEFAULT_BASE_URL).rstrip("/"), api_key


def mask_key(key: str) -> str:
    if not key:
        return "未配置"
    if len(key) <= 12:
        return key[:3] + "***"
    return key[:8] + "..." + key[-6:]


def safe_json_loads(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\((\{.*\}|\[.*\])\)\s*;?\s*$", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return {"raw_text": text[:3000]}


def flatten_json(obj: Any, rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    if rows is None:
        rows = []
    if isinstance(obj, dict):
        scalar_items = {k: v for k, v in obj.items() if not isinstance(v, (dict, list))}
        if len(scalar_items) >= 2:
            rows.append(scalar_items)
        for v in obj.values():
            flatten_json(v, rows)
    elif isinstance(obj, list):
        for item in obj:
            flatten_json(item, rows)
    return rows


def extract_tables(obj: Any) -> List[pd.DataFrame]:
    tables = []

    def walk(x: Any):
        if isinstance(x, list):
            if x and all(isinstance(i, dict) for i in x):
                df = pd.DataFrame(x)
                if not df.empty:
                    tables.append(df)
            for i in x:
                walk(i)
        elif isinstance(x, dict):
            for key in ["data", "rows", "list", "result", "items", "datas", "values"]:
                v = x.get(key)
                if isinstance(v, list) and v and all(isinstance(i, dict) for i in v):
                    df = pd.DataFrame(v)
                    if not df.empty:
                        tables.append(df)
            if isinstance(x.get("columns"), list) and isinstance(x.get("rows"), list):
                try:
                    tables.append(pd.DataFrame(x["rows"], columns=x["columns"]))
                except Exception:
                    pass
            for v in x.values():
                walk(v)

    walk(obj)

    unique = []
    seen = set()
    for df in tables:
        sig = (tuple(map(str, df.columns)), df.head(3).to_json(force_ascii=False))
        if sig not in seen:
            unique.append(df)
            seen.add(sig)
    return unique


def post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int = 12) -> Dict[str, Any]:
    started = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        elapsed = round(time.time() - started, 3)
        parsed = safe_json_loads(resp.text)
        return {
            "ok": 200 <= resp.status_code < 300,
            "status_code": resp.status_code,
            "elapsed": elapsed,
            "url": url,
            "payload": payload,
            "headers_sent": {k: ("***" if k.lower() in {"authorization", "api-key", "apikey", "x-api-key"} else v) for k, v in headers.items()},
            "text_preview": resp.text[:2000],
            "json": parsed,
        }
    except Exception as e:
        elapsed = round(time.time() - started, 3)
        return {
            "ok": False,
            "status_code": None,
            "elapsed": elapsed,
            "url": url,
            "payload": payload,
            "headers_sent": {k: ("***" if k.lower() in {"authorization", "api-key", "apikey", "x-api-key"} else v) for k, v in headers.items()},
            "error": repr(e),
            "json": None,
        }


def build_headers(api_key: str, auth_style: str) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Streamlit-IWenCai-SkillHub-Tester/1.0",
    }
    if auth_style == "Authorization Bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif auth_style == "apikey":
        headers["apikey"] = api_key
    elif auth_style == "api-key":
        headers["api-key"] = api_key
    elif auth_style == "X-API-Key":
        headers["X-API-Key"] = api_key
    return headers


def skill_to_query(skill_id: str, query: str) -> str:
    mapping = {
        "hithink-sector-selector": f"使用问财选板块能力，查询：{query}",
        "hithink-industry-query": f"使用行业数据查询能力，查询：{query}",
        "report-search": f"搜索研报，查询：{query}",
        "announcement-search": f"搜索上市公司公告，查询：{query}",
        "hithink-zhishu-query": f"查询指数数据，查询：{query}",
        "hithink-market-query": f"查询行情数据，查询：{query}",
        "hithink-macro-query": f"查询宏观经济数据，查询：{query}",
    }
    return mapping.get(skill_id, query)


def make_payload(style: str, query: str, skill_id: str, page: int, limit: int) -> Dict[str, Any]:
    if style == "query2data 官方自然语言":
        return {
            "query": skill_to_query(skill_id, query),
            "source": "test",
            "page": str(page),
            "limit": str(limit),
            "is_cache": "1",
            "expand_index": "true",
        }
    if style == "SkillHub skill_id + query":
        return {
            "skill_id": skill_id,
            "skillId": skill_id,
            "query": query,
            "page": page,
            "limit": limit,
        }
    if style == "SkillHub skills 数组":
        return {
            "skills": [skill_id],
            "query": query,
            "page": page,
            "limit": limit,
        }
    if style == "Claw/Tool 调用结构":
        return {
            "name": skill_id,
            "arguments": {
                "query": query,
                "page": page,
                "limit": limit,
            },
        }
    return {"query": query, "page": page, "limit": limit}


def candidate_paths(skill_id: str) -> List[str]:
    return [
        "/v1/query2data",
        "/v1/skillhub/run",
        "/v1/skills/run",
        "/skillhub/run",
        "/api/skillhub/run",
        f"/v1/skills/{skill_id}/run",
    ]


st.title("🧪 爱问财 SkillHub 独立测试台")
st.caption("先在独立项目里确认 Key、Base URL、技能路径、认证方式和返回结构，再移植回量化终端。")

base_url, api_key = get_iwencai_config()

with st.sidebar:
    st.header("配置检查")
    st.write("Base URL：", base_url or "未配置")
    st.write("API Key：", mask_key(api_key))
    st.markdown("---")
    st.info(
        "Secrets 推荐：\n\n"
        'IWENCAI_BASE_URL = "https://openapi.iwencai.com"\n'
        'IWENCAI_API_KEY = "你的新Key"\n\n'
        "或：\n\n"
        "[iwencai]\n"
        'base_url = "https://openapi.iwencai.com"\n'
        'api_key = "你的新Key"'
    )

if not api_key:
    st.error("没有读取到 IWENCAI_API_KEY。请先在 Streamlit Secrets 中配置。")
    st.stop()

tab1, tab2, tab3 = st.tabs(["单技能测试", "批量诊断", "返回结构解析"])

with tab1:
    st.subheader("单技能测试")

    col1, col2 = st.columns([1, 1])
    with col1:
        skill_label = st.selectbox("选择官方技能", list(OFFICIAL_SKILLS.keys()), index=0)
        skill_id = OFFICIAL_SKILLS[skill_label]
        st.code(skill_id)
    with col2:
        auth_style = st.selectbox(
            "认证方式",
            ["Authorization Bearer", "apikey", "api-key", "X-API-Key"],
            index=0,
        )

    query = st.text_area(
        "测试查询",
        value="今日A股行业板块资金流入排名，显示板块名称、涨跌幅、主力净流入、成交额、领涨股",
        height=90,
    )

    col3, col4, col5 = st.columns([1, 1, 1])
    with col3:
        payload_style = st.selectbox(
            "请求体格式",
            ["query2data 官方自然语言", "SkillHub skill_id + query", "SkillHub skills 数组", "Claw/Tool 调用结构"],
            index=0,
        )
    with col4:
        path = st.selectbox("接口路径", candidate_paths(skill_id), index=0)
    with col5:
        timeout = st.number_input("超时秒数", min_value=3, max_value=60, value=15, step=1)

    page = st.number_input("page", min_value=1, max_value=20, value=1)
    limit = st.number_input("limit", min_value=1, max_value=100, value=20)

    if st.button("🚀 发送测试请求", type="primary"):
        url = base_url.rstrip("/") + path
        headers = build_headers(api_key, auth_style)
        payload = make_payload(payload_style, query, skill_id, page, limit)

        with st.spinner("正在请求爱问财接口..."):
            result = post_json(url, headers, payload, timeout=timeout)

        if result["ok"]:
            st.success(f"请求成功：HTTP {result['status_code']}，耗时 {result['elapsed']} 秒")
        else:
            st.error(f"请求失败：HTTP {result.get('status_code')}，耗时 {result['elapsed']} 秒")

        st.markdown("#### 请求信息")
        st.json({
            "url": result["url"],
            "headers_sent": result["headers_sent"],
            "payload": result["payload"],
        })

        st.markdown("#### 返回预览")
        st.code(result.get("text_preview") or result.get("error") or "", language="text")

        parsed = result.get("json")
        if parsed is not None:
            st.markdown("#### JSON")
            st.json(parsed)

            tables = extract_tables(parsed)
            if tables:
                st.markdown("#### 自动提取表格")
                for i, df in enumerate(tables[:5], start=1):
                    st.write(f"表格 {i}：{df.shape[0]} 行 × {df.shape[1]} 列")
                    st.dataframe(df.head(50), use_container_width=True)
            else:
                rows = flatten_json(parsed)
                if rows:
                    st.markdown("#### 递归摊平字段")
                    st.dataframe(pd.DataFrame(rows).head(100), use_container_width=True)

with tab2:
    st.subheader("批量诊断")
    st.write("依次测试多个认证方式、路径和技能，用来找出真正可用的组合。")

    batch_query = st.text_area(
        "批量诊断查询",
        value="今日A股行业板块资金流入排名，显示板块名称、涨跌幅、主力净流入、成交额、领涨股",
        height=80,
        key="batch_query",
    )
    selected_skills = st.multiselect(
        "选择要批量测试的技能",
        list(OFFICIAL_SKILLS.keys()),
        default=["问财选板块", "行业数据查询", "行情数据查询"],
    )
    max_paths = st.slider("每个技能最多测试几个路径", 1, 6, 3)
    batch_timeout = st.slider("单次请求超时秒数", 3, 30, 8)

    if st.button("🧭 开始批量诊断", type="primary"):
        records = []
        progress = st.progress(0)
        total = max(1, len(selected_skills) * 4 * max_paths)
        done = 0

        for label in selected_skills:
            skill_id = OFFICIAL_SKILLS[label]
            for auth_style in ["Authorization Bearer", "apikey", "api-key", "X-API-Key"]:
                for path in candidate_paths(skill_id)[:max_paths]:
                    url = base_url.rstrip("/") + path
                    headers = build_headers(api_key, auth_style)
                    payload = make_payload("query2data 官方自然语言", batch_query, skill_id, 1, 10)
                    result = post_json(url, headers, payload, timeout=batch_timeout)

                    preview = result.get("text_preview") or result.get("error") or ""
                    records.append({
                        "技能": label,
                        "skill_id": skill_id,
                        "认证方式": auth_style,
                        "路径": path,
                        "HTTP": result.get("status_code"),
                        "成功": result["ok"],
                        "耗时": result["elapsed"],
                        "返回预览": preview[:180],
                    })
                    done += 1
                    progress.progress(min(1.0, done / total))

        df = pd.DataFrame(records)
        st.dataframe(df, use_container_width=True)

        ok_df = df[df["成功"] == True]
        if not ok_df.empty:
            st.success("找到可用组合。优先看下面这些行。")
            st.dataframe(ok_df, use_container_width=True)
        else:
            st.error("没有找到 2xx 成功组合。请检查 Base URL、Key 权限、接口路径或官方套餐是否开通。")

with tab3:
    st.subheader("返回结构解析")
    st.write("把官方测试台或日志里的 JSON 粘到这里，帮助我们写解析器。")

    raw = st.text_area("粘贴 JSON 返回", height=220)
    if st.button("解析 JSON"):
        parsed = safe_json_loads(raw)
        if parsed is None:
            st.error("无法解析。")
        else:
            st.json(parsed)
            tables = extract_tables(parsed)
            if tables:
                for i, df in enumerate(tables[:8], start=1):
                    st.write(f"表格 {i}：{df.shape[0]} 行 × {df.shape[1]} 列")
                    st.dataframe(df.head(100), use_container_width=True)
            else:
                rows = flatten_json(parsed)
                if rows:
                    st.dataframe(pd.DataFrame(rows).head(200), use_container_width=True)
                else:
                    st.warning("没有提取到表格或摊平字段。")
