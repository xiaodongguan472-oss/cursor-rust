# Cursor 模型锁解锁（保留真实账号）— 技术文档

本文档描述如何在**保留用户真实 Cursor 登录账号（包括 free 账号）的前提下**，去掉 Cursor 客户端 UI 上的模型锁（🔒），让所有模型都能在选择器中选中。

> 作用域：本方案**只解 UI 锁**。它不改变服务端对该账号的权限判断 —— 真正发起 AI 请求时，服务端仍按账号实际订阅级别处理。如果你的目标是让 AI 请求真的可以打到付费模型，UI 解锁只是第一步，还需要你自己的中转层负责回源。

---

## 1. 背景：Cursor 是怎么决定显示"锁"的

经过对真实流量的逆向分析，Cursor 客户端**判断"是否给某个模型显示锁"的核心数据源是一个 HTTPS 接口**：

```
GET https://api2.cursor.sh/auth/full_stripe_profile
```

返回体（注意 `Content-Type: text/plain; charset=utf-8`，但内容是合法 JSON）：

```json
{
  "membershipType": "free",
  "verifiedStudent": false,
  "studentDiscountApplied": false,
  "trialEligible": true,
  "trialLengthDays": 7,
  "isOnStudentPlan": false,
  "isOnBillableAuto": true,
  "customerBalance": null,
  "trialWasCancelled": false,
  "isTeamMember": false,
  "teamMembershipType": null,
  "individualMembershipType": "free",
  "lastPaymentFailed": false,
  "pendingCancellationDate": null,
  "isYearlyPlan": false
}
```

**核心字段**：
- `membershipType: "free"` → 客户端把当前账号判定为 free → 模型选择器上付费模型显示 🔒
- `individualMembershipType: "free"` → 同上，作为冗余校验

**结论**：只要在客户端读到这个响应**之前**把 `membershipType` 和 `individualMembershipType` 改成 `"pro"` 或 `"ultra"`，UI 上的锁就会消失。

### 1.1 走过的弯路（避免重复踩坑）

最初我们以为锁是由 Statsig 实验 `free_user_model_picker.variant` 控制（社区资料常这么说）。实际验证：

- 接口：`POST /aiserver.v1.AnalyticsService/BootstrapStatsig`（返回 protobuf，内含一个大 JSON 字符串）
- 真实响应里 `hash_used: "djb2"`，所有 `dynamic_configs` 的 key 都是 **djb2 哈希后的数字 ID**（如 `1020226244`），不再是字符串 `free_user_model_picker`。
- 直接改字符串 key 的 dynamic_configs 等于往配置里**加了一个客户端永远查不到的字段**，对 UI 完全无效。
- 所以**不要再花时间在 Statsig 上**，直接改 `/auth/full_stripe_profile` 才是正解。

`BootstrapStatsig` 改写如果将来要做，必须先用 djb2 算法把 `free_user_model_picker` 哈希成数字，再去匹配 dynamic_configs 的 key。但目前没必要。

---

## 2. 实现方案：MITM 改写 stripe_profile

### 2.1 总体链路

```
Cursor 客户端
   │  HTTPS (HTTP/2)
   ▼
本地 MITM 代理 (监听 127.0.0.1:8189)
   │  - 拦截 /auth/full_stripe_profile
   │  - 把 membershipType: "free" 改成 "pro"
   │  - 其他所有请求原样透传
   ▼
真实 cursor.sh (api2.cursor.sh / api3.cursor.sh / ...)
```

**关键设计**：
- **完全透传**：除了 `/auth/full_stripe_profile`，所有请求/响应都不动 → 用户真实账号的 token、登录态、配额、AI 请求全部走原通道，不会出现"账号被劫持"的副作用。
- **只改 UI 信号**：不伪造账号、不伪造 token、不伪造 AvailableModels 列表 → 兼容性最高，Cursor 升级后大概率仍有效。

### 2.2 客户端需要的配置（一次性）

要让 Cursor 把流量交给本地 MITM，**必须**满足以下条件：

#### A. mitmproxy CA 证书要被信任
两个层面同时信任：

