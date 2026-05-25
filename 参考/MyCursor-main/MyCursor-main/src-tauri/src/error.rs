/// 应用统一错误枚举
///
/// 整个后端只使用此类型，所有 command 返回 `Result<T, AppError>`。
/// 前端收到的是 `#[error("...")]` 定义的可读错误字符串。
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    // --- Cursor IDE 相关 ---
    #[error("未找到 Cursor IDE 安装路径")]
    CursorNotFound,

    #[error("Cursor 正在运行，请先关闭")]
    CursorRunning,

    #[error("未找到 workbench 文件：{0}")]
    WorkbenchNotFound(String),

    // --- 账号相关 ---
    #[error("账号不存在：{0}")]
    AccountNotFound(String),

    #[error("账号已存在：{0}")]
    AccountDuplicate(String),

    // --- 认证相关 ---
    #[error("Token 无效或已过期")]
    TokenInvalid,

    #[error("未授权（HTTP {0}）")]
    Unauthorized(u16),

    // --- 无缝切号 ---
    #[error("无缝切号服务启动失败：{0}")]
    SeamlessServerError(String),

    #[error("尚未注入 workbench")]
    NotInjected,

    // --- 备份 ---
    #[error("备份不存在：{0}")]
    BackupNotFound(String),

    // --- 通用 ---
    #[error("IO 错误：{0}")]
    Io(String),

    #[error("数据库错误：{0}")]
    Database(String),

    #[error("API 请求错误：{0}")]
    Api(String),

    #[error("校验错误：{0}")]
    Validation(String),

    #[error("平台错误：{0}")]
    Platform(String),

    #[error("{0}")]
    Internal(String),
}

impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e.to_string())
    }
}

impl From<rusqlite::Error> for AppError {
    fn from(e: rusqlite::Error) -> Self {
        Self::Database(e.to_string())
    }
}

impl From<reqwest::Error> for AppError {
    fn from(e: reqwest::Error) -> Self {
        Self::Api(e.to_string())
    }
}

impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        Self::Internal(e.to_string())
    }
}

impl From<anyhow::Error> for AppError {
    fn from(e: anyhow::Error) -> Self {
        Self::Internal(e.to_string())
    }
}

impl From<String> for AppError {
    fn from(e: String) -> Self {
        Self::Internal(e)
    }
}

impl From<&str> for AppError {
    fn from(e: &str) -> Self {
        Self::Internal(e.to_string())
    }
}

/// Tauri 要求命令返回的错误类型实现 Serialize
impl serde::Serialize for AppError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}
