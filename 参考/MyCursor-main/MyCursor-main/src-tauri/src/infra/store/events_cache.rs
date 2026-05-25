/// 事件缓存持久化（events_data.json）
use crate::error::AppError;
use std::path::PathBuf;

/// 事件缓存
pub struct EventsCache {
    path: PathBuf,
}

impl EventsCache {
    pub fn new(data_dir: &PathBuf) -> Self {
        Self {
            path: data_dir.join("events_data.json"),
        }
    }

    /// 保存事件缓存
    pub fn save(&self, data: &str) -> Result<(), AppError> {
        std::fs::write(&self.path, data)?;
        Ok(())
    }

    /// 加载事件缓存
    pub fn load(&self) -> Result<serde_json::Value, AppError> {
        if !self.path.exists() {
            return Ok(serde_json::json!(null));
        }
        let content = std::fs::read_to_string(&self.path)?;
        let value: serde_json::Value = serde_json::from_str(&content)?;
        Ok(value)
    }

    /// 清除缓存
    pub fn clear(&self) -> Result<(), AppError> {
        if self.path.exists() {
            std::fs::remove_file(&self.path)?;
        }
        Ok(())
    }

    pub fn path(&self) -> &PathBuf {
        &self.path
    }
}
