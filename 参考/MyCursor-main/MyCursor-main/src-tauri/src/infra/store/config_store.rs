/// 应用配置持久化（config.json）
use crate::error::AppError;
use std::path::PathBuf;

/// 配置存储
pub struct ConfigStore {
    path: PathBuf,
}

impl ConfigStore {
    pub fn new(data_dir: &PathBuf) -> Self {
        Self {
            path: data_dir.join("config.json"),
        }
    }

    /// 读取完整配置
    pub fn read(&self) -> serde_json::Value {
        self.path
            .exists()
            .then(|| {
                std::fs::read_to_string(&self.path)
                    .ok()
                    .and_then(|s| serde_json::from_str(&s).ok())
            })
            .flatten()
            .unwrap_or_else(|| serde_json::json!({}))
    }

    /// 写入配置
    pub fn write(&self, config: &serde_json::Value) -> Result<(), AppError> {
        let content = serde_json::to_string_pretty(config)?;
        std::fs::write(&self.path, content)?;
        Ok(())
    }

    /// 获取/设置自定义 Cursor 路径
    pub fn get_custom_cursor_path(&self) -> Option<String> {
        self.read()
            .get("custom_cursor_path")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string())
    }

    pub fn set_custom_cursor_path(&self, path: &str) -> Result<(), AppError> {
        let mut config = self.read();
        config["custom_cursor_path"] = serde_json::json!(path);
        self.write(&config)
    }

    pub fn clear_custom_cursor_path(&self) -> Result<(), AppError> {
        let mut config = self.read();
        if let Some(obj) = config.as_object_mut() {
            obj.remove("custom_cursor_path");
        }
        self.write(&config)
    }
}
