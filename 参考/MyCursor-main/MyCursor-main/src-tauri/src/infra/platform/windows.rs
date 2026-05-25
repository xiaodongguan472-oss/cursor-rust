/// Windows 平台特定实现
use crate::domain::identity::MachineIds;
use crate::error::AppError;
use super::PlatformOps;

pub struct WindowsOps;

impl PlatformOps for WindowsOps {
    fn update_system_ids(&self, ids: &MachineIds) -> Result<(), AppError> {
        use winreg::enums::*;
        use winreg::RegKey;

        let hklm = RegKey::predef(HKEY_LOCAL_MACHINE);

        // MachineGuid：优先使用绑定的 machine_guid（系统级），回退到 machine_id
        let guid_value = ids.machine_guid.as_deref().unwrap_or(&ids.machine_id);
        if let Ok(key) = hklm.open_subkey_with_flags(
            "SOFTWARE\\Microsoft\\Cryptography",
            KEY_SET_VALUE,
        ) {
            let _ = key.set_value("MachineGuid", &guid_value);
        }

        // SQMClient MachineId：优先使用绑定的 sqm_client_id（系统级），回退到 sqm_id
        let sqm_value = ids.sqm_client_id.as_deref().unwrap_or(&ids.sqm_id);
        if let Ok(key) = hklm.open_subkey_with_flags(
            "SOFTWARE\\Microsoft\\SQMClient",
            KEY_SET_VALUE,
        ) {
            let _ = key.set_value("MachineId", &sqm_value);
        }

        Ok(())
    }

    fn is_admin(&self) -> bool {
        use windows::Win32::Security::{
            GetTokenInformation, TokenElevation, TOKEN_ELEVATION, TOKEN_QUERY,
        };
        use windows::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};

        unsafe {
            let process = GetCurrentProcess();
            let mut token_handle = std::mem::zeroed();
            if OpenProcessToken(process, TOKEN_QUERY, &mut token_handle).is_err() {
                return false;
            }

            let mut elevation = TOKEN_ELEVATION { TokenIsElevated: 0 };
            let mut return_length = 0u32;

            if GetTokenInformation(
                token_handle,
                TokenElevation,
                Some(&mut elevation as *mut _ as *mut _),
                std::mem::size_of::<TOKEN_ELEVATION>() as u32,
                &mut return_length,
            )
            .is_err()
            {
                return false;
            }

            elevation.TokenIsElevated != 0
        }
    }
}
