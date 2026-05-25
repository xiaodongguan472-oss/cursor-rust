/// 认证领域模型
///
/// 包含用户认证信息、Token 信息、授权校验结果等纯数据结构。
use crate::domain::usage::AggregatedUsageData;
use serde::{Deserialize, Serialize};

/// 用户认证信息
#[derive(Debug, Clone, Serialize, Deserialize, specta::Type)]
pub struct UserAuthInfo {
    pub is_authorized: bool,
    pub token_length: usize,
    pub token_valid: bool,
    pub api_status: Option<u16>,
    pub error_message: Option<String>,
    pub checksum: Option<String>,
    pub account_info: Option<AuthAccountInfo>,
}

/// 认证模块的账号信息（区别于 account 模块的 AccountInfo）
#[derive(Debug, Clone, Serialize, Deserialize, specta::Type)]
pub struct AuthAccountInfo {
    pub email: Option<String>,
    pub username: Option<String>,
    pub subscription_type: Option<String>,
    pub subscription_status: Option<String>,
    pub trial_days_remaining: Option<i32>,
    pub usage_info: Option<String>,
    pub aggregated_usage: Option<AggregatedUsageData>,
}

/// 授权校验结果
#[derive(Debug, Clone, Serialize, Deserialize, specta::Type)]
pub struct AuthCheckResult {
    pub success: bool,
    pub user_info: Option<UserAuthInfo>,
    pub message: String,
    pub details: Vec<String>,
}

/// Token 信息（包含来源）
#[derive(Debug, Clone, Serialize, Deserialize, specta::Type)]
pub struct TokenInfo {
    pub token: Option<String>,
    pub source: String,
    pub found: bool,
    pub message: String,
}
