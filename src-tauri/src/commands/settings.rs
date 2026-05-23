use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use super::utils;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppSettings {
    #[serde(default = "default_true")]
    pub auto_check_update: bool,
    #[serde(default)]
    pub auto_activate_on_startup: bool,
    #[serde(default)]
    pub debug_mode: bool,
    #[serde(default)]
    pub force_modify_mode: bool,
    #[serde(default)]
    pub custom_cursor_path: String,
    #[serde(default)]
    pub agreement_accepted: bool,
}

fn default_true() -> bool { true }

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            auto_check_update: true,
            auto_activate_on_startup: false,
            debug_mode: false,
            force_modify_mode: false,
            custom_cursor_path: String::new(),
            agreement_accepted: false,
        }
    }
}

fn settings_path() -> PathBuf {
    let dir = utils::get_app_data_dir();
    dir.join("settings.json")
}

pub fn load_settings() -> AppSettings {
    let path = settings_path();
    if path.exists() {
        if let Ok(content) = fs::read_to_string(&path) {
            if let Ok(settings) = serde_json::from_str::<AppSettings>(&content) {
                return settings;
            }
        }
    }
    AppSettings::default()
}

fn save_settings_to_file(settings: &AppSettings) -> Result<(), String> {
    let path = settings_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("创建设置目录失败: {}", e))?;
    }
    let content = serde_json::to_string_pretty(settings)
        .map_err(|e| format!("序列化设置失败: {}", e))?;
    fs::write(&path, content).map_err(|e| format!("写入设置文件失败: {}", e))?;
    Ok(())
}

#[tauri::command]
pub async fn get_settings() -> AppSettings {
    utils::dlog!("[Settings] get_settings 被调用");
    load_settings()
}

#[tauri::command]
pub async fn save_settings(settings: AppSettings) -> Result<bool, String> {
    utils::dlog!("[Settings] save_settings 被调用");
    save_settings_to_file(&settings)?;
    Ok(true)
}

#[tauri::command]
pub fn quit_app(app_handle: tauri::AppHandle) {
    app_handle.exit(0);
}
