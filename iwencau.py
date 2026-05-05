import os
import json
import shlex
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="爱问财 SkillHub CLI 测试台 v2", page_icon="🧪", layout="wide")

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
    extra_paths = [
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/.openclaw/bin"),
        os.path.expanduser("~/.skillhub/bin"),
        os.path.expanduser("~/.npm-global/bin"),
        os.path.expanduser("~/.npm/bin"),
        "/mount/src/iwencai/.bin",
        "/mount/src/iwencai/node_modules/.bin",
    ]
    env["PATH"] = ":".join(extra_paths + [env.get("PATH", "")])
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
        return p.returncode, (p.stdout or "")[-16000:], (p.stderr or "")[-16000:]
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", (e.stderr or "") + f"\n[TIMEOUT] 超过 {timeout} 秒未返回"
    except Exception as e:
        return 999, "", repr(e)


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
            st.dataframe(pd.DataFrame(rows).head(200), width="stretch")


def which_many(names: List[str]) -> pd.DataFrame:
    rows = []
    for name in names:
        _, out, _ = run_cmd(f"command -v {shlex.quote(name)} || true", timeout=5)
        rows.append({"命令": name, "路径": out.strip(), "是否存在": bool(out.strip())})
    return pd.DataFrame(rows)


def cli_probe_commands() -> str:
    return """
echo "===== basic ====="
python --version || true
node --version || true
npm --version || true
unzip -v | head -2 || true
curl --version | head -1 || true

echo "===== PATH ====="
echo "$PATH"

echo "===== command probe ====="
for c in skillhub iwencai wencai claw openclaw npx node npm unzip; do
  printf "%-12s -> " "$c"
  command -v "$c" || true
done

echo "===== home dirs ====="
ls -la ~ | head -80
echo "--- ~/.openclaw ---"; ls -la ~/.openclaw 2>/dev/null || true
echo "--- ~/.skillhub ---"; ls -la ~/.skillhub 2>/dev/null || true
echo "--- ~/.local/bin ---"; ls -la ~/.local/bin 2>/dev/null || true
echo "--- node_modules/.bin ---"; ls -la node_modules/.bin 2>/dev/null || true
"""


st.title("🧪 爱问财 SkillHub CLI 版 Streamlit 测试台 v2")
st.caption("v2 修复重点：增加 packages.txt 安装 unzip，并主动把 CLI 可能安装目录加入 PATH。")

env = get_iwencai_env()
base_url = env.get("IWENCAI_BASE_URL", "")
api_key = env.get("IWENCAI_API_KEY", "")

with st.sidebar:
    st.header("Secrets / 环境变量")
    st.write("IWENCAI_BASE_URL：", base_url)
    st.write("IWENCAI_API_KEY：", mask_key(api_key))
    st.markdown("---")
    st.info('Secrets 推荐：\n\nIWENCAI_BASE_URL = "https://openapi.iwencai.com"\nIWENCAI_API_KEY = "你的新 Key"')
    st.warning("不要在聊天窗口、GitHub 或代码里明文写 API Key。")

if not api_key:
    st.error("未读取到 IWENCAI_API_KEY。请先配置 Streamlit Secrets。")
    st.stop()

tabs = st.tabs(["1 环境检查", "2 官方安装", "3 技能安装", "4 技能调用", "5 自定义命令", "6 结论"])

with tabs[0]:
    st.subheader("环境检查")
    code, out, err = run_cmd(cli_probe_commands(), timeout=20)
    render_cmd_result(code, out, err)
    st.markdown("#### CLI 命令探测表")
    st.dataframe(which_many(["skillhub", "iwencai", "wencai", "claw", "openclaw", "npx", "node", "npm", "unzip"]), width="stretch")