1. **Windows 系统信任根**：把 `~/.mitmproxy/mitmproxy-ca-cert.cer` 装到「受信任的根证书颁发机构」（本地计算机或当前用户均可）。

2. **Cursor 内嵌 Node 进程也要信任**（Cursor 是 Electron，请求是 Node 发的，Node 不读 Windows 信任根）：
   ```
   系统环境变量 NODE_EXTRA_CA_CERTS = <绝对路径>\mitmproxy-ca-cert.pem
   ```
   设置后必须**完全退出**所有 Cursor 进程再启动（环境变量旧进程不会重读）。

#### B. Cursor 设置走代理

修改 `%APPDATA%\Cursor\User\settings.json`，至少包含：
```json
{
  "http.proxy": "http://127.0.0.1:8189",
  "http.experimental.systemCertificatesV2": true
}
```

- `http.proxy`：让 Cursor 把 HTTPS 请求发到 MITM。
- `http.experimental.systemCertificatesV2`：开启实验性的系统证书集成，否则 Electron 不一定吃 Windows 信任根 + NODE_EXTRA_CA_CERTS。
- ~~`cursor.general.disableHttp2`~~：测试证明**不需要**，mitmproxy 12.x 支持 HTTP/2。如果遇到部分流量绕过代理才需要加。

#### C. 把上面的"手动配置"全部自动化

集成进自家程序时，A/B 两步不应该让用户手动做。完整自动化方案见第 4 节。三件事：

1. 把 mitmproxy CA 装到 Windows 信任根（弹 / 不弹 UAC 两种选择）。
2. 设置系统/用户环境变量 `NODE_EXTRA_CA_CERTS` 指向 PEM 路径。
3. 写入 / 合并 `settings.json`（保留用户已有键，仅追加 3 个键）。

退出 / 卸载时**反向操作**：移走 settings.json 中你写入的键，移走环境变量，可选移走信任根证书。否则用户停用你的工具后 Cursor 会因找不到代理而无法联网。

---

## 3. 自动化部署：把 CA 安装 / 环境变量 / settings.json 全部自动化

集成进自家程序时，不应该让用户去做"双击 .cer 文件→点下一步"这种事。本节给出全套自动化方案（Windows 平台），其它平台思路相同但命令不同。

### 3.1 CA 安装：两种选择

#### 选择 A：装到 `LocalMachine\Root`（全机器生效，**弹一次 UAC**）

- 命令：`certutil.exe -addstore Root <证书绝对路径>`
- 必须管理员权限 → 用 `Start-Process -Verb RunAs` 触发 UAC
- 用户**首次启动**程序时弹一次 UAC，点"是"即装完；以后启动检查到已装则跳过，**0 弹窗**
- 用户点"否"：PowerShell 退出码为 `1223`，要捕获并提示

#### 选择 B：装到 `CurrentUser\Root`（仅当前用户生效，**完全无 UAC**）

- 命令：`certutil.exe -user -addstore Root <证书绝对路径>`
- 普通权限即可，**全程静默**
- 副作用：只对当前登录的 Windows 用户生效。多用户机器其他用户用 Cursor 会因证书不被信任而 TLS 失败
- **推荐策略**：先试 B，B 失败再退回 A（弹 UAC 兜底）

> 关于 CurrentUser 是否真的对 Cursor 生效：Electron + Node 在开启 `http.experimental.systemCertificatesV2` 后会读 Windows Schannel，Schannel 同时读 LocalMachine\Root 和 CurrentUser\Root，所以 B 也够用。

### 3.2 SHA1 指纹：判断"是否已装"的唯一标识

`certutil -verifystore Root <thumbprint>` 用大写无分隔的 SHA1（DER 字节的 SHA1）。从 PEM 计算的伪代码：

```
der_bytes  = base64_decode(pem 去掉 BEGIN/END/换行)
thumbprint = sha1(der_bytes).hex().upper()
```

### 3.3 Python 完整实现

