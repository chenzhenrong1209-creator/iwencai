import os
import json
import shlex
import subprocess
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="爱问财 SkillHub CLI 测试台",
    page_icon="🧪",
    layout="wide",
)

OFFICIAL_SKILLS = [
    "hithink-sector-selector",
    "hithink-industry-query",
    "report-search",
    "announcement-search",
    "hithink-zhishu-query",
    "hithink-market-query",
    "hithink-macro-query",
]

DEFAULT_BASE_URL = "https://openapi.iwencai.com"
INSTALL_URL = "https://www.iwencai.com/skillhub/static/0.0.4/download_and_install.sh"


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value).strip()
    except Exception:
        pass
    return default


def get_iwencai_env() -> Dict[str, str]:
    base_url = get_secret("IWENCAI_BASE_URL", DEFAULT_BASE_URL)
    api_key = get_secret("IWENCAI_API_KEY", "")

    try:
        section = st.secrets.get("iwencai", {})
        if isinstance(section, dict):
            base_url = str(section.get("base_url") or section.get("url") or base_url).strip()
            api_key = str(section.get("api_key") or api_key).strip()
    except Exception:
        pass

    env = os.environ.copy()
    env["IWENCAI_BASE_URL"] = base_url or DEFAULT_BASE_URL
    env["IWENCAI_API_KEY"] = api_key or ""
    return env


def mask_key(key: str) -> str:
    if not key:
        return "未配置"
    if len(key) < 16:
        return key[:3] + "***"
    return key[:8] + "..." + key[-6:]


def run_cmd(cmd: str, timeout: int = 30, env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env or get_iwencai_env(),
            executable="/bin/bash",
        )
        return p.returncode, (p.stdout or "")[-12000:], (p.stderr or "")[-12000:]
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", (e.stderr or "") + f"\n[TIMEOUT] 超过 {timeout} 秒未返回"
    except Exception as e:
        return 999, "", repr(e)


def which_many(names: List[str]) -> pd.DataFrame:
    rows = []
    for name in names:
        _, out, _ = run_cmd(f"command -v {shlex.quote(name)} || true", timeout=5)
        rows.append({"命令": name, "路径": out.strip(), "是否存在": bool(out.strip())})
    return pd.DataFrame(rows)


