/// Workbench 文件补丁操作（main.js / workbench.desktop.main.js）
use crate::error::AppError;
use crate::infra::cursor::ResolvedPaths;
use std::path::PathBuf;

const SEAMLESS_MARKER: &str = "/* __MYCURSOR_SEAMLESS__ */";

/// Workbench 补丁操作
pub struct WorkbenchPatcher<'a> {
    paths: &'a ResolvedPaths,
}

impl<'a> WorkbenchPatcher<'a> {
    pub fn new(paths: &'a ResolvedPaths) -> Self {
        Self { paths }
    }

    /// 获取 workbench.js 路径
    pub fn workbench_js_path(&self) -> Result<&PathBuf, AppError> {
        self.paths.workbench_js.as_ref()
            .ok_or_else(|| AppError::WorkbenchNotFound("workbench.desktop.main.js".to_string()))
    }

    /// 获取 main.js 路径
    pub fn main_js_path(&self) -> Result<&PathBuf, AppError> {
        self.paths.main_js.as_ref()
            .ok_or_else(|| AppError::WorkbenchNotFound("main.js".to_string()))
    }

    /// 检查 workbench 是否已被注入
    pub fn is_injected(&self) -> Result<bool, AppError> {
        let wp = self.workbench_js_path()?;
        if !wp.exists() {
            return Ok(false);
        }
        let content = std::fs::read_to_string(wp)?;
        Ok(content.contains("__MYCURSOR_SEAMLESS__"))
    }

    /// 获取无缝切号备份路径
    pub fn seamless_backup_path(&self) -> Result<PathBuf, AppError> {
        let wp = self.workbench_js_path()?;
        let filename = wp.file_name()
            .ok_or_else(|| AppError::Internal("无法获取文件名".to_string()))?
            .to_string_lossy();
        let mut backup = wp.clone();
        backup.set_file_name(format!("{}.backup.seamless", filename));
        Ok(backup)
    }

    /// 检查无缝切号备份是否存在
    pub fn backup_exists(&self) -> Result<bool, AppError> {
        Ok(self.seamless_backup_path()?.exists())
    }
}
