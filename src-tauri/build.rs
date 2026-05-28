fn main() {
    // Windows: 通过 Tauri 自带的 WindowsAttributes 嵌入 requireAdministrator manifest
    let mut attrs = tauri_build::Attributes::new();

    #[cfg(windows)]
    {
        let windows = tauri_build::WindowsAttributes::new()
            .app_manifest(r#"
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>
"#);
        attrs = attrs.windows_attributes(windows);
    }

    tauri_build::try_build(attrs).expect("failed to run tauri build script");
}
