// ============================================================================
// Cursor 模型锁 UI 解锁 —— v2 方案：直接改写渲染进程 workbench JS
//
// 背景（为什么从 MITM 代理换成这个方案）：
//   旧方案靠本地 MITM 代理 + settings.json 里的 http.proxy=127.0.0.1:8189，
//   拦截并改写 /auth/full_stripe_profile 响应把会员类型改成 pro。
//   但 http.proxy 是「全局」设置 —— Cursor 3.11+ 下，所有 cursor.sh 流量
//   （包括 AI 对话的 gRPC/http2 流式请求）都被迫经过 MITM 代理，
//   经过代理转发后 AI 请求报错「An unexpected error occurred」。
//   去掉 proxy 则 AI 恢复，但模型又被锁 —— 死结。
//
// 新方案：不碰网络层，直接改渲染进程的 workbench JS 文件。
//   会员状态最终都经过 `this.storeMembershipType=s=>{...}` 存进 storage，
//   我们在函数体开头强制 `s='pro'`，无论 Cursor 从哪个接口/缓存拿到会员状态，
//   存下来的都是 pro → 模型解锁。完全不影响 AI 流量，无需代理、无需 CA。
//
//   membershipType 枚举底层就是字符串（e.FREE="free", e.PRO="pro"），
//   所以直接塞字面量 'pro'，不依赖被混淆的枚举变量名。
//
// 注入点锚点：`this.storeMembershipType=s=>{`
//   在 workbench.desktop.main.js / workbench.glass.main.js 里各唯一出现 1 次，
//   两个文件形式完全一致。注入后变成：
//     this.storeMembershipType=s=>{/*MOCURSO_MODELUNLOCK*/s='pro';const o=...
// ============================================================================

use std::fs;
use std::path::{Path, PathBuf};
use super::utils;
use super::cursor_paths;

/// 幂等标记 —— 注入时插入，检查/避免重复注入靠它。
const UNLOCK_MARKER: &str = "/*MOCURSO_MODELUNLOCK*/";

/// 注入锚点正则：`storeMembershipType=<参数>=>{`
///
/// 关键：参数名随 Cursor 版本 / 混淆而变（3.5.17 是 `r`、3.11 是 `s`、其它版本可能不同），
/// 所以不能硬编码参数名，用正则捕获实际参数名，注入时复用它把该参数强制改成 'pro'。
///   3.5.17: storeMembershipType=r=>{  → storeMembershipType=r=>{/*MARKER*/r='pro';
///   3.11:   storeMembershipType=s=>{  → storeMembershipType=s=>{/*MARKER*/s='pro';
fn unlock_regex() -> regex::Regex {
    // 捕获组 1 = 参数名（合法 JS 标识符）
    regex::Regex::new(r"storeMembershipType=([A-Za-z_$][\w$]*)=>\{").unwrap()
}

/// 由匹配到的参数名构造「已注入」形态字符串，用于还原时定位。
fn injected_form(param: &str) -> String {
    format!("storeMembershipType={p}=>{{{m}{p}='pro';", p = param, m = UNLOCK_MARKER)
}

/// 需要处理的两个渲染进程文件名（desktop 常规窗口 / glass 新 UI）。
/// glass 在部分版本不存在，容忍缺失。
const WORKBENCH_FILES: &[&str] = &[
    "workbench.desktop.main.js",
    "workbench.glass.main.js",
];

/// 由 base_path（.../resources/app 或 .../Contents/Resources/app）推导某个 workbench 文件路径。
fn workbench_file_path(base_path: &Path, file_name: &str) -> PathBuf {
    base_path
        .join("out")
        .join("vs")
        .join("workbench")
        .join(file_name)
}

/// 取 Cursor base_path（resources/app）。取不到返回 None。
fn get_base_path() -> Option<PathBuf> {
    let paths = cursor_paths::get_cursor_paths();
    if paths.error.is_some() {
        return None;
    }
    paths.base_path.map(PathBuf::from)
}

/// 给单个 workbench 文件注入解锁补丁。
/// 返回 Ok(true)=已注入, Ok(false)=已存在无需注入/锚点未找到, Err=写入失败。
fn patch_one(path: &Path) -> Result<bool, String> {
    if !path.exists() {
        // glass 文件在部分版本不存在 —— 不算错误
        return Ok(false);
    }
    let content = fs::read_to_string(path).map_err(|e| format!("读取失败: {}", e))?;

    // 已注入 → 幂等跳过
    if content.contains(UNLOCK_MARKER) {
        return Ok(false);
    }

    // 正则匹配 storeMembershipType=<参数>=>{  —— 捕获参数名
    let re = unlock_regex();
    let caps = match re.captures(&content) {
        Some(c) => c,
        // 锚点不存在（Cursor 换了实现）→ 不报错，交由上层判断整体成败
        None => return Ok(false),
    };
    let param = caps.get(1).map(|m| m.as_str().to_string()).unwrap_or_default();
    if param.is_empty() {
        return Ok(false);
    }

    // 首次注入前备份纯净版
    let bak = PathBuf::from(format!("{}.mcbak", path.to_string_lossy()));
    if !bak.exists() {
        let _ = fs::copy(path, &bak);
    }

    // 只替换第一处（锚点本就唯一）：storeMembershipType=<p>=>{ → 后面插 /*MARKER*/<p>='pro';
    // 用 NoExpand 避免替换串里的 `$`（参数名可能以 $ 开头）被当成捕获组引用。
    let replacement = injected_form(&param);
    let new_content = re
        .replace(&content, regex::NoExpand(replacement.as_str()))
        .into_owned();

    utils::safe_modify_file(path, || {
        fs::write(path, &new_content).map_err(|e| format!("写入失败: {}", e))
    })?;
    Ok(true)
}

