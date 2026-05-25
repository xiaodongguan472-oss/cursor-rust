import { Icon, UsageDisplay } from "@/components";
import type { AccountInfo } from "@/types/account";

interface AccountUsageModalProps {
  isOpen: boolean;
  account: AccountInfo | null;
  onClose: () => void;
}

export function AccountUsageModal({ isOpen, account, onClose }: AccountUsageModalProps) {
  if (!isOpen || !account) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4">
        <div
          className="fixed inset-0 transition-opacity"
          style={{ backgroundColor: "rgba(0, 0, 0, 0.5)" }}
          onClick={onClose}
        />
        <div
          className="relative z-10 w-[95%] max-w-[750px] max-h-[90vh] overflow-hidden"
          style={{
            backgroundColor: "var(--bg-primary)",
            boxShadow: "var(--shadow-heavy)",
            backdropFilter: "blur(var(--backdrop-blur))",
            WebkitBackdropFilter: "blur(var(--backdrop-blur))",
            borderRadius: "var(--border-radius-large)",
          }}
        >
          <div className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-medium" style={{ color: "var(--text-primary)" }}>
                用量统计 - {account.email}
              </h3>
              <button
                onClick={onClose}
                style={{
                  color: "var(--text-secondary)",
                  transition: "color var(--transition-duration) ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "var(--text-primary)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "var(--text-secondary)";
                }}
              >
                <Icon name="close" size={20} />
              </button>
            </div>

            <div className="overflow-y-auto max-h-[calc(90vh-120px)]">
              <UsageDisplay token={account.token} email={account.email} className="mt-4" hideHeader={true} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
