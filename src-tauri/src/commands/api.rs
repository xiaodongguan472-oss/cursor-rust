use super::utils;

#[tauri::command]
pub async fn get_latest_notice() -> serde_json::Value {
    utils::dlog!("[API] get_latest_notice 被调用");
    let api_url = utils::api_url(obfstr::obfstr!("/hou/csk/notice/latest"));
    let api_url = api_url.as_str();
    match utils::http_get_json(api_url).await {
        Ok(result) => {
            let success = result.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            if success && result.get("data").is_some() {
                return result;
            }
            // Fallback
            serde_json::json!({
                "success": true,
                "data": {
                    "id": 1,
                    "title": "最新公告",
                    "content": "不要频繁进行换号，一天之内如果进行大量无效换号，本店会进行设备封禁，一天10-20个号足够使用！！",
                    "time": chrono::Local::now().format("%Y-%m-%d %H:%M").to_string(),
                    "user": "系统管理员"
                }
            })
        }
        Err(e) => {
            utils::dlog!("[API] get_latest_notice 请求失败: {}", e);
            serde_json::json!({
                "success": true,
                "data": {
                    "id": 1,
                    "title": "最新公告",
                    "content": "不要频繁进行换号，一天之内如果进行大量无效换号，本店会进行设备封禁，一天10-20个号足够使用！！",
                    "time": chrono::Local::now().format("%Y-%m-%d %H:%M").to_string(),
                    "user": "系统管理员"
                }
            })
        }
    }
}

#[tauri::command]
pub async fn get_latest_tool_version() -> serde_json::Value {
    utils::dlog!("[API] get_latest_tool_version 被调用");
    let system_type = if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        if std::env::consts::ARCH == "aarch64" { "macM" } else { "macI" }
    } else {
        "linux"
    };

    // 优先使用新版 toolVersion 接口（带 description 字段）
    let new_api_url = format!(
        "{}{}{}",
        utils::api_base(),
        obfstr::obfstr!("/csk/toolVersion/latest?systemType="),
        system_type
    );

    match utils::http_get_json(&new_api_url).await {
        Ok(result) => {
            // newManager Result 格式: { code: "200", msg: "成功", data: {...} }
            let code = result.get("code").and_then(|v| v.as_str()).unwrap_or("");
            let success = result.get("success").and_then(|v| v.as_bool()).unwrap_or(false);

            if (code == "200" || success) && result.get("data").is_some() {
                // 转换为前端期望的统一格式
                return serde_json::json!({
                    "success": true,
                    "data": result.get("data")
                });
            }
            utils::dlog!("[API] toolVersion 接口返回非成功: {:?}", result);
        }
        Err(e) => {
            utils::dlog!("[API] toolVersion 接口失败: {}, 尝试旧接口", e);
        }
    }

    // 回退到旧接口
    let old_api_url = format!(
        "{}{}{}",
        utils::api_base(),
        obfstr::obfstr!("/hou/csk/download/latest-tool?systemType="),
        system_type
    );

    match utils::http_get_json(&old_api_url).await {
        Ok(result) => {
            let success = result.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            let code = result.get("code").and_then(|v| v.as_str()).unwrap_or("");
            if (success || code == "200") && result.get("data").is_some() {
                return serde_json::json!({
                    "success": true,
                    "data": result.get("data")
                });
            }
            serde_json::json!({
                "success": false,
                "message": "无法获取版本信息",
                "data": null
            })
        }
        Err(_e) => serde_json::json!({
            "success": false,
            "message": "无法连接到服务器",
            "data": null
        }),
    }
}

#[tauri::command]
pub async fn get_latest_popup() -> serde_json::Value {
    utils::dlog!("[API] get_latest_popup 被调用");
    let api_url = utils::api_url(obfstr::obfstr!("/hou/csk/popup/latest"));
    let api_url = api_url.as_str();
    match utils::http_get_json(api_url).await {
        Ok(result) => {
            let success = result.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            if success && result.get("data").is_some() {
                return result;
            }
            serde_json::json!({
                "success": false,
                "message": "暂无弹窗",
                "data": null
            })
        }
        Err(_) => serde_json::json!({
            "success": false,
            "message": "无法连接到服务器",
            "data": null
        }),
    }
}

#[tauri::command]
pub async fn get_qrcode_image() -> serde_json::Value {
    let api_url = utils::api_url(obfstr::obfstr!("/hou/csk/image/latest"));
    let api_url = api_url.as_str();
    match utils::http_get_json(api_url).await {
        Ok(result) => {
            let success = result.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            if success {
                if let Some(data) = result.get("data") {
                    if let Some(image_path) = data.get("imagePath").and_then(|v| v.as_str()) {
                        return serde_json::json!({
                            "success": true,
                            "imagePath": format!("{}{}{}", utils::api_base(), obfstr::obfstr!("/hou/csk/"), image_path),
                            "message": "获取二维码成功"
                        });
                    }
                }
            }
            serde_json::json!({
                "success": false,
                "message": "暂无二维码",
                "imagePath": null
            })
        }
        Err(_) => serde_json::json!({
            "success": false,
            "message": "无法连接到服务器",
            "imagePath": null
        }),
    }
}

#[tauri::command]
pub async fn check_version_update() -> serde_json::Value {
    utils::dlog!("[API] check_version_update 被调用");
    let app_version = env!("CARGO_PKG_VERSION");
    // 传递当前版本号，后端根据版本判断是否需要强制更新
    let api_url = format!(
        "{}{}{}",
        utils::api_base(),
        obfstr::obfstr!("/hou/csk/version/check?version="),
        app_version
    );

    match utils::http_get_json(&api_url).await {
        Ok(result) => {
            utils::dlog!("[API] check_version_update 返回: {:?}", result);
            let success = result.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            if success {
                if let Some(data) = result.get("data") {
                    // 直接透传后端返回的 data（包含 needUpdate/forceUpdate/updateMessage/downloadUrl 等）
                    return serde_json::json!({
                        "success": true,
                        "currentVersion": app_version,
                        "data": data
                    });
                }
            }
            serde_json::json!({
                "success": false,
                "currentVersion": app_version
            })
        }
        Err(e) => {
            utils::dlog!("[API] check_version_update 失败: {}", e);
            serde_json::json!({
                "success": false,
                "currentVersion": app_version
            })
        }
    }
}
