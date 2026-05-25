/** 操作结果展示卡片 */
import { Card, Icon } from "@/components";
import type { SeamlessResult } from "@/types/account";

interface ResultCardProps {
  result: SeamlessResult;
}

export function ResultCard({ result }: ResultCardProps) {
  const isSuccess = result.success;

  return (
    <Card>
      <Card.Header>
        <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
          <Icon name="info" size={20} />
          操作结果
        </h2>
      </Card.Header>
      <Card.Content>
        <div
          className="p-4 rounded-lg"
          style={{
            backgroundColor: isSuccess ? "rgba(78, 201, 176, 0.1)" : "rgba(244, 135, 113, 0.1)",
            border: `1px solid ${isSuccess ? "rgba(78, 201, 176, 0.3)" : "rgba(244, 135, 113, 0.3)"}`,
          }}
        >
          <p className="font-medium text-sm mb-2" style={{ color: isSuccess ? "#4ec9b0" : "#f48771" }}>
            {isSuccess ? "成功" : "失败"}：{result.message}
          </p>
          {result.details && result.details.length > 0 && (
            <ul className="space-y-1">
              {result.details.map((d, i) => (
                <li key={i} className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>
                  {d}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card.Content>
    </Card>
  );
}
