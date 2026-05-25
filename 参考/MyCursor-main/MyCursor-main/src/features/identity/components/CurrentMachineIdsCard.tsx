import { Card, Icon } from "@/components";
import type { MachineIds } from "@/types/auth";

interface CurrentMachineIdsCardProps {
  currentMachineIds: MachineIds;
  machineIdFileContent: string | null;
}

export function CurrentMachineIdsCard({
  currentMachineIds,
  machineIdFileContent,
}: CurrentMachineIdsCardProps) {
  return (
    <Card>
      <Card.Header>
        <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
          <Icon name="info" size={20} />
          当前 Machine ID
        </h2>
      </Card.Header>
      <Card.Content>
        <div className="space-y-3">
          {Object.entries(currentMachineIds).map(([key, value]) => (
            <div
              key={key}
              className="p-4"
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

        {machineIdFileContent && (
          <div
            className="p-4 mt-4"
            style={{
              backgroundColor: "rgba(74, 137, 220, 0.1)",
              border: "1px solid rgba(74, 137, 220, 0.2)",
              borderRadius: "var(--border-radius)",
            }}
          >
            <p className="mb-2 text-sm font-medium" style={{ color: "var(--primary-color)" }}>
              machineId 文件内容:
            </p>
            <p className="text-xs font-mono break-all" style={{ color: "var(--text-secondary)" }}>
              {machineIdFileContent}
            </p>
          </div>
        )}
      </Card.Content>
    </Card>
  );
}
