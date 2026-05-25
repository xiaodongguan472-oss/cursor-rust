/** 使用说明卡片 */
import { Card, Icon } from "@/components";

const STEPS = [
  "注入前请先完全关闭 Cursor。",
  "设置端口，点击「注入无感换号」。",
  "点击「启动服务器」开启 HTTP 账号服务。",
  "打开 Cursor 正常使用。",
  "需要换号时，点击右下角 ⚡ 按钮，弹出账号选择（可按类型/标签筛选）。",
  "选择账号后无感切换，重新发送即可。",
  "使用期间保持 MyCursor 在后台运行。",
  "Cursor 更新后需重新注入。",
];

export function UsageGuide() {
  return (
    <Card>
      <Card.Header>
        <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
          <Icon name="info" size={20} />
          使用说明
        </h2>
      </Card.Header>
      <Card.Content>
        <div className="space-y-3">
          {STEPS.map((step, i) => (
            <div key={i} className="flex items-start gap-3">
              <span
                className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                style={{ backgroundColor: "var(--primary-color)", color: "white" }}
              >
                {i + 1}
              </span>
              <p className="text-sm pt-0.5" style={{ color: "var(--text-secondary)" }}>
                {step}
              </p>
            </div>
          ))}
        </div>
      </Card.Content>
    </Card>
  );
}
