use std::fs;
use std::path::Path;
use serde::{Deserialize, Serialize};
use super::utils;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModifyResult {
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisResult {
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub analysis: Option<FileAnalysis>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileAnalysis {
    pub file_size: usize,
    pub contains_get_machine_id: bool,
    pub contains_nullish_coalescing: bool,
    pub patterns: Vec<serde_json::Value>,
    pub nullish_lines: Vec<serde_json::Value>,
}

/// 计算文本中各类括号数量
fn count_brackets(s: &str) -> (usize, usize, usize, usize) {
    (
        s.matches('{').count(),
        s.matches('}').count(),
        s.matches('(').count(),
        s.matches(')').count(),
    )
}

/// 修补差值校验：保证修补前后括号数量没有改变（我们的正则只移除 `??xxx`，括号应保持不变）
///
/// 注意：不能用绝对平衡校验（{}=={}），因为 main.js 是 14MB 巨型 bundle，
/// 字符串/正则/注释中本来就有大量不平衡的 `{` `}`。
fn validate_patch_diff(before: &str, after: &str) -> Result<(), String> {
    let (b_ob, b_cb, b_op, b_cp) = count_brackets(before);
    let (a_ob, a_cb, a_op, a_cp) = count_brackets(after);

    if b_ob != a_ob || b_cb != a_cb {
        return Err(format!(
            "修补改变了大括号数量：{{ {} -> {}, }} {} -> {}",
            b_ob, a_ob, b_cb, a_cb
        ));
    }
    if b_op != a_op || b_cp != a_cp {
        return Err(format!(
            "修补改变了小括号数量：( {} -> {}, ) {} -> {}",
            b_op, a_op, b_cp, a_cp
        ));
    }
    Ok(())
}

/// 同步修补 main.js 文件，去掉 getMachineId/getMacMachineId 的 ?? fallback
///
/// 1:1 对齐 MyCursor 的 modify_main_js：直接 read + replace + write，不做权限处理包装。
/// macOS 上仅清除 chflags 不可变标志；权限不足由 std::fs::write 报错。
///
/// 返回 Ok(true) 表示修改了文件，Ok(false) 表示无需修补，Err 表示失败
pub fn patch_main_js_file(main_path: &Path) -> Result<bool, String> {
    if !main_path.exists() {
        return Err(format!("文件不存在: {}", main_path.display()));
    }

    // Create backup
    let backup_path = main_path.with_extension("js.bak");
    if !backup_path.exists() {
        let _ = fs::copy(main_path, &backup_path);
    }

    // macOS: 清除 chflags（仅对该文件；Cursor 安装目录通常不会有，但保险起见）
    utils::clear_macos_immutable_flag(main_path);

    let content = fs::read_to_string(main_path).map_err(|e| format!("读取文件失败: {}", e))?;

    // 与 MyCursor modify_main_js 完全一致的正则替换
    let patterns = [
        (r"async getMachineId\(\)\{return [^??]+\?\?([^}]+)\}", "async getMachineId(){return $1}"),
        (r"async getMacMachineId\(\)\{return [^??]+\?\?([^}]+)\}", "async getMacMachineId(){return $1}"),
    ];

    let mut new_content = content.clone();
    let mut modified = false;
    for (pattern, replacement) in &patterns {
        if let Ok(re) = regex::Regex::new(pattern) {
            let after = re.replace_all(&new_content, *replacement).to_string();
            if after != new_content {
                new_content = after;
                modified = true;
            }
        }
    }

    // 宽松模式 fallback（用于较新版本 Cursor，函数签名可能不同）
    if !modified {
        if let Ok(re) = regex::Regex::new(r"(getMachineId[^{]*\{[^}]*?return\s+[^;]*?)(\?\?)([^;}]+)") {
            let after = re.replace_all(&new_content, "$1$3").to_string();
            if after != new_content {
                new_content = after;
                modified = true;
            }
        }
    }

    if !modified {
        // 已经修补过 或 当前版本不需要修补
        return Ok(false);
    }

    // 差值校验：修补前后括号数量必须完全相同（移除 ??xxx 不应改变括号）
    validate_patch_diff(&content, &new_content).map_err(|e| format!("修补校验失败: {}", e))?;

    // === 直接写入，不做权限切换（与 MyCursor 完全一致）===
    fs::write(main_path, &new_content).map_err(|e| format!("写入文件失败: {}（提示：macOS 下 /Applications/Cursor.app 可能需要管理员权限）", e))?;

    Ok(true)
}

#[tauri::command]
pub async fn modify_cursor_main_js(main_path: String) -> ModifyResult {
    let path = Path::new(&main_path).to_path_buf();
    match patch_main_js_file(&path) {
        Ok(true) => ModifyResult { success: true, message: Some("文件修改成功".to_string()), error: None },
        Ok(false) => ModifyResult {
            success: false, message: None,
            error: Some("未找到匹配的函数模式，建议启用强制修改模式或手动修改".to_string()),
        },
        Err(e) => ModifyResult { success: false, message: None, error: Some(e) },
    }
}

#[tauri::command]
pub async fn analyze_cursor_file(file_path: String) -> AnalysisResult {
    if !Path::new(&file_path).exists() {
        return AnalysisResult { success: false, analysis: None, error: Some("文件不存在".to_string()) };
    }

    let content = match fs::read_to_string(&file_path) {
        Ok(c) => c,
        Err(e) => return AnalysisResult { success: false, analysis: None, error: Some(e.to_string()) },
    };

    let mut nullish_lines = Vec::new();
    for (i, line) in content.lines().enumerate() {
        if line.contains("??") {
            nullish_lines.push(serde_json::json!({
                "lineNumber": i + 1,
                "content": &line.trim()[..line.trim().len().min(100)]
            }));
            if nullish_lines.len() >= 10 { break; }
        }
    }

    AnalysisResult {
        success: true,
        analysis: Some(FileAnalysis {
            file_size: content.len(),
            contains_get_machine_id: content.contains("getMachineId"),
            contains_nullish_coalescing: content.contains("??"),
            patterns: vec![],
            nullish_lines,
        }),
        error: None,
    }
}

#[tauri::command]
pub async fn restore_cursor_backup(file_path: String) -> ModifyResult {
    let backup_path = format!("{}.bak", file_path);
    if !Path::new(&backup_path).exists() {
        return ModifyResult { success: false, message: None, error: Some("备份文件不存在".to_string()) };
    }
    if !Path::new(&file_path).exists() {
        return ModifyResult { success: false, message: None, error: Some("原文件不存在".to_string()) };
    }

    match fs::copy(&backup_path, &file_path) {
        Ok(_) => ModifyResult { success: true, message: Some("备份恢复成功".to_string()), error: None },
        Err(e) => ModifyResult { success: false, message: None, error: Some(e.to_string()) },
    }
}

#[tauri::command]
pub async fn modify_cursor_workbench(
    workbench_path: String,
    is_valid: bool,
    days: Option<u32>,
) -> ModifyResult {
    if !Path::new(&workbench_path).exists() {
        return ModifyResult { success: false, message: None, error: Some("文件不存在".to_string()) };
    }

    // Create backup
    let backup = format!("{}.bak", workbench_path);
    if !Path::new(&backup).exists() {
        let _ = fs::copy(&workbench_path, &backup);
    }

    let content = match fs::read_to_string(&workbench_path) {
        Ok(c) => c,
        Err(e) => return ModifyResult { success: false, message: None, error: Some(e.to_string()) },
    };

    let mut new_content = content.clone();
    let mut modified = false;

    if is_valid {
        // Enable pro: 正则 + 替换串都 obfstr 化（防 .rdata 暴露 Cursor 破解特征）
        let pattern = obfstr::obfstr!(r"(isPro:function\(\)\{return )(.*?)(\})").to_string();
        let replacement = obfstr::obfstr!("${1}true${3}").to_string();
        if let Ok(re) = regex::Regex::new(&pattern) {
            if re.is_match(&new_content) {
                new_content = re.replace_all(&new_content, replacement.as_str()).to_string();
                modified = true;
            }
        }
        // Set usage days: 正则也 obfstr 加密
        if let Some(d) = days {
            let team_pattern = obfstr::obfstr!(r"(getCursorTeamInfo:function\(\)\{return\{)([^}]*?)(\}\})").to_string();
            let usage_days_key = obfstr::obfstr!("usageDays").to_string();
            if let Ok(re) = regex::Regex::new(&team_pattern) {
                if re.is_match(&new_content) {
                    let replacement = format!("${{1}}{}:{}${{3}}", usage_days_key, d);
                    new_content = re.replace_all(&new_content, replacement.as_str()).to_string();
                    modified = true;
                }
            }
        }
    } else {
        // Disable pro: 正则 + 替换串都 obfstr 化
        let pattern = obfstr::obfstr!(r"(isPro:function\(\)\{return )(.*?)(\})").to_string();
        let replacement = obfstr::obfstr!("${1}false${3}").to_string();
        if let Ok(re) = regex::Regex::new(&pattern) {
            if re.is_match(&new_content) {
                new_content = re.replace_all(&new_content, replacement.as_str()).to_string();
                modified = true;
            }
        }
    }

    if !modified {
        return ModifyResult { success: false, message: None, error: Some("未找到匹配的函数模式".to_string()) };
    }

    let workbench_path_buf = Path::new(&workbench_path).to_path_buf();
    let write_result = utils::safe_modify_file(&workbench_path_buf, || {
        fs::write(&workbench_path, &new_content).map_err(|e| format!("写入失败: {}", e))
    });
    match write_result {
        Ok(_) => ModifyResult { success: true, message: None, error: None },
        Err(e) => ModifyResult { success: false, message: None, error: Some(e) },
    }
}

/// 启动时确保 Cursor 用户 settings.json 中 `"update.mode": "none"`，禁用自动更新。
///
/// settings.json 是 JSONC（允许 `//` 注释与尾随逗号），serde_json 严格解析会失败，
/// 因此分两条路线处理：
///   - 文件能被严格解析（干净 JSON，无注释）→ 直接改 Value 后用 pretty 回写；
///   - 解析失败（含注释/尾逗号）→ 在文本层面用正则替换/插入，保留用户注释。
/// 仅在确实需要改动时才写盘，避免无谓触碰文件（也降低 Cursor 运行时占用导致的写冲突）。
pub fn ensure_auto_update_disabled() {
    let path = match utils::get_cursor_settings_json_path() {
        Some(p) => p,
        None => {
            crate::ulog!("[AutoUpdate] 无法定位 settings.json 路径，跳过");
            return;
        }
    };

    // 读取现有内容；文件不存在或为空 → 创建最小配置
    let content = match fs::read_to_string(&path) {
        Ok(s) => s,
        Err(_) => {
            if let Some(parent) = path.parent() {
                let _ = fs::create_dir_all(parent);
            }
            let body = "{\n    \"update.mode\": \"none\"\n}\n";
            match fs::write(&path, body) {
                Ok(_) => { crate::ulog!("[AutoUpdate] settings.json 不存在，已创建并写入 update.mode=none"); }
                Err(e) => { crate::ulog!("[AutoUpdate] 创建 settings.json 失败: {}", e); }
            }
            return;
        }
    };

    if content.trim().is_empty() {
        let body = "{\n    \"update.mode\": \"none\"\n}\n";
        match fs::write(&path, body) {
            Ok(_) => { crate::ulog!("[AutoUpdate] settings.json 为空，已写入 update.mode=none"); }
            Err(e) => { crate::ulog!("[AutoUpdate] 写入空 settings.json 失败: {}", e); }
        }
        return;
    }

    // 路线 A：严格 JSON 解析成功（无注释/尾逗号）→ 用 Value 安全改写
    if let Ok(serde_json::Value::Object(mut map)) = serde_json::from_str::<serde_json::Value>(&content) {
        if map.get("update.mode").and_then(|v| v.as_str()) == Some("none") {
            crate::ulog!("[AutoUpdate] update.mode 已为 none，无需改动");
            return;
        }
        map.insert("update.mode".to_string(), serde_json::Value::String("none".to_string()));
        match serde_json::to_string_pretty(&serde_json::Value::Object(map)) {
            Ok(out) => match fs::write(&path, out) {
                Ok(_) => { crate::ulog!("[AutoUpdate] 已设置 update.mode=none（JSON 模式）"); }
                Err(e) => { crate::ulog!("[AutoUpdate] 回写 settings.json 失败: {}", e); }
            },
            Err(e) => { crate::ulog!("[AutoUpdate] 序列化 settings.json 失败: {}", e); }
        }
        return;
    }

    // 路线 B：JSONC（含注释/尾逗号）→ 文本层面处理，保留注释
    if content.contains("\"update.mode\"") {
        // 已是 none → 跳过
        let none_re = regex::Regex::new(r#""update\.mode"\s*:\s*"none""#).unwrap();
        if none_re.is_match(&content) {
            crate::ulog!("[AutoUpdate] update.mode 已为 none，无需改动（JSONC）");
            return;
        }
        // 替换已有键的字符串值
        let key_re = regex::Regex::new(r#"("update\.mode"\s*:\s*)"[^"]*""#).unwrap();
        if key_re.is_match(&content) {
            let new_content = key_re.replace(&content, r#"${1}"none""#).to_string();
            match fs::write(&path, new_content) {
                Ok(_) => { crate::ulog!("[AutoUpdate] 已将 update.mode 改为 none（JSONC 替换）"); }
                Err(e) => { crate::ulog!("[AutoUpdate] 回写 settings.json 失败: {}", e); }
            }
        } else {
            // 键存在但值不是简单字符串 → 不擅自改动，避免破坏配置
            crate::ulog!("[AutoUpdate] 检测到 update.mode 但值格式异常，未自动修改");
        }
        return;
    }

    // 没有该键 → 在第一个 '{' 之后插入（尾逗号在 JSONC 中合法）
    if let Some(idx) = content.find('{') {
        let mut new_content = String::with_capacity(content.len() + 32);
        new_content.push_str(&content[..=idx]);
        new_content.push_str("\n    \"update.mode\": \"none\",");
        new_content.push_str(&content[idx + 1..]);
        match fs::write(&path, new_content) {
            Ok(_) => { crate::ulog!("[AutoUpdate] 已插入 update.mode=none（JSONC 插入）"); }
            Err(e) => { crate::ulog!("[AutoUpdate] 回写 settings.json 失败: {}", e); }
        }
    } else {
        crate::ulog!("[AutoUpdate] settings.json 内容异常（缺少对象起始），跳过");
    }
}
