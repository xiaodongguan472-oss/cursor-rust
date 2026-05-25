/// 认证服务
///
/// 负责 Token 获取（按优先级链）、授权校验、用户信息查询。
use crate::domain::auth::*;
use crate::error::AppError;
use crate::infra::cursor::CursorBridge;
use crate::infra::api::CursorApiClient;
use crate::infra::api::checksum::{ChecksumBuilder, TokenParser};
use crate::{log_info, log_debug, log_error};
use std::path::PathBuf;

/// 认证服务
pub struct AuthService {
    cursor: CursorBridge,
    api: CursorApiClient,
}

impl AuthService {
    pub fn new(cursor: CursorBridge, api: CursorApiClient) -> Self {
        Self { cursor, api }
    }

    /// 自动获取 Token（按优先级链）
    pub fn get_token(&self) -> Result<TokenInfo, AppError> {
        // 优先级 1: 环境变量
        if let Ok(token) = std::env::var("CURSOR_TOKEN") {
            if !token.is_empty() {
                return Ok(TokenInfo {
                    token: Some(token),
                    source: "环境变量 CURSOR_TOKEN".to_string(),
                    found: true,
                    message: "从环境变量获取".to_string(),
                });
            }
        }

        if let Ok(token) = std::env::var("CURSOR_AUTH_TOKEN") {
            if !token.is_empty() {
                return Ok(TokenInfo {
                    token: Some(token),
                    source: "环境变量 CURSOR_AUTH_TOKEN".to_string(),
                    found: true,
                    message: "从环境变量获取".to_string(),
                });
            }
        }

        // 优先级 2: storage.json
        if let Ok(Some(token)) = self.cursor.storage().read_token() {
            if !token.is_empty() {
                let cleaned = TokenParser::extract_token_part(&token);
                return Ok(TokenInfo {
                    token: Some(cleaned),
                    source: "storage.json".to_string(),
                    found: true,
                    message: "从 storage.json 获取".to_string(),
                });
            }
        }

        // 优先级 3: SQLite (state.vscdb)
        if let Ok(Some(token)) = self.cursor.sqlite().read_token() {
            if !token.is_empty() {
                let cleaned = TokenParser::extract_token_part(&token);
                return Ok(TokenInfo {
                    token: Some(cleaned),
                    source: "state.vscdb".to_string(),
                    found: true,
                    message: "从 SQLite 获取".to_string(),
                });
            }
        }

        Ok(TokenInfo {
            token: None,
            source: "未找到".to_string(),
            found: false,
            message: "未找到有效的 Token".to_string(),
        })
    }

    /// 获取 CursorBridge 引用
    pub fn cursor(&self) -> &CursorBridge {
        &self.cursor
    }

    /// 获取 API 客户端引用
    pub fn api(&self) -> &CursorApiClient {
        &self.api
    }
}
