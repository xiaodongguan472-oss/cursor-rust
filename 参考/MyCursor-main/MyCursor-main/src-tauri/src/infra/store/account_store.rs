/// 账号数据持久化（account_cache.json）
use crate::domain::account::AccountInfo;
use crate::error::AppError;
use std::path::PathBuf;

/// 账号数据存储
pub struct AccountStore {
    path: PathBuf,
}

impl AccountStore {
    pub fn new(data_dir: &PathBuf) -> Self {
        Self {
            path: data_dir.join("account_cache.json"),
        }
    }

    /// 加载所有账号
    pub fn load_all(&self) -> Result<Vec<AccountInfo>, AppError> {
        if !self.path.exists() {
            return Ok(Vec::new());
        }
        let content = std::fs::read_to_string(&self.path)?;
        let accounts: Vec<AccountInfo> = serde_json::from_str(&content)?;
        Ok(accounts)
    }

    /// 保存所有账号（原子写入）
    pub fn save_all(&self, accounts: &[AccountInfo]) -> Result<(), AppError> {
        self.atomic_write(accounts)
    }

    /// 加载原始 JSON（兼容旧接口）
    pub fn load_raw(&self) -> Result<serde_json::Value, AppError> {
        if !self.path.exists() {
            return Ok(serde_json::json!([]));
        }
        let content = std::fs::read_to_string(&self.path)?;
        let value: serde_json::Value = serde_json::from_str(&content)?;
        Ok(value)
    }

    /// 保存原始 JSON（兼容旧接口）
    pub fn save_raw(&self, data: &str) -> Result<(), AppError> {
        let tmp = self.path.with_extension("json.tmp");
        std::fs::write(&tmp, data)?;
        std::fs::rename(&tmp, &self.path)?;
        Ok(())
    }

    /// 清除所有缓存
    pub fn clear(&self) -> Result<(), AppError> {
        if self.path.exists() {
            std::fs::remove_file(&self.path)?;
        }
        Ok(())
    }

    /// 获取文件路径
    pub fn path(&self) -> &PathBuf {
        &self.path
    }

    /// 原子写入
    fn atomic_write(&self, accounts: &[AccountInfo]) -> Result<(), AppError> {
        let content = serde_json::to_string_pretty(accounts)?;
        let tmp = self.path.with_extension("json.tmp");
        std::fs::write(&tmp, &content)?;
        std::fs::rename(&tmp, &self.path)?;
        Ok(())
    }
}
