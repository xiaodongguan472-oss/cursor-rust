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

fn validate_cursor_file(content: &str) -> Result<(), String> {
    let open_braces = content.matches('{').count();
    let close_braces = content.matches('}').count();
    let open_parens = content.matches('(').count();
    let close_parens = content.matches(')').count();

    if open_braces != close_braces {
        return Err(format!("大括号不匹配: {} vs {}", open_braces, close_braces));
    }
    if open_parens != close_parens {
        return Err(format!("小括号不匹配: {} vs {}", open_parens, close_parens));
    }
    Ok(())
}

#[tauri::command]
pub async fn modify_cursor_main_js(main_path: String) -> ModifyResult {
    if !Path::new(&main_path).exists() {
        return ModifyResult { success: false, message: None, error: Some("文件不存在".to_string()) };
    }

    // Create backup
    let backup_path = format!("{}.bak", main_path);
    if !Path::new(&backup_path).exists() {
        let _ = fs::copy(&main_path, &backup_path);
    }

    let content = match fs::read_to_string(&main_path) {
        Ok(c) => c,
        Err(e) => return ModifyResult { success: false, message: None, error: Some(format!("读取文件失败: {}", e)) },
    };

    let mut new_content = content.clone();
    let mut modified = false;

    // Pattern 1: async getMachineId(){return ...??...}
    let patterns = [
        (r"async getMachineId\(\)\{return [^??]+\?\?([^}]+)\}", "async getMachineId(){return $1}"),
        (r"async getMacMachineId\(\)\{return [^??]+\?\?([^}]+)\}", "async getMacMachineId(){return $1}"),
    ];

    for (pattern, replacement) in &patterns {
        if let Ok(re) = regex::Regex::new(pattern) {
            if re.is_match(&new_content) {
                let before = new_content.clone();
                new_content = re.replace_all(&new_content, *replacement).to_string();
                if new_content != before {
                    modified = true;
                    break;
                }
            }
        }
    }

    // Loose pattern fallback
    if !modified {
        if let Ok(re) = regex::Regex::new(r"(getMachineId[^{]*\{[^}]*?return\s+[^;]*?)(\?\?)([^;}]+)") {
            if re.is_match(&new_content) {
                let before = new_content.clone();
                new_content = re.replace_all(&new_content, "$1$3").to_string();
                if new_content != before {
                    modified = true;
                }
            }
        }
    }

    if modified {
        if let Err(e) = validate_cursor_file(&new_content) {
            return ModifyResult {
                success: false, message: None,
                error: Some(format!("语法验证失败: {}", e)),
            };
        }

        let main_path_buf = Path::new(&main_path).to_path_buf();
        let write_result = utils::safe_modify_file(&main_path_buf, || {
            fs::write(&main_path, &new_content).map_err(|e| format!("写入文件失败: {}", e))
        });
        match write_result {
            Ok(_) => ModifyResult { success: true, message: Some("文件修改成功".to_string()), error: None },
            Err(e) => ModifyResult { success: false, message: None, error: Some(e) },
        }
    } else {
        ModifyResult {
            success: false, message: None,
            error: Some("未找到匹配的函数模式，建议启用强制修改模式或手动修改".to_string()),
        }
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
        // Enable pro
        if let Ok(re) = regex::Regex::new(r"(isPro:function\(\)\{return )(.*?)(\})") {
            if re.is_match(&new_content) {
                new_content = re.replace_all(&new_content, "${1}true${3}").to_string();
                modified = true;
            }
        }
        // Set usage days
        if let Some(d) = days {
            if let Ok(re) = regex::Regex::new(r"(getCursorTeamInfo:function\(\)\{return\{)([^}]*?)(\}\})") {
                if re.is_match(&new_content) {
                    new_content = re.replace_all(&new_content, &format!("${{1}}usageDays:{}${{3}}", d)).to_string();
                    modified = true;
                }
            }
        }
    } else {
        // Disable pro
        if let Ok(re) = regex::Regex::new(r"(isPro:function\(\)\{return )(.*?)(\})") {
            if re.is_match(&new_content) {
                new_content = re.replace_all(&new_content, "${1}false${3}").to_string();
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