```python
"""cert_install.py — Windows 下安装 mitmproxy CA 到信任根（自动选择 user/machine 存储）"""
import base64
import hashlib
import os
import subprocess
import sys
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000  # 隐藏 certutil/powershell 黑窗


def cert_sha1_from_pem(pem_path: Path) -> str:
    """读 PEM、提取第一个 cert 的 DER、算 SHA1（certutil 风格：大写无分隔）。"""
    text = pem_path.read_text(encoding="utf-8")
    # 取出 BEGIN/END CERTIFICATE 之间的 base64
    inside = []
    capture = False
    for line in text.splitlines():
        if "BEGIN CERTIFICATE" in line:
            capture = True
            continue
        if "END CERTIFICATE" in line:
            break
        if capture:
            inside.append(line.strip())
    if not inside:
        raise ValueError(f"未在 {pem_path} 找到 CERTIFICATE 段")
    der = base64.b64decode("".join(inside))
    return hashlib.sha1(der).hexdigest().upper()


def is_cert_installed(thumbprint: str, user_store: bool) -> bool:
    args = ["certutil.exe", "-verifystore"]
    if user_store:
        args.insert(1, "-user")
    args += ["Root", thumbprint]
    r = subprocess.run(
        args, capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return r.returncode == 0 and thumbprint in r.stdout.upper()


def install_user_store(pem_path: Path) -> bool:
    """装到 CurrentUser\\Root — 不弹 UAC。"""
    r = subprocess.run(
        ["certutil.exe", "-user", "-addstore", "Root", str(pem_path)],
        capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    if r.returncode != 0:
        sys.stderr.write(f"[cert] user store install failed rc={r.returncode}\n"
                         f"stdout: {r.stdout}\nstderr: {r.stderr}\n")
        return False
    return True


def install_machine_store_with_uac(pem_path: Path) -> bool:
    """装到 LocalMachine\\Root — 弹一次 UAC。用户点否返回 False。"""
    def quote(s: str) -> str:                # PowerShell 单引号转义
        return "'" + s.replace("'", "''") + "'"

    script = (
        "$p = Start-Process -FilePath 'certutil.exe' "
        f"-ArgumentList @('-addstore','Root',{quote(str(pem_path))}) "
        "-Verb RunAs -WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode"
    )
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    if r.returncode == 1223:
        sys.stderr.write("[cert] user declined UAC elevation\n")
        return False
    if r.returncode != 0:
        sys.stderr.write(f"[cert] machine store install failed rc={r.returncode}\n"
                         f"stdout: {r.stdout}\nstderr: {r.stderr}\n")
        return False
    return True


def ensure_mitmproxy_cert_installed(
    pem_path: Path,
    prefer_user_store: bool = True,
) -> str:
    """幂等保证 mitmproxy CA 在 Windows 信任根中。返回最终所在 store 名。

    策略：
      1. 检查 user store / machine store 是否已装（看一处即可），已装 → 返回。
      2. 若 prefer_user_store=True，先尝试静默装 user store。
      3. 失败再走 machine store（弹 UAC）。
    """
    if not pem_path.exists():
        raise FileNotFoundError(f"找不到证书 {pem_path}，请先启动 mitmdump 让它生成")

    thumb = cert_sha1_from_pem(pem_path)

    if is_cert_installed(thumb, user_store=True):
        return "CurrentUser\\Root"
    if is_cert_installed(thumb, user_store=False):
        return "LocalMachine\\Root"

    if prefer_user_store and install_user_store(pem_path):
        return "CurrentUser\\Root"

    if install_machine_store_with_uac(pem_path):
        return "LocalMachine\\Root"

    raise RuntimeError("证书安装失败：用户拒绝 UAC 或 certutil 报错")


def uninstall_mitmproxy_cert(pem_path: Path) -> None:
    """卸载/退出时调用，从两个 store 都尝试移除。失败忽略。"""
    thumb = cert_sha1_from_pem(pem_path)
    for user_flag in ([], ["-user"]):
        subprocess.run(
            ["certutil.exe", *user_flag, "-delstore", "Root", thumb],
            capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW,
        )
```

调用：

```python
pem = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
store = ensure_mitmproxy_cert_installed(pem)
print(f"CA 已就绪 in {store}")
```

### 3.4 NODE_EXTRA_CA_CERTS 环境变量

