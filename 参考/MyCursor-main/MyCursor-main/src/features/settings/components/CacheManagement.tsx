/** 数据管理（清除缓存区域） */
import { Button, Icon } from "@/components";

interface CacheManagementProps {
  onClearUsageData: () => void;
  onClearAccountCache: () => void;
  onClearEventsData: () => void;
}

const CACHE_ITEMS = [
  {
    key: "usage",
    label: "清除所有用量数据",
    warning: "此操作将删除本地保存的所有用量数据，但不影响账户信息",
  },
  {
    key: "account",
    label: "清除所有账户缓存",
    warning: "此操作将删除本地保存的所有账户订阅信息缓存",
  },
  {
    key: "events",
    label: "清除所有事件数据",
    warning: "此操作将删除本地保存的所有事件明细数据",
  },
] as const;

export function CacheManagement({
  onClearUsageData,
  onClearAccountCache,
  onClearEventsData,
}: CacheManagementProps) {
  const handlers: Record<string, () => void> = {
    usage: onClearUsageData,
    account: onClearAccountCache,
    events: onClearEventsData,
  };

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
        <Icon name="trash" size={20} />
        数据管理
      </h3>
      <div className="space-y-4">
        {CACHE_ITEMS.map((item) => (
          <div key={item.key}>
            <Button
              variant="danger"
              onClick={handlers[item.key]}
              icon={<Icon name="trash" size={16} />}
            >
              {item.label}
            </Button>
            <p className="text-xs text-gray-500 mt-2 flex items-start gap-1">
              <Icon name="alert" size={14} color="#ef4444" />
              {item.warning}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
