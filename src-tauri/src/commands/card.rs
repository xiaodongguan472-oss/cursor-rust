use serde::{Deserialize, Serialize};
use std::fs;
use super::utils;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CardVerifyResult {
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CardInfoResult {
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none", rename = "cardCode")]
    pub card_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "cardType")]
    pub card_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "startTime")]
    pub start_time: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "endTime")]
    pub end_time: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "useDays")]
    pub use_days: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

fn card_info_file_path() -> std::path::PathBuf {
    utils::get_app_data_dir().join("card_info.json")
}

fn get_device_id() -> String {
    let app_dir = utils::get_app_data_dir();
    let device_id_file = app_dir.join("device_id.txt");
    if device_id_file.exists() {
        if let Ok(cached) = fs::read_to_string(&device_id_file) {
            let cached = cached.trim().to_string();
            if cached.len() > 10 {
                return cached;
            }
        }
    }
    let id = utils::generate_stable_machine_id();
    let _ = fs::create_dir_all(&app_dir);
    let _ = fs::write(&device_id_file, &id);
    id
}

async fn do_verify(card_code: &str, api_url: &str) -> CardVerifyResult {
    let machine_id = get_device_id();

    let body = serde_json::json!({
        "cardCode": card_code,
        "deviceId": machine_id
    });

    let result = if api_url.contains("/renew") {
        utils::http_post_json(api_url, &body).await
    } else {
        utils::http_post_json(api_url, &body).await
    };

    match result {
        Ok(data) => {
            let success = data.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            if !success {
                let msg = data.get("message").and_then(|v| v.as_str()).unwrap_or("验证失败");
                return CardVerifyResult {
                    success: false,
                    data: None,
                    error: Some(msg.to_string()),
                };
            }

            // Calculate remaining days
            let mut remaining_days: i64 = 31;
            if let Some(end_time) = data.get("endTime").and_then(|v| v.as_str()) {
                if let Ok(end_dt) = chrono::NaiveDateTime::parse_from_str(end_time, "%Y-%m-%d %H:%M:%S") {
                    let now = chrono::Local::now().naive_local();
                    let diff = end_dt - now;
                    remaining_days = diff.num_days().max(0);
                }
            }

            let card_info = serde_json::json!({
                "card": data.get("cardCode").and_then(|v| v.as_str()).unwrap_or(""),
                "address": data.get("cardType").and_then(|v| v.as_str()).unwrap_or("专用"),
                "start": data.get("startTime").and_then(|v| v.as_str()).unwrap_or(""),
                "end": data.get("endTime").and_then(|v| v.as_str()).unwrap_or(""),
                "usetime": data.get("useDays").and_then(|v| v.as_u64()).unwrap_or(31).to_string()
            });

            let account_info = serde_json::json!({
                "userid": data.get("userId").and_then(|v| v.as_str()).unwrap_or(""),
                "email": data.get("email").and_then(|v| v.as_str()).unwrap_or(""),
                "token": data.get("token").and_then(|v| v.as_str()).unwrap_or(""),
                "current_time": chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
            });

            CardVerifyResult {
                success: true,
                data: Some(serde_json::json!({
                    "card_info": card_info,
                    "account_info": account_info,
                    "remaining_days": remaining_days
                })),
                error: None,
            }
        }
        Err(e) => CardVerifyResult {
            success: false,
            data: None,
            error: Some(format!("API请求失败: {}", e)),
        },
    }
}

#[tauri::command]
pub async fn verify_card_only(card_code: String) -> CardVerifyResult {
    let card_code = card_code.trim();
    let verify_url = utils::api_url("/hou/csk/card/verify");
    let result = do_verify(card_code, &verify_url).await;

    // Save card info to file if successful
    if result.success {
        if let Some(ref data) = result.data {
            if let Some(card_info) = data.get("card_info") {
                let save_data = serde_json::json!({
                    "cardCode": card_info.get("card").and_then(|v| v.as_str()).unwrap_or(""),
                    "cardType": card_info.get("address").and_then(|v| v.as_str()).unwrap_or("专用"),
                    "startTime": card_info.get("start").and_then(|v| v.as_str()).unwrap_or(""),
                    "endTime": card_info.get("end").and_then(|v| v.as_str()).unwrap_or(""),
                    "useDays": card_info.get("usetime").and_then(|v| v.as_str()).unwrap_or("31").parse::<u32>().unwrap_or(31),
                    "email": data.get("account_info").and_then(|a| a.get("email")).and_then(|v| v.as_str()).unwrap_or("")
                });
                let _ = save_card_info_to_file(&save_data);
            }
        }
    }

    result
}