Cursor / VS Code 的请求是 Node 发的，Node 不读 Windows 信任根，必须额外指向 PEM。

#### 用户级（不需要管理员）

```python
def set_node_extra_ca_certs_user(pem_path: Path) -> None:
    """写入 HKCU\\Environment，对当前用户所有新进程生效。"""
    subprocess.run(
        ["setx", "NODE_EXTRA_CA_CERTS", str(pem_path)],
        capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    # 同时给当前进程一份，免重启
    os.environ["NODE_EXTRA_CA_CERTS"] = str(pem_path)
```

> **`setx` 的坑**：只对**新启动**的进程生效，已运行的 Cursor 不会感知。所以装完必须**完全退出 Cursor 再启动**（包括托盘）才会读到。

#### 系统级（弹 UAC）

```python
def set_node_extra_ca_certs_machine(pem_path: Path) -> None:
    """写入 HKLM\\...\\Environment，对所有用户生效，需要管理员。"""
    subprocess.run(
        ["setx", "/M", "NODE_EXTRA_CA_CERTS", str(pem_path)],
        capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    # 注意 setx /M 本身需要管理员运行；非管理员调用会失败
```

集成时优先用户级即可。

#### 清理

```python
def clear_node_extra_ca_certs() -> None:
    # setx 没有删除子命令，用 reg delete
    subprocess.run(
        ["reg", "delete", "HKCU\\Environment", "/F", "/V", "NODE_EXTRA_CA_CERTS"],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )
    os.environ.pop("NODE_EXTRA_CA_CERTS", None)
```

### 3.5 settings.json 的安全合并（不破坏用户已有配置）

`%APPDATA%\Cursor\User\settings.json` 用户可能已经有大量自定义键，**不能直接覆盖**。还要处理几个边缘情况：

- 文件可能不存在 → 当 `{}` 处理
- 文件可能是 JSONC（含 `//` 行注释 / `/* */` 块注释 / 尾随逗号）→ 先归一化再解析
- 文件可能有 BOM → 解析前剥掉
- 写回后用户可读 → 不要压缩成一行，用缩进 2 个空格
- 退出时只移走"自己加的"键，不动用户其它键

完整实现可参考本仓库 [`internal/cursor/settings.go`](../internal/cursor/settings.go) 的 `WriteUserProxySettings` / `ClearUserProxySettings` / `decodeCursorSettingsJSONC` / `stripJSONCComments` / `stripJSONCTrailingCommas`。Python 版的最小骨架：

```python
import json
import re
from pathlib import Path

# 我们维护的键集合 —— 卸载时只移除这些
MANAGED_KEYS = (
    "http.proxy",
    "http.experimental.systemCertificatesV2",
)

def _strip_jsonc(text: str) -> str:
    # 1) 去 BOM
    if text.startswith("﻿"):
        text = text[1:]
    # 2) 去注释（保留字符串里的 // 和 /*）
    out, i, n = [], 0, len(text)
    in_str = False
    escape = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch); i += 1; continue
        if ch == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                # 行注释
                i += 2
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
                continue
        out.append(ch); i += 1
    cleaned = "".join(out)
    # 3) 去尾随逗号  ,}  ,]
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    return cleaned


def cursor_settings_path() -> Path:
    return Path(os.environ["APPDATA"]) / "Cursor" / "User" / "settings.json"


def load_cursor_settings() -> dict:
    p = cursor_settings_path()
    if not p.exists():
        return {}
    raw = p.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    return json.loads(_strip_jsonc(raw))


def save_cursor_settings(data: dict) -> None:
    p = cursor_settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(encoded, encoding="utf-8")
    tmp.replace(p)


def apply_cursor_settings(proxy_url: str = "http://127.0.0.1:8189") -> None:
    s = load_cursor_settings()
    s["http.proxy"] = proxy_url
    s["http.experimental.systemCertificatesV2"] = True
    save_cursor_settings(s)


def clear_cursor_settings() -> None:
    s = load_cursor_settings()
    changed = False
    for k in MANAGED_KEYS:
        if k in s:
            del s[k]
            changed = True
    if changed:
        save_cursor_settings(s)
```

