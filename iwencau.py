import os
import json
import shlex
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="爱问财 SkillHub CLI 测试台 v3",
    page_icon="🧪",
    layout="wide",
)

OFFICIAL_SKILLS = [
    "news-search",
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
ENV_SETUP_URL = "https://www.iwencai.com/skillhub/static/0.0.4/setup_iwencai_env.sh"


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value).strip()
    except Exception:
        pass
    return default


def get_env() -> Dict[str, str]:
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
    extra_paths = [
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/.iwencai/bin"),
        os.path.expanduser("~/.openclaw/bin"),
        os.path.expanduser("~/.skillhub/bin"),
        os.path.expanduser("~/bin"),
        "/mount/src/iwencai",
        "/mount/src/iwencai/.bin",
        "/mount/src/iwencai/node_modules/.bin",
    ]
    env["PATH"] = ":".join(extra_paths + [env.get("PATH", "")])
    return env


def mask_key(key: str) -> str:
    if not key:
        return "未配置"
    return key[:8] + "..." + key[-6:] if len(key) > 16 else key[:3] + "***"


def run_cmd(cmd: str, timeout: int = 60) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout,
            env=get_env(),
        )
        return p.returncode, (p.stdout or "")[-20000:], (p.stderr or "")[-20000:]
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", (e.stderr or "") + f"\n[TIMEOUT] 超过 {timeout} 秒未返回"
    except Exception as e:
        return 999, "", repr(e)


