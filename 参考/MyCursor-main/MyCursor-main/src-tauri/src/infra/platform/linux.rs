/// Linux 平台特定实现
use crate::domain::identity::MachineIds;
use crate::error::AppError;
use super::PlatformOps;

pub struct LinuxOps;

impl PlatformOps for LinuxOps {
    fn update_system_ids(&self, _ids: &MachineIds) -> Result<(), AppError> {
        Ok(())
    }

    fn is_admin(&self) -> bool {
        true
    }
}