def extract_json_like(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    objects = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                objects.append(json.loads(line))
            except Exception:
                pass
    return objects or None


def flatten_json(obj: Any, rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    if rows is None:
        rows = []
    if isinstance(obj, dict):
        scalar = {k: v for k, v in obj.items() if not isinstance(v, (dict, list))}
        if len(scalar) >= 2:
            rows.append(scalar)
        for v in obj.values():
            flatten_json(v, rows)
    elif isinstance(obj, list):
        for item in obj:
            flatten_json(item, rows)
    return rows


def render_cmd_result(code: int, out: str, err: str):
    if code == 0:
        st.success(f"命令执行成功，退出码 {code}")
    else:
        st.error(f"命令执行失败，退出码 {code}")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### STDOUT")
        st.code(out or "无输出", language="text")
    with c2:
        st.markdown("#### STDERR")
        st.code(err or "无输出", language="text")

    parsed = extract_json_like(out)
    if parsed is not None:
        st.markdown("#### JSON 解析")
        st.json(parsed)
        rows = flatten_json(parsed)
        if rows:
            st.markdown("#### 摊平表格")
            st.dataframe(pd.DataFrame(rows).head(200), use_container_width=True)


st.title("🧪 爱问财 SkillHub CLI 版 Streamlit 测试台")
st.caption("目标：不再猜 REST 路径，而是按官方方式安装/调用 CLI，观察真实命令、真实输出和真实错误。")

env = get_iwencai_env()
base_url = env.get("IWENCAI_BASE_URL", "")
api_key = env.get("IWENCAI_API_KEY", "")

with st.sidebar:
    st.header("Secrets / 环境变量")
    st.write("IWENCAI_BASE_URL：", base_url)
    st.write("IWENCAI_API_KEY：", mask_key(api_key))
    st.markdown("---")
    st.info(
        "Streamlit Secrets 建议：\n\n"
        'IWENCAI_BASE_URL = "https://openapi.iwencai.com"\n'
        'IWENCAI_API_KEY = "你的新 Key"\n\n'
        "或：\n\n"
        "[iwencai]\n"
        'base_url = "https://openapi.iwencai.com"\n'
        'api_key = "你的新 Key"'
    )
    st.warning("不要在聊天窗口、GitHub 或代码里明文写 API Key。")

if not api_key:
    st.error("未读取到 IWENCAI_API_KEY。请先配置 Streamlit Secrets。")
    st.stop()

tabs = st.tabs(["1 环境检查", "2 安装 CLI", "3 技能安装", "4 技能调用", "5 自定义命令", "6 接回主系统建议"])

with tabs[0]:
    st.subheader("环境检查")

    st.markdown("#### Python / Shell / Node")
    code, out, err = run_cmd("python --version && node --version 2>/dev/null || true && npm --version 2>/dev/null || true && uname -a", timeout=10)
    render_cmd_result(code, out, err)

    st.markdown("#### 可能的 CLI 命令探测")
    candidates = ["skillhub", "iwencai", "wencai", "claw", "openclaw", "npx", "node", "npm"]
    st.dataframe(which_many(candidates), use_container_width=True)

    st.markdown("#### 相关目录探测")
    code, out, err = run_cmd(
        "ls -la ~ 2>/dev/null | head -100; "
        "echo '--- ~/.openclaw ---'; ls -la ~/.openclaw 2>/dev/null || true; "
        "echo '--- ~/.skillhub ---'; ls -la ~/.skillhub 2>/dev/null || true; "
        "echo '--- current ---'; pwd && ls -la",
        timeout=10,
    )
    render_cmd_result(code, out, err)

with tabs[1]:
    st.subheader("安装 CLI")
    st.warning("Streamlit Cloud 的运行环境可能重建，CLI 安装不一定永久保留。本页用于测试官方 CLI 能否在云端安装和执行。")

    install_cmd = f"""
set -e
curl -fsSL {INSTALL_URL} -o /tmp/iwencai_skillhub_install.sh
bash /tmp/iwencai_skillhub_install.sh
echo "---- after install ----"
command -v skillhub || true
command -v iwencai || true
command -v claw || true
command -v openclaw || true
ls -la ~/.openclaw 2>/dev/null || true
ls -la ~/.skillhub 2>/dev/null || true
"""
    st.code(install_cmd, language="bash")

    timeout = st.slider("安装超时秒数", 30, 300, 120, key="install_timeout")
    if st.button("🚀 执行官方安装脚本", type="primary"):
        with st.spinner("正在执行官方安装脚本..."):
            code, out, err = run_cmd(install_cmd, timeout=timeout)
        render_cmd_result(code, out, err)

with tabs[2]:
    st.subheader("技能安装")
    st.write("如果 CLI 已安装，尝试安装官方技能。不同 CLI 的命令名可能不同，所以这里提供多种候选命令。")

    skill = st.selectbox("选择技能", OFFICIAL_SKILLS)
    cli_name = st.selectbox("CLI 命令名", ["skillhub", "iwencai", "claw", "openclaw", "npx skillhub"], index=0)

    install_variants = [
        f"{cli_name} install {skill}",
        f"{cli_name} skill install {skill}",
        f"{cli_name} add {skill}",
        f"{cli_name} skills install {skill}",
        f"{cli_name} --help",
    ]

    selected_cmd = st.selectbox("选择安装命令候选", install_variants)
    st.code(selected_cmd, language="bash")

    if st.button("📦 执行技能安装/探测", type="primary"):
        code, out, err = run_cmd(selected_cmd, timeout=90)
        render_cmd_result(code, out, err)

    st.markdown("#### 一键尝试安装全部技能")
    all_cmd = "\n".join([f"{cli_name} install {s} || true" for s in OFFICIAL_SKILLS])
    st.code(all_cmd, language="bash")
    if st.button("📦 尝试安装全部技能"):
        code, out, err = run_cmd(all_cmd, timeout=240)
        render_cmd_result(code, out, err)

with tabs[3]:
    st.subheader("技能调用")

    skill = st.selectbox("选择要调用的技能", OFFICIAL_SKILLS, key="run_skill")
    cli_name = st.selectbox("CLI 命令名", ["skillhub", "iwencai", "claw", "openclaw", "npx skillhub"], index=0, key="run_cli")

    query = st.text_area(
        "查询内容",
        value="今日A股行业板块资金流入排名，显示板块名称、涨跌幅、主力净流入、成交额、领涨股",
        height=90,
    )

    q = shlex.quote(query)
    run_variants = [
        f"{cli_name} run {skill} --query {q}",
        f"{cli_name} exec {skill} --query {q}",
        f"{cli_name} call {skill} --query {q}",
        f"{cli_name} run {skill} {q}",
        f"{cli_name} {skill} {q}",
        f"{cli_name} --help",
    ]

    selected_cmd = st.selectbox("选择调用命令候选", run_variants)
    st.code(selected_cmd, language="bash")
    run_timeout = st.slider("调用超时秒数", 10, 180, 60, key="run_timeout")

    if st.button("🔎 执行技能调用", type="primary"):
        code, out, err = run_cmd(selected_cmd, timeout=run_timeout)
        render_cmd_result(code, out, err)

with tabs[4]:
    st.subheader("自定义命令")
    st.warning("这里会在 Streamlit Cloud 容器里执行命令。不要输入包含明文 Key 的命令。Key 已通过环境变量注入。")
    custom_cmd = st.text_area(
        "自定义 shell 命令",
        value="env | grep IWENCAI | sed 's/IWENCAI_API_KEY=.*/IWENCAI_API_KEY=***MASKED***/g'",
        height=160,
    )
    custom_timeout = st.slider("自定义命令超时秒数", 5, 180, 30)

    if st.button("▶️ 执行自定义命令"):
        code, out, err = run_cmd(custom_cmd, timeout=custom_timeout)
        render_cmd_result(code, out, err)

with tabs[5]:
    st.subheader("接回主系统建议")
    st.markdown(
        """
等这个测试台跑通后，我们只需要记录三件事：

1. **真正可用的 CLI 命令名**
2. **真正可用的技能调用命令格式**
3. **返回结构**：JSON、Markdown、CSV，还是纯文本表格。

接回主量化终端时，不再猜 REST 路径，而是用 `subprocess.run` 调用官方 CLI，并把 `IWENCAI_BASE_URL` 和 `IWENCAI_API_KEY` 从 Streamlit Secrets 注入环境变量。
        """
    )
