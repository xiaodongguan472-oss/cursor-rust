fn main() {
    // Windows: 强制以管理员身份运行（嵌入 requireAdministrator manifest）
    #[cfg(target_os = "windows")]
    {
        use embed_manifest::{embed_manifest, new_manifest, ExecutionLevel};
        embed_manifest(
            new_manifest("Cursor-Renewal")
                .requested_execution_level(ExecutionLevel::RequireAdministrator),
        )
        .expect("unable to embed manifest");
    }

    tauri_build::build()
}
