/** HTTP 服务器控制卡片（启动/停止按钮） */
import { Button, Card, Icon } from "@/components";
import type { SeamlessStatus } from "@/types/account";

interface ServerControlProps {
  status: SeamlessStatus | null;
  actionLoading: string | null;
  onStart: () => void;
  onStop: () => void;
}

export function ServerControl({ status, actionLoading, onStart, onStop }: ServerControlProps) {
  return (
    <Card>
      <Card.Header>
        <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
          <Icon name="settings" size={20} />
          HTTP 服务器
        </h2>
      </Card.Header>
      <Card.Content>
        <div className="space-y-4">
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            使用 Cursor 期间需保持服务器运行，为注入的代码提供账号数据。
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Button
              variant="info"
              onClick={onStart}
              loading={actionLoading === "start"}
              disabled={!!actionLoading || (status?.server_running ?? false)}
              className="h-14"
              icon={<Icon name="login" size={20} />}
            >
              启动服务器
            </Button>
            <Button
              variant="danger"
              onClick={onStop}
              loading={actionLoading === "stop"}
              disabled={!!actionLoading || !(status?.server_running ?? false)}
              className="h-14"
              icon={<Icon name="logout" size={20} />}
            >
              停止服务器
            </Button>
          </div>
        </div>
      </Card.Content>
    </Card>
  );
}
