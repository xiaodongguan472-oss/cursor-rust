/** 无感换号状态总览卡片 */
import { Card, Icon } from "@/components";
import type { SeamlessStatus } from "@/types/account";
import { StatusBadge } from "./StatusBadge";

interface StatusCardProps {
  status: SeamlessStatus | null;
  port: number;
}

export function StatusCard({ status, port }: StatusCardProps) {
  return (
    <Card>
      <Card.Header>
        <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
          <Icon name="info" size={20} />
          当前状态
        </h2>
      </Card.Header>
      <Card.Content>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatusBadge label="注入状态" active={status?.injected ?? false} activeText="已注入" inactiveText="未注入" />
          <StatusBadge label="HTTP 服务器" active={status?.server_running ?? false} activeText={`运行中 (:${status?.port ?? port})`} inactiveText="已停止" />
          <StatusBadge label="原始备份" active={status?.backup_exists ?? false} activeText="已备份" inactiveText="无" />
          <div className="p-3 rounded-lg" style={{ backgroundColor: "var(--bg-secondary)" }}>
            <p className="text-xs font-medium mb-1" style={{ color: "var(--text-tertiary)" }}>端口</p>
            <p className="text-sm font-mono font-semibold" style={{ color: "var(--text-primary)" }}>{port}</p>
          </div>
        </div>
      </Card.Content>
    </Card>
  );
}