### 3.6 端到端自动化清单

集成程序的"启动"与"退出"对称地做这些事：

| 阶段 | 启动时做 | 退出 / 禁用时做 |
|---|---|---|
| MITM 代理 | 启动 mitmdump / 自家代理监听 127.0.0.1:8189 | 关闭代理进程 |
| mitmproxy CA | `ensure_mitmproxy_cert_installed(pem)` | `uninstall_mitmproxy_cert(pem)`（可选）|
| NODE_EXTRA_CA_CERTS | `set_node_extra_ca_certs_user(pem)` | `clear_node_extra_ca_certs()` |
| settings.json | `apply_cursor_settings(proxy_url)` | `clear_cursor_settings()` |
| 提示用户 | "请重新启动 Cursor 以应用配置" | "请重新启动 Cursor 以恢复直连" |

**关键提示**：环境变量和 settings.json 都需要 Cursor 重启才能生效。集成程序应该在第一次配置完成后弹一个非阻塞提示。

---

## 4. 核心改写逻辑（精确细节）

### 4.1 拦截规则

只在响应阶段（`response` hook）操作。匹配条件：

```
host  ∈ { api2.cursor.sh, api3.cursor.sh } 或后缀为 .cursor.sh
path  以  /auth/full_stripe_profile  结尾
```

### 4.2 body 判定（容易踩的坑）

Cursor 服务端返回这个接口时：

```
Content-Type: text/plain; charset=utf-8
Body:        {"membershipType":"free",...}   ← 实际是 JSON
```

**不要用 content-type 判断 JSON**！正确做法：
```python
text = body.decode("utf-8")
if not text.lstrip().startswith("{"):
    return  # 不是 JSON 形态
data = json.loads(text)
```

OPTIONS 预检（CORS）返回 204 + 空 body，会走到同一个 path，要先排除空 body。

### 4.3 字段改写

```python
TARGET_MEMBERSHIP = "pro"  # 或 "ultra"

# 关键字段
data["membershipType"] = TARGET_MEMBERSHIP
if data.get("individualMembershipType") is not None:
    data["individualMembershipType"] = TARGET_MEMBERSHIP

# 顺便规避一些"账号异常"横幅（可选但建议）
if data.get("trialWasCancelled") is True:
    data["trialWasCancelled"] = False
if data.get("pendingCancellationDate"):
    data["pendingCancellationDate"] = None
if data.get("lastPaymentFailed") is True:
    data["lastPaymentFailed"] = False
```

不要动 `verifiedStudent`、`isTeamMember`、`isOnStudentPlan` 等 —— 这些字段如果伪造可能触发额外校验，且与 UI 锁无关。

### 4.4 重写响应

```python
new_body = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
flow.response.content = new_body
flow.response.headers["content-length"] = str(len(new_body))
# 不要改 content-type，保持原始 text/plain; charset=utf-8
```

紧凑分隔符（无空格）保持和原响应一致，避免触发任何 size 校验。

---

## 5. 最小可工作实现（mitmproxy addon）

```python
"""cursor_unlock.py — mitmproxy addon"""
import json
import sys
from mitmproxy import http

CURSOR_HOSTS = {"api2.cursor.sh", "api3.cursor.sh"}
FULL_STRIPE_PROFILE_PATH = "/auth/full_stripe_profile"
TARGET_MEMBERSHIP = "pro"


def _host_matches(host: str) -> bool:
    h = (host or "").lower().strip()
    return h in CURSOR_HOSTS or h.endswith(".cursor.sh")


class CursorUnlock:
    def __init__(self):
        self.patched = 0

    def response(self, flow: http.HTTPFlow) -> None:
        if not _host_matches(flow.request.pretty_host):
            return
        if not flow.request.path.split("?")[0].endswith(FULL_STRIPE_PROFILE_PATH):
            return

        raw = flow.response.content or b""
        if not raw:
            return
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return
        if not text.lstrip().startswith("{"):
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return

        changed = False
        old_mt = data.get("membershipType")
        if old_mt != TARGET_MEMBERSHIP:
            data["membershipType"] = TARGET_MEMBERSHIP
            changed = True
        if data.get("individualMembershipType") not in (None, TARGET_MEMBERSHIP):
            data["individualMembershipType"] = TARGET_MEMBERSHIP
            changed = True
        if data.get("trialWasCancelled") is True:
            data["trialWasCancelled"] = False
            changed = True
        if data.get("pendingCancellationDate"):
            data["pendingCancellationDate"] = None
            changed = True
        if data.get("lastPaymentFailed") is True:
            data["lastPaymentFailed"] = False
            changed = True

        if not changed:
            return

        new_body = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        flow.response.content = new_body
        flow.response.headers["content-length"] = str(len(new_body))
        self.patched += 1
        print(f"[cursor_unlock] patched membershipType {old_mt}→{TARGET_MEMBERSHIP} "
              f"(total {self.patched})", file=sys.stderr)


addons = [CursorUnlock()]
```