def parse_json(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    objs = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                objs.append(json.loads(line))
            except Exception:
                pass
    return objs or None


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


def render_result(code: int, out: str, err: str):
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

    parsed = parse_json(out)
    if parsed is not None:
        st.markdown("#### JSON 解析")
        st.json(parsed)
        rows = flatten_json(parsed)
        if rows:
            st.dataframe(pd.DataFrame(rows).head(200), width="stretch")


def probe_cmd() -> str:
    return '''
echo "===== basic ====="
python --version || true
node --version || true
npm --version || true
curl --version | head -1 || true
unzip -v | head -2 || true

echo "===== PATH ====="
echo "$PATH"

echo "===== command probe ====="
for c in iwencai-skillhub-cli skillhub iwencai wencai claw openclaw node npm npx unzip curl; do
  printf "%-24s -> " "$c"
  command -v "$c" || true
done

echo "===== directories ====="
echo "--- home ---"; ls -la ~ | head -80
echo "--- ~/.local/bin ---"; ls -la ~/.local/bin 2>/dev/null || true
echo "--- ~/.iwencai ---"; ls -la ~/.iwencai 2>/dev/null || true
echo "--- ~/.openclaw ---"; ls -la ~/.openclaw 2>/dev/null || true
echo "--- ~/.skillhub ---"; ls -la ~/.skillhub 2>/dev/null || true
echo "--- cwd ---"; pwd; ls -la
'''


st.title("🧪 爱问财 SkillHub CLI 版 Streamlit 测试台 v3")
st.caption("v3 按官方截图修正：CLI 名称为 iwencai-skillhub-cli，安装命令为 curl ... | bash -s，并增加系统依赖检测。")

env = get_env()
api_key = env.get("IWENCAI_API_KEY", "")
base_url = env.get("IWENCAI_BASE_URL", "")

with st.sidebar:
    st.header("配置")
    st.write("IWENCAI_BASE_URL：", base_url)
    st.write("IWENCAI_API_KEY：", mask_key(api_key))
    st.info(
        "Secrets：\n\n"
        'IWENCAI_BASE_URL = "https://openapi.iwencai.com"\n'
        'IWENCAI_API_KEY = "你的新 Key"'
    )

if not api_key:
    st.error("没有读取到 IWENCAI_API_KEY。")
    st.stop()

tabs = st.tabs(["1 环境检查", "2 官方安装 CLI", "3 环境变量脚本", "4 安装技能", "5 调用技能", "6 自定义命令"])

with tabs[0]:
    st.subheader("环境检查")
    code, out, err = run_cmd(probe_cmd(), timeout=30)
    render_result(code, out, err)
    st.warning("如果这里 node、npm、unzip 都不存在，说明 packages.txt 没有被 Streamlit Cloud 安装。请确认 packages.txt 在仓库根目录，并重新部署。")

with tabs[1]:
    st.subheader("官方安装 CLI")
    cmd = f'''
set -e
echo "===== check dependencies ====="
command -v curl
command -v unzip
node --version || true
npm --version || true

echo "===== run official installer ====="
curl -fsSL {INSTALL_URL} | bash -s

echo "===== after install ====="
''' + probe_cmd()
    st.code(cmd, language="bash")
    timeout = st.slider("安装超时秒数", 30, 360, 180, key="install_timeout")
    if st.button("🚀 执行官方 CLI 安装", type="primary"):
        code, out, err = run_cmd(cmd, timeout=timeout)
        render_result(code, out, err)

with tabs[2]:
    st.subheader("执行官方环境变量配置脚本")
    st.write("官方截图里的 setup_iwencai_env.sh 本质是写入环境变量。Streamlit 里仍以 Secrets 为主，这里用于验证官方脚本能不能运行。")
    cmd = f'''
set -e
curl -fsSL {ENV_SETUP_URL} | bash -s -- --IWENCAI_API_KEY="$IWENCAI_API_KEY" --IWENCAI_BASE_URL="$IWENCAI_BASE_URL"
echo "===== env after setup ====="
env | grep IWENCAI | sed 's/IWENCAI_API_KEY=.*/IWENCAI_API_KEY=***MASKED***/g'
'''
    st.code(cmd, language="bash")
    if st.button("🧩 执行环境变量脚本"):
        code, out, err = run_cmd(cmd, timeout=90)
        render_result(code, out, err)

with tabs[3]:
    st.subheader("安装技能")
    skill = st.selectbox("选择技能", OFFICIAL_SKILLS)
    cmd = f"iwencai-skillhub-cli install {skill}"
    st.code(cmd, language="bash")
    if st.button("📦 安装该技能", type="primary"):
        code, out, err = run_cmd(cmd, timeout=180)
        render_result(code, out, err)

    all_cmd = "\n".join([f"iwencai-skillhub-cli install {s} || true" for s in OFFICIAL_SKILLS])
    st.markdown("#### 一键安装全部技能")
    st.code(all_cmd, language="bash")
    if st.button("📦 安装全部技能"):
        code, out, err = run_cmd(all_cmd, timeout=360)
        render_result(code, out, err)

with tabs[4]:
    st.subheader("调用技能")
    skill = st.selectbox("选择技能", OFFICIAL_SKILLS, key="run_skill")
    query = st.text_area("查询内容", value="今日A股行业板块资金流入排名，显示板块名称、涨跌幅、主力净流入、成交额、领涨股", height=100)
    q = shlex.quote(query)
    variants = [
        f"iwencai-skillhub-cli run {skill} --query {q}",
        f"iwencai-skillhub-cli call {skill} --query {q}",
        f"iwencai-skillhub-cli exec {skill} --query {q}",
        f"iwencai-skillhub-cli {skill} {q}",
        "iwencai-skillhub-cli --help",
    ]
    cmd = st.selectbox("调用命令候选", variants)
    st.code(cmd, language="bash")
    timeout = st.slider("调用超时秒数", 10, 240, 90)
    if st.button("🔎 执行调用", type="primary"):
        code, out, err = run_cmd(cmd, timeout=timeout)
        render_result(code, out, err)

with tabs[5]:
    st.subheader("自定义命令")
    custom = st.text_area("命令", value="iwencai-skillhub-cli --help", height=160)
    timeout = st.slider("超时秒数", 5, 240, 60)
    if st.button("▶️ 执行自定义命令"):
        code, out, err = run_cmd(custom, timeout=timeout)
        render_result(code, out, err)