#[tauri::command]
pub async fn verify_card(card_code: String) -> CardVerifyResult {
    let card_code = card_code.trim();
    let renew_url = utils::api_url("/hou/csk/card/renew");
    do_verify(card_code, &renew_url).await
}

#[tauri::command]
pub async fn get_card_info(card_code: String) -> CardInfoResult {
    let card_code = card_code.trim();
    let api_url = format!("{}/hou/csk/card/info/{}", utils::api_base(), card_code);

    match utils::http_get_json(&api_url).await {
        Ok(data) => {
            let success = data.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            CardInfoResult {
                success,
                card_code: data.get("cardCode").and_then(|v| v.as_str()).map(String::from),
                card_type: data.get("cardType").and_then(|v| v.as_str()).map(String::from),
                start_time: data.get("startTime").and_then(|v| v.as_str()).map(String::from),
                end_time: data.get("endTime").and_then(|v| v.as_str()).map(String::from),
                use_days: data.get("useDays").and_then(|v| v.as_u64()).map(|v| v as u32),
                error: if !success { data.get("message").and_then(|v| v.as_str()).map(String::from) } else { None },
            }
        }
        Err(e) => CardInfoResult {
            success: false,
            card_code: None, card_type: None, start_time: None, end_time: None, use_days: None,
            error: Some(format!("API请求失败: {}", e)),
        },
    }
}

fn save_card_info_to_file(card_info: &serde_json::Value) -> bool {
    let path = card_info_file_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }

    let mut data = card_info.clone();
    if let Some(obj) = data.as_object_mut() {
        obj.insert("savedAt".to_string(), serde_json::json!(chrono::Local::now().to_rfc3339()));
        obj.insert("machineId".to_string(), serde_json::json!(get_device_id()));
    }

    match serde_json::to_string_pretty(&data) {
        Ok(content) => fs::write(&path, content).is_ok(),
        Err(_) => false,
    }
}

#[tauri::command]
pub async fn save_card_info(card_info: serde_json::Value) -> bool {
    save_card_info_to_file(&card_info)
}

#[tauri::command]
pub async fn load_card_info() -> Option<serde_json::Value> {
    let path = card_info_file_path();
    if !path.exists() {
        return None;
    }

    let content = fs::read_to_string(&path).ok()?;
    let mut card_info: serde_json::Value = serde_json::from_str(&content).ok()?;

    // Verify data integrity
    let card_code = card_info.get("cardCode").and_then(|v| v.as_str());
    let end_time = card_info.get("endTime").and_then(|v| v.as_str());
    if card_code.is_none() || end_time.is_none() {
        return None;
    }

    // Check expiration
    if let Some(end_str) = end_time {
        if let Ok(end_dt) = chrono::NaiveDateTime::parse_from_str(end_str, "%Y-%m-%d %H:%M:%S") {
            let now = chrono::Local::now().naive_local();
            if end_dt <= now {
                if let Some(obj) = card_info.as_object_mut() {
                    obj.insert("expired".to_string(), serde_json::json!(true));
                }
            }
        }
    }

    Some(card_info)
}

#[tauri::command]
pub async fn clear_card_info() -> bool {
    let path = card_info_file_path();
    if path.exists() {
        fs::remove_file(&path).is_ok()
    } else {
        true
    }
}

#[tauri::command]
pub async fn record_usage(_card_code: String) -> serde_json::Value {
    serde_json::json!({
        "success": true,
        "message": "使用记录已保存"
    })
}