/// 还原单个 workbench 文件的解锁补丁（把注入串换回纯锚点）。
fn unpatch_one(path: &Path) -> Result<(), String> {
    if !path.exists() {
        return Ok(());
    }
    let content = fs::read_to_string(path).map_err(|e| format!("读取失败: {}", e))?;
    if !content.contains(UNLOCK_MARKER) {
        return Ok(()); // 没注入过
    }
    // 已注入形态：storeMembershipType=<p>=>{/*MARKER*/<p>='pro';  → 还原成 storeMembershipType=<p>=>{
    // 注意：Rust regex 不支持反向引用（\1），所以两个 <p> 分别用独立捕获组匹配
    // （实际它们相等，但正则层面不强制；MARKER 唯一已足够保证只命中我们注入的那处）。
    let restore_re = regex::Regex::new(&format!(
        r"storeMembershipType=([A-Za-z_$][\w$]*)=>\{{{}[A-Za-z_$][\w$]*='pro';",
        regex::escape(UNLOCK_MARKER)
    )).map_err(|e| format!("构造还原正则失败: {}", e))?;
    let new_content = restore_re
        .replace(&content, "storeMembershipType=$1=>{")
        .into_owned();
    utils::safe_modify_file(path, || {
        fs::write(path, &new_content).map_err(|e| format!("写入失败: {}", e))
    })
}

/// 检查单个文件是否已注入。
fn is_one_patched(path: &Path) -> bool {
    fs::read_to_string(path)
        .map(|c| c.contains(UNLOCK_MARKER))
        .unwrap_or(false)
}

// ============================================================================
// 对外接口 —— 与旧 unlock_mitm 同名语义，供 seamless_switch 调用
// ============================================================================

/// 开启模型解锁：给所有存在的 workbench 文件注入 storeMembershipType 强制 pro。
/// 只要 desktop 文件注入成功（或已注入）就算成功；glass 缺失可容忍。
pub fn enable_unlock() -> Result<(), String> {
    let base = get_base_path().ok_or_else(|| "无法定位 Cursor 安装路径".to_string())?;

    let mut desktop_ok = false;
    let mut errors: Vec<String> = Vec::new();

    for name in WORKBENCH_FILES {
        let path = workbench_file_path(&base, name);
        let is_desktop = *name == "workbench.desktop.main.js";
        match patch_one(&path) {
            Ok(true) => {
                if is_desktop { desktop_ok = true; }
            }
            Ok(false) => {
                // 文件不存在 / 已注入 / 锚点缺失
                if is_desktop && path.exists() && is_one_patched(&path) {
                    desktop_ok = true; // 已经注入过也算成功
                }
            }
            Err(e) => errors.push(format!("{}: {}", name, e)),
        }
    }

    if desktop_ok {
        Ok(())
    } else if !errors.is_empty() {
        Err(errors.join("; "))
    } else {
        Err("未找到可注入的 workbench 文件（Cursor 版本可能已变更解锁实现）".to_string())
    }
}

/// 关闭模型解锁：还原所有 workbench 文件。
pub fn disable_unlock() -> Result<(), String> {
    let base = match get_base_path() {
        Some(b) => b,
        None => return Ok(()), // 定位不到就算了，不阻塞关闭流程
    };
    for name in WORKBENCH_FILES {
        let path = workbench_file_path(&base, name);
        let _ = unpatch_one(&path);
    }
    Ok(())
}

/// 检查解锁是否已生效（desktop 文件已注入即视为已开启）。
#[allow(dead_code)]
pub fn is_unlock_enabled() -> bool {
    let base = match get_base_path() {
        Some(b) => b,
        None => return false,
    };
    let desktop = workbench_file_path(&base, "workbench.desktop.main.js");
    is_one_patched(&desktop)
}

/// 程序启动时调用：若之前开过解锁但 Cursor 更新覆盖了 workbench（补丁丢失），
/// 这里不主动重注入（避免用户没开解锁却被注入）——重注入交给「激活无感换号」流程。
/// 保留此函数是为了与旧 auto_restore_on_startup 调用点对齐；当前为 no-op。
pub fn auto_restore_on_startup() {
    // no-op：解锁状态由用户显式开关驱动，启动时不擅自注入。
}

