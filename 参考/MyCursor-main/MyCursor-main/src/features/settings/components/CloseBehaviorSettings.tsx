/** 关闭行为设置 */
import { Button, Icon } from "@/components";

interface CloseBehaviorSettingsProps {
  minimizeToTray: boolean;
  onSetBehavior: (minimize: boolean) => void;
}

export function CloseBehaviorSettings({ minimizeToTray, onSetBehavior }: CloseBehaviorSettingsProps) {
  return (
    <div>
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
        <Icon name="window" size={20} />
        关闭行为
      </h3>
      <div className="flex gap-3">
        <Button
          variant={minimizeToTray ? "primary" : "ghost"}
          onClick={() => onSetBehavior(true)}
          icon={<Icon name="minimize" size={16} />}
        >
          最小化到托盘
        </Button>
        <Button
          variant={!minimizeToTray ? "primary" : "ghost"}
          onClick={() => onSetBehavior(false)}
          icon={<Icon name="power" size={16} />}
        >
          直接退出
        </Button>
      </div>
      <p className="text-xs mt-2" style={{ color: "var(--text-tertiary)" }}>
        设置点击窗口关闭按钮时的行为
      </p>
    </div>
  );
}