启动：
```
mitmdump -s cursor_unlock.py --listen-host 127.0.0.1 --listen-port 8189
```

---

## 6. 集成到其他程序的建议

### 6.1 如果你的程序是 Go / Rust / Node MITM 代理

把上面的拦截逻辑翻译过去就行，伪代码：

```
on_response(flow):
    if not is_cursor_host(flow.request.host): return
    if not flow.request.path.endswith("/auth/full_stripe_profile"): return
    body = flow.response.body
    if not body: return
    if not body.lstrip().startswith(b"{"): return
    data = json.parse(body)
    if data.membershipType == "pro" and data.individualMembershipType == "pro": return
    data.membershipType = "pro"
    if data.individualMembershipType is not None:
        data.individualMembershipType = "pro"
    new = json.dumps(data, compact=True)
    flow.response.body = new
    flow.response.headers["content-length"] = len(new)
```

### 6.2 如果你已经有一套伪造账号的方案（像 cursor-client 那样）

`cursor-client` 的做法是**全套伪造**（假 token + 假 email + 假 plan + 假 stripe profile）。它本来就已经返回 `membershipType: "ultra"`，所以 UI 也是解锁的 —— 不需要叠加本方案。

本方案的价值在于**保留真实账号** —— 适用于：
- 让用户真实邮箱继续显示在 UI 上
- 让真实账号的配额继续走 cursor 服务端
- 只想去掉 UI 锁，不想接管账号体系

### 6.3 部署要点检查清单

集成到你的程序时务必处理：

| 项目 | 必做原因 |
|---|---|
| 透明部署 MITM CA 到 Windows 信任根 | 否则 Cursor 报 TLS 错误 |
| 设置 `NODE_EXTRA_CA_CERTS` 系统环境变量并提示重启 Cursor | Electron 的 Node 不读 Windows 信任根 |
| 写入 `settings.json` 加 `http.proxy` + `http.experimental.systemCertificatesV2` | 否则 Cursor 流量不走你的代理 |
| 处理 OPTIONS 预检（204 / 空 body）→ 不能崩 | 同 path 会被预检命中 |
| `content-type: text/plain` 也要当 JSON 处理 | 否则跳过改写 |
| 改写后重算 `content-length` | 否则部分客户端会报错 |
| 退出/卸载时移除 `settings.json` 里你写入的键 | 否则用户禁用你的工具后 Cursor 会因找不到代理而无法联网 |

---

## 7. 拓展：如果只改 stripe_profile 不够

实测在 Cursor 当前版本（2026-06 测）**只改 `full_stripe_profile.membershipType`** 就足以去掉模型选择器的锁。但 Cursor 版本更新可能引入额外校验，下面是已知的"相关接口"列表，按重要性排序，便于未来排查时叠加改写：

