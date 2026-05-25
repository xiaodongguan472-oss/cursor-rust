/** 数据说明卡片 */
import { Card, Icon } from "@/components";

const INFO_ITEMS = [
  { text: "本地存储:", detail: "所有数据保存在程序同级 cursor_data 目录中" },
  { text: "自动保存:", detail: "用量数据和日期选择会自动保存到本地" },
  { text: "离线访问:", detail: "无需联网即可查看已保存的用量数据" },
  { text: "手动刷新:", detail: "只有点击\"刷新\"按钮时才会获取最新数据" },
];

export function DataInfo() {
  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
        <Icon name="info" size={20} />
        数据说明
      </h3>
      <div className="space-y-3 text-sm" style={{ color: "var(--text-secondary)" }}>
        {INFO_ITEMS.map((item, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className="text-green-500 mt-0.5">✓</span>
            <p><strong>{item.text}</strong> {item.detail}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}
