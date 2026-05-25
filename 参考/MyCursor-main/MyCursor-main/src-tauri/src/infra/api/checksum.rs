/// x-cursor-checksum 生成器与 Token 解析器
use crate::error::AppError;
use sha2::{Digest, Sha256};
use std::time::{SystemTime, UNIX_EPOCH};

/// Checksum 生成器
pub struct ChecksumBuilder;

impl ChecksumBuilder {
    /// 生成 x-cursor-checksum header 值
    pub fn build(machine_id: &str, mac_machine_id: &str) -> Result<String, AppError> {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|e| AppError::Internal(e.to_string()))?
            .as_millis();

        let data = format!(
            "{}{}",
            machine_id,
            timestamp
        );

        let mut hasher = Sha256::new();
        hasher.update(data.as_bytes());
        let hash = format!("{:x}", hasher.finalize());

        let checksum = format!(
            "{}{}",
            &hash[..16],
            &hash[16..32]
        );

        Ok(checksum)
    }
}

/// Token 清洗与解析
pub struct TokenParser;

impl TokenParser {
    /// 清洗 raw token（URL decode + 提取 :: 后的实际 token）
    pub fn clean(raw: &str) -> Result<String, AppError> {
        let decoded = raw.replace("%3A%3A", "::").replace("%3a%3a", "::");
        let token = if decoded.contains("::") {
            decoded.split("::").last().unwrap_or(&decoded)
        } else {
            &decoded
        };
        let trimmed = token.trim();
        if trimmed.is_empty() {
            return Err(AppError::TokenInvalid);
        }
        Ok(trimmed.to_string())
    }

    /// 提取 token 部分（不报错版本）
    pub fn extract_token_part(raw: &str) -> String {
        Self::clean(raw).unwrap_or_else(|_| raw.to_string())
    }
}
