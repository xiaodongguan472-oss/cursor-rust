/** 注入管理卡片（端口设置 + 注入/恢复按钮） */
import { Button, Card, Input, Icon } from "@/components";
import type { SeamlessStatus } from "@/types/account";

interface InjectionControlProps {
  status: SeamlessStatus | null;
  port: number;
  actionLoading: string | null;
  onPortChange: (port: number) => void;
  onInject: () => void;
  onRestore: () => void;
}

export function InjectionControl({
  status,
  port,
  actionLoading,
  onPortChange,
  onInject,
  onRestore,
}: InjectionControlProps) {
  return (
    <Card>
      <Card.Header>
        <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
          <Icon name="plug" size={20} />
          注入管理
        </h2>
      </Card.Header>
      <Card.Content>
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
              服务端口:
            </label>
            <Input
              type="number"
              value={port.toString()}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10);
                if (!isNaN(v) && v > 0 && v < 65536) onPortChange(v);
              }}
              className="w-32"
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Button
              variant="primary"
              onClick={onInject}
              loading={actionLoading === "inject"}
              disabled={!!actionLoading}
              className="h-16 flex-col"
              icon={<Icon name="bolt" size={20} />}
            >
              {status?.injected ? "重新注入" : "注入无感换号"}
            </Button>
            <Button
              variant="danger"
              onClick={onRestore}
              loading={actionLoading === "restore"}
              disabled={!!actionLoading || !status?.backup_exists}
              className="h-16 flex-col"
              icon={<Icon name="refresh" size={20} />}
            >
              恢复原始文件
            </Button>
          </div>
        </div>
      </Card.Content>
    </Card>
  );
}
