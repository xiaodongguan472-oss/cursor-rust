use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use super::settings;
use super::utils;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CursorPaths {
    pub base_path: Option<String>,
    pub package_path: Option<String>,
    pub main_path: Option<String>,
    pub workbench_path: Option<String>,
    pub version: Option<String>,
    pub error: Option<String>,
}

fn find_cursor_base_path(settings: &settings::AppSettings) -> Option<PathBuf> {
    // Check custom path first
    if !settings.custom_cursor_path.is_empty() {
        let custom = settings.custom_cursor_path.trim().trim_matches(|c| c == '\'' || c == '"');
        let custom_path = PathBuf::from(custom);

        #[cfg(target_os = "windows")]
        {
            let win_app = custom_path.join("resources").join("app");
            if win_app.exists() {
                return Some(win_app);
            }
        }

        #[cfg(target_os = "macos")]
        {
            if custom.ends_with(".app") || custom.ends_with(".app/") {
                let p = custom.trim_end_matches('/');
                let base = PathBuf::from(p).join("Contents").join("Resources").join("app");
                if base.exists() {
                    return Some(base);
                }
            }
            let app_in_dir = custom_path.join("Cursor.app").join("Contents").join("Resources").join("app");
            if app_in_dir.exists() {
                return Some(app_in_dir);
            }
        }

        #[cfg(target_os = "linux")]
        {
            let linux_app = custom_path.join("resources").join("app");
            if linux_app.exists() {
                return Some(linux_app);
            }
        }

        // Try package.json directly
        if custom_path.join("package.json").exists() {
            return Some(custom_path);
        }

        // Try resources/app under custom path
        let resources_app = custom_path.join("resources").join("app");
        if resources_app.exists() {
            return Some(resources_app);
        }
    }

    // Default paths
    #[cfg(target_os = "windows")]
    {
        let home = dirs::home_dir()?;
        let default = home.join("AppData").join("Local").join("Programs").join("Cursor").join("resources").join("app");
        if default.exists() {
            return Some(default);
        }

        if let Ok(pf) = std::env::var("ProgramFiles") {
            let pf_path = PathBuf::from(pf).join("Cursor").join("resources").join("app");
            if pf_path.exists() {
                return Some(pf_path);
            }
        }

        if let Ok(pf86) = std::env::var("ProgramFiles(x86)") {
            let pf86_path = PathBuf::from(pf86).join("Cursor").join("resources").join("app");
            if pf86_path.exists() {
                return Some(pf86_path);
            }
        }
    }

    #[cfg(target_os = "macos")]
    {
        let default = PathBuf::from("/Applications/Cursor.app/Contents/Resources/app");
        if default.exists() {
            return Some(default);
        }
    }

    #[cfg(target_os = "linux")]
    {
        let paths = [
            "/opt/Cursor/resources/app",
            "/usr/share/cursor/resources/app",
        ];
        for p in &paths {
            let pb = PathBuf::from(p);
            if pb.exists() {
                return Some(pb);
            }
        }
    }

    None
}

#[tauri::command]
pub fn get_cursor_paths() -> CursorPaths {
    let app_settings = settings::load_settings();
    let base_path = match find_cursor_base_path(&app_settings) {
        Some(p) => p,
        None => {
            return CursorPaths {
                base_path: None,
                package_path: None,
                main_path: None,
                workbench_path: None,
                version: None,
                error: Some("Cursor安装路径不存在".to_string()),
            };
        }
    };

    let package_path = base_path.join("package.json");
    let main_path = base_path.join("out").join("main.js");
    let workbench_path = base_path
        .join("out")
        .join("vs")
        .join("workbench")
        .join("workbench.desktop.main.js");

    if !package_path.exists() || !main_path.exists() {
        return CursorPaths {
            base_path: Some(base_path.to_string_lossy().to_string()),
            package_path: None,
            main_path: None,
            workbench_path: None,
            version: None,
            error: Some("Cursor核心文件不存在".to_string()),
        };
    }

    // Read version
    let version = fs::read_to_string(&package_path)
        .ok()
        .and_then(|content| {
            serde_json::from_str::<serde_json::Value>(&content).ok()
        })
        .and_then(|v| v["version"].as_str().map(|s| s.to_string()));

    CursorPaths {
        base_path: Some(base_path.to_string_lossy().to_string()),
        package_path: Some(package_path.to_string_lossy().to_string()),
        main_path: Some(main_path.to_string_lossy().to_string()),
        workbench_path: if workbench_path.exists() {
            Some(workbench_path.to_string_lossy().to_string())
        } else {
            None
        },
        version,
        error: None,
    }
}

#[tauri::command]
pub fn get_user_data_path() -> Result<String, String> {
    utils::get_cursor_data_dir()
        .map(|p| p.to_string_lossy().to_string())
        .ok_or_else(|| "无法确定Cursor用户数据路径".to_string())
}

/// Get cursor install path from base_path (removing resources/app or Contents/Resources/app)
pub fn get_cursor_install_from_base_path(base_path: &str) -> PathBuf {
    let p = Path::new(base_path);
    #[cfg(target_os = "macos")]
    {
        // macOS: Contents/Resources/app → 往上3层到 .app 根目录
        p.parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .map(|p| p.to_path_buf())
            .unwrap_or_else(|| PathBuf::from(base_path))
    }
    #[cfg(not(target_os = "macos"))]
    {
        // Windows/Linux: resources/app → 往上2层
        p.parent()
            .and_then(|p| p.parent())
            .map(|p| p.to_path_buf())
            .unwrap_or_else(|| PathBuf::from(base_path))
    }
}
