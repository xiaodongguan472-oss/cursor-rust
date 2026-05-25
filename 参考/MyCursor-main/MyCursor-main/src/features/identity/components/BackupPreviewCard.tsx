import { Button, Card } from "@/components";
import type { BackupInfo, MachineIds } from "@/types/auth";

interface BackupPreviewCardProps {
  backup: BackupInfo;
  machineIds: MachineIds;
  loading: boolean;
  onConfirm: () => void;
  onBack: () => void;
}

export function BackupPreviewCard({
  backup,
  machineIds,
  loading,
  onConfirm,
  onBack,
}: BackupPreviewCardProps) {
  return (
    <Card>
      <Card.Header>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            预览备份内容
          </h2>
          <Button variant="ghost" size="sm" onClick={onBack}>
            返回
          </Button>
        </div>
      </Card.Header>
      <Card.Content className="space-y-6">
        <div
          className="p-4"
          style={{
            backgroundColor: "rgba(74, 137, 220, 0.1)",
            border: "1px solid rgba(74, 137, 220, 0.2)",
            borderRadius: "var(--border-radius)",
          }}
        >
          <h3 className="mb-2 font-medium" style={{ color: "var(--primary-color)" }}>
            备份信息
          </h3>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            日期: {backup.date_formatted}
          </p>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            大小: {backup.size} bytes
          </p>
        </div>

        <div className="space-y-3">
          <h3 className="font-medium" style={{ color: "var(--text-primary)" }}>
            将要恢复的 Machine ID:
          </h3>
          {Object.entries(machineIds).map(([key, value]) => (
            <div
              key={key}
              className="p-3"
              style={{
                backgroundColor: "var(--bg-secondary)",
                borderRadius: "var(--border-radius)",
              }}
            >
              <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                {key}
              </p>
              <p className="mt-1 text-xs font-mono break-all" style={{ color: "var(--text-secondary)" }}>
                {value}
              </p>
            </div>
          ))}
        </div>
      </Card.Content>
      <Card.Footer>
        <div className="flex gap-3">
          <Button variant="primary" onClick={onConfirm} loading={loading}>
            确认恢复
          </Button>
          <Button variant="ghost" onClick={onBack}>
            取消
          </Button>
        </div>
      </Card.Footer>
    </Card>
  );
}