| 接口 | 关键字段 | 当前是否必须改 |
|---|---|---|
| `GET /auth/full_stripe_profile` | `membershipType`, `individualMembershipType` | ✅ 必须 |
| `GET /auth/stripe_profile` | （字符串形式的 paymentId） | ❌ 不必 |
| `POST /aiserver.v1.DashboardService/GetPlanInfo` | proto `planName`, `includedAmountCents` | ❌ 不必 |
| `POST /aiserver.v1.DashboardService/GetCurrentPeriodUsage` | proto `displayMessage`, `planUsage.*` | ❌ 不必 |
| `POST /aiserver.v1.DashboardService/GetMe` | proto `email`, `firstName`, `userId` | ❌ 不必（真实账号自带）|
| `POST /aiserver.v1.AiService/AvailableModels` | proto `models[].default_on`, `supports_*` | ❌ 不必 |
| `POST /aiserver.v1.AnalyticsService/BootstrapStatsig` | proto 嵌套 JSON, dynamic_configs（key 是 djb2 哈希）| ❌ 不必 |

**如果未来 Cursor 版本变化导致只改 stripe_profile 不够**：抓 `BootstrapStatsig` 的明文 JSON（field 1 的 string），看 `dynamic_configs` 里 djb2(`"free_user_model_picker"`) 对应的 hash 数字 key 的 value，再改 `variant`。djb2 算法：

```python
def djb2(s: str) -> str:
    h = 0
    for ch in s:
        h = ((h * 33) + ord(ch)) & 0xFFFFFFFFFFFFFFFF
    return str(h)
```

---

## 8. 风险与限制

| 风险 | 说明 |
|---|---|
| **服务端不会真给配额** | UI 解锁，但 free 账号实际请求付费模型时服务端可能 403。这一点本方案无法解决，必须配合中转层。|
| Cursor 升级可能改字段名 | 字段名一旦变（如 `membershipType` → `accountTier`），本方案立刻失效。建议在你的程序里加监控：每天抓一次 `/auth/full_stripe_profile` 真实响应做字段对比。|
| MITM CA 是安全敏感操作 | 装上去之后你的程序就能解密所有走它的 HTTPS 流量。集成时要让用户明确知情并能一键卸载。|
| Statsig 缓存 | Cursor 客户端会本地缓存 Statsig bootstrap 一段时间。改 stripe_profile 是即时生效的，但如果用户切换账号后立刻看，Statsig 那边可能短暂有偏差。一般忽略即可。|

---

## 9. 验证清单

集成完毕后，按下面顺序验证：

1. 启动你的 MITM 代理，监听某个端口（示例 8189）。
2. 装 CA + 设 `NODE_EXTRA_CA_CERTS` + 写 `settings.json`。
3. 完全退出 Cursor，重启。
4. 抓代理日志，确认 `/auth/full_stripe_profile` 被命中且日志打印 `patched membershipType free→pro`。
5. 打开 Cursor 模型选择器，确认所有付费模型不再显示 🔒。
6. 打开 Cursor Settings 左侧账号区，理论上仍显示你的真实邮箱（因为 GetMe 未改）；但 "Free Plan" 文案可能变化（这是次要 UI，不影响功能）。

如果第 5 步失败，按本文档第 6 节追加改写。

---

## 附录 A：实测得到的关键样本

**Free 账号的 `full_stripe_profile` 真实响应**（已脱敏）：
```json
{
  "membershipType": "free",
  "verifiedStudent": false,
  "studentDiscountApplied": false,
  "trialEligible": true,
  "trialLengthDays": 7,
  "isOnStudentPlan": false,
  "isOnBillableAuto": true,
  "customerBalance": null,
  "trialWasCancelled": false,
  "isTeamMember": false,
  "teamMembershipType": null,
  "individualMembershipType": "free",
  "lastPaymentFailed": false,
  "pendingCancellationDate": null,
  "isYearlyPlan": false
}
```

**改写后**（最小化改动）：
```json
{
  "membershipType": "pro",
  "verifiedStudent": false,
  "studentDiscountApplied": false,
  "trialEligible": true,
  "trialLengthDays": 7,
  "isOnStudentPlan": false,
  "isOnBillableAuto": true,
  "customerBalance": null,
  "trialWasCancelled": false,
  "isTeamMember": false,
  "teamMembershipType": null,
  "individualMembershipType": "pro",
  "lastPaymentFailed": false,
  "pendingCancellationDate": null,
  "isYearlyPlan": false
}
```

仅 `membershipType` 与 `individualMembershipType` 两个字段改动，其他全部原样保留。
