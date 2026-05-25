import type { AccountInfo } from "@/types/account";

interface SwitchAccountModalProps {
  isOpen: boolean;
  account: AccountInfo | null;
  resetMachineId: boolean;
  machineIdOption: "bound" | "new";
  onClose: () => void;
  onResetMachineIdChange: (value: boolean) => void;
  onMachineIdOptionChange: (value: "bound" | "new") => void;
  onConfirm: () => void;
}

export function SwitchAccountModal({
  isOpen,
  account,
  resetMachineId,
  machineIdOption,
  onClose,
  onResetMachineIdChange,
  onMachineIdOptionChange,
  onConfirm,
}: SwitchAccountModalProps) {
  if (!isOpen || !account) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0" style={{ backgroundColor: "rgba(0,0,0,0.5)" }} onClick={onClose} />
      <div
        className="relative z-10 w-[400px] rounded-lg p-6"
        style={{ backgroundColor: "var(--bg-primary)", boxShadow: "var(--shadow-heavy)" }}
      >
        <h3 className="text-lg font-semibold mb-4" style={{ color: "var(--text-primary)" }}>
          切换账号
        </h3>
        <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
          确定要使用账号 <strong>{account.email}</strong> 吗？
          <br />
          此操作可能会重启 Cursor！
        </p>

        <label className="flex items-center gap-2 mb-3 cursor-pointer">
          <input
            type="checkbox"
            checked={resetMachineId}
            onChange={(e) => onResetMachineIdChange(e.target.checked)}
            style={{ accentColor: "var(--primary-color)" }}
          />
          <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
            重置机器码（推荐）
          </span>
        </label>

        {resetMachineId && (
          <div className="ml-6 space-y-2 mb-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="machineIdOption"
                checked={machineIdOption === "bound"}
                onChange={() => onMachineIdOptionChange("bound")}
                style={{ accentColor: "var(--primary-color)" }}
              />
              <span
                className="text-sm"
                style={{ color: account.machine_ids ? "var(--text-primary)" : "var(--text-tertiary)" }}
              >
                使用该账号已绑定的机器码
                {!account.machine_ids && <span className="text-xs ml-1">(无绑定)</span>}
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="machineIdOption"
                checked={machineIdOption === "new"}
                onChange={() => onMachineIdOptionChange("new")}
                style={{ accentColor: "var(--primary-color)" }}
              />
              <span className="text-sm" style={{ color: "var(--text-primary)" }}>
                随机新的机器码并绑定到账号
              </span>
            </label>
          </div>
        )}

        <div className="flex justify-end gap-3 mt-4 pt-4" style={{ borderTop: "1px solid var(--border-primary)" }}>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded"
            style={{
              backgroundColor: "var(--bg-secondary)",
              color: "var(--text-primary)",
              border: "1px solid var(--border-primary)",
            }}
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm rounded font-medium"
            style={{ backgroundColor: "var(--primary-color)", color: "white", border: "none" }}
          >
            确定
          </button>
        </div>
      </div>
    </div>
  );
}