with tabs[1]:
    st.subheader("执行官方安装脚本")
    st.warning("如果这里仍失败，请重点看 STDERR。v1 的失败原因是缺少 unzip；v2 已通过 packages.txt 安装 unzip。")
    install_cmd = f'''
set -e
echo "===== dependency check ====="
command -v unzip
command -v curl
node --version || true
npm --version || true

echo "===== download installer ====="
curl -fsSL {INSTALL_URL} -o /tmp/iwencai_skillhub_install.sh
sed -n '1,220p' /tmp/iwencai_skillhub_install.sh

echo "===== run installer ====="
bash /tmp/iwencai_skillhub_install.sh

echo "===== after install probe ====="
''' + cli_probe_commands()
    st.code(install_cmd, language="bash")
    timeout = st.slider("安装超时秒数", 30, 360, 180)
    if st.button("🚀 执行官方安装脚本", type="primary"):
        code, out, err = run_cmd(install_cmd, timeout=timeout)
        render_cmd_result(code, out, err)

with tabs[2]:
    st.subheader("安装技能")
    skill = st.selectbox("选择技能", OFFICIAL_SKILLS)
    cli_name = st.selectbox("CLI 命令名", ["skillhub", "iwencai", "claw", "openclaw", "npx skillhub"], index=0)
    install_variants = [
        f"{cli_name} install {skill}",
        f"{cli_name} skill install {skill}",
        f"{cli_name} add {skill}",
        f"{cli_name} skills install {skill}",
        f"{cli_name} list",
        f"{cli_name} --help",
    ]
    selected_cmd = st.selectbox("选择命令候选", install_variants)
    st.code(selected_cmd, language="bash")
    if st.button("📦 执行技能安装/探测", type="primary"):
        code, out, err = run_cmd(selected_cmd, timeout=120)
        render_cmd_result(code, out, err)
    st.markdown("#### 一键安装全部技能")
    all_cmd = "\n".join([f"{cli_name} install {s} || true" for s in OFFICIAL_SKILLS])
    st.code(all_cmd, language="bash")
    if st.button("📦 尝试安装全部技能"):
        code, out, err = run_cmd(all_cmd, timeout=300)
        render_cmd_result(code, out, err)

with tabs[3]:
    st.subheader("调用技能")
    skill = st.selectbox("选择技能", OFFICIAL_SKILLS, key="run_skill")
    cli_name = st.selectbox("CLI 命令名", ["skillhub", "iwencai", "claw", "openclaw", "npx skillhub"], index=0, key="run_cli")
    query = st.text_area("查询内容", value="今日A股行业板块资金流入排名，显示板块名称、涨跌幅、主力净流入、成交额、领涨股", height=90)
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
    timeout = st.slider("调用超时秒数", 10, 240, 90)
    if st.button("🔎 执行技能调用", type="primary"):
        code, out, err = run_cmd(selected_cmd, timeout=timeout)
        render_cmd_result(code, out, err)

with tabs[4]:
    st.subheader("自定义命令")
    st.warning("这里会执行 shell 命令。不要输入明文 Key，Key 已通过环境变量注入。")
    custom_cmd = st.text_area("自定义命令", value="env | grep IWENCAI | sed 's/IWENCAI_API_KEY=.*/IWENCAI_API_KEY=***MASKED***/g'", height=160)
    timeout = st.slider("自定义命令超时秒数", 5, 240, 60)
    if st.button("▶️ 执行自定义命令"):
        code, out, err = run_cmd(custom_cmd, timeout=timeout)
        render_cmd_result(code, out, err)

with tabs[5]:
    st.subheader("当前判断")
    st.markdown("""
你 v1 测试失败的直接原因已经很明确：

- 官方安装脚本失败：`unzip is required but not installed`
- 后续调用失败：`skillhub: command not found`

所以不是 Key 一定错，也不是技能一定不能用，而是 CLI 没有成功安装。  
v2 通过 `packages.txt` 安装 `unzip`，再重新运行官方安装脚本。

如果 v2 安装后仍然没有 `skillhub` 命令，请把“官方安装”页的完整 STDOUT/STDERR 发回来，我们继续看它实际安装出来的命令名和目录。
""")
