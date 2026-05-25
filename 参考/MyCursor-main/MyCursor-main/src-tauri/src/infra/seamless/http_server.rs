/// 无缝切号 HTTP 服务器
///
/// 监听 127.0.0.1:{port}，为 Cursor 内部的注入脚本提供 API 接口。
use crate::{log_error, log_info};
use std::io::{self, Read};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// CORS 头部注入
fn cors_headers(
    r: tiny_http::Response<io::Cursor<Vec<u8>>>,
) -> tiny_http::Response<io::Cursor<Vec<u8>>> {
    r.with_header("Access-Control-Allow-Origin: *".parse::<tiny_http::Header>().unwrap())
        .with_header("Access-Control-Allow-Methods: GET, POST, OPTIONS".parse::<tiny_http::Header>().unwrap())
        .with_header("Access-Control-Allow-Headers: Content-Type".parse::<tiny_http::Header>().unwrap())
        .with_header("Content-Type: application/json; charset=utf-8".parse::<tiny_http::Header>().unwrap())
}

/// JSON 响应构造
fn json_resp(status: u16, body: &str) -> tiny_http::Response<io::Cursor<Vec<u8>>> {
    cors_headers(
        tiny_http::Response::from_string(body)
            .with_status_code(tiny_http::StatusCode(status)),
    )
}

/// 读取账号缓存文件
fn read_account_cache(data_dir: &std::path::Path) -> Result<serde_json::Value, String> {
    let p = data_dir.join("account_cache.json");
    if !p.exists() {
        return Ok(serde_json::json!([]));
    }
    let c = std::fs::read_to_string(&p).map_err(|e| e.to_string())?;
    serde_json::from_str(&c).map_err(|e| e.to_string())
}

/// 处理 /api/accounts 请求
fn handle_accounts(data_dir: &std::path::Path) -> tiny_http::Response<io::Cursor<Vec<u8>>> {
    match read_account_cache(data_dir) {
        Ok(a) => json_resp(200, &serde_json::json!({"code":0,"data":a}).to_string()),
        Err(e) => json_resp(500, &serde_json::json!({"code":1,"msg":e}).to_string()),
    }
}

/// 处理 /api/switch 请求
fn handle_switch(body: &str, data_dir: &std::path::Path) -> tiny_http::Response<io::Cursor<Vec<u8>>> {
    #[derive(serde::Deserialize)]
    struct SwitchRequest {
        email: String,
    }

    let req: SwitchRequest = match serde_json::from_str(body) {
        Ok(r) => r,
        Err(e) => {
            return json_resp(400, &serde_json::json!({"code":1,"msg":e.to_string()}).to_string())
        }
    };

    let accs = match read_account_cache(data_dir) {
        Ok(a) => a,
        Err(e) => return json_resp(500, &serde_json::json!({"code":1,"msg":e}).to_string()),
    };

    match accs
        .as_array()
        .and_then(|a| a.iter().find(|x| x["email"].as_str() == Some(&req.email)))
    {
        Some(acc) => {
            log_info!("[无感换号] 切换: {}", req.email);
            json_resp(
                200,
                &serde_json::json!({
                    "code": 0,
                    "data": {
                        "token": acc["token"],
                        "email": acc["email"],
                        "refresh_token": acc["refresh_token"],
                        "machine_ids": acc.get("machine_ids")
                    }
                })
                .to_string(),
            )
        }
        None => json_resp(404, &serde_json::json!({"code":1,"msg":"未找到"}).to_string()),
    }
}

/// 运行 HTTP 服务器（阻塞）
pub fn run(port: u16, data_dir: &std::path::Path, stop_flag: &AtomicBool) {
    let addr = format!("127.0.0.1:{}", port);
    let srv = match tiny_http::Server::http(&addr) {
        Ok(s) => s,
        Err(e) => {
            log_error!("[无感换号] 启动失败: {}", e);
            return;
        }
    };
    log_info!("[无感换号] 服务器启动: {}", addr);

    while !stop_flag.load(Ordering::SeqCst) {
        match srv.recv_timeout(std::time::Duration::from_millis(500)) {
            Ok(Some(mut req)) => {
                let url = req.url().to_string();
                let method = req.method().to_string();

                if method == "OPTIONS" {
                    let _ = req.respond(json_resp(200, "{}"));
                    continue;
                }

                let resp = match (method.as_str(), url.as_str()) {
                    ("GET", "/api/health") => json_resp(200, r#"{"status":"ok"}"#),
                    ("GET", "/api/accounts") => handle_accounts(data_dir),
                    ("POST", "/api/switch") => {
                        let mut body = String::new();
                        let _ = req.as_reader().read_to_string(&mut body);
                        handle_switch(&body, data_dir)
                    }
                    _ => json_resp(404, r#"{"code":1}"#),
                };

                let _ = req.respond(resp);
            }
            Ok(None) => {}
            Err(e) => {
                log_error!("[无感换号] {}", e);
            }
        }
    }
}
