import React from "react";
import { Card, Button } from "@/components";
import type { RestoreResult, ResetResult } from "@/types/auth";

interface ResultDisplayProps {
  result: RestoreResult | ResetResult | null;
  type: "restore" | "reset" | "complete_reset";
  onBack: () => void;
  onRefresh: () => void;
}

export const ResultDisplay: React.FC<ResultDisplayProps> = ({
  result,
  type,
  onBack,
  onRefresh,
}) => {
  if (!result) {
    return null;
  }

  const isReset = type === "reset" || type === "complete_reset";
  const title = type === "complete_reset" ? "完全重置" : type === "reset" ? "重置" : "恢复";

  return (
    <Card>
      <Card.Content className="space-y-6">
        <div className="text-center">
          <div className="text-5xl mb-4">{result.success ? "✅" : "❌"}</div>
          <h2 className="mb-2 text-lg font-medium" style={{ color: "var(--text-primary)" }}>
            {title}
            {result.success ? "成功" : "失败"}
          </h2>
          <p style={{ color: "var(--text-secondary)" }}>{result.message}</p>
        </div>

        {isReset && "new_ids" in result && result.new_ids && (
          <div>
            <h3 className="mb-2 font-medium" style={{ color: "var(--text-primary)" }}>
              新的 Machine ID:
            </h3>
            <div className="space-y-2">
              {Object.entries(result.new_ids).map(([key, value]) => (
                <div
                  key={key}
                  className="p-3 rounded"
                  style={{
                    backgroundColor: "rgba(16, 185, 129, 0.1)",
                    border: "1px solid rgba(16, 185, 129, 0.2)",
                  }}
                >
                  <p className="text-sm font-medium" style={{ color: "#10b981" }}>
                    {key}
                  </p>
                  <p className="mt-1 text-xs font-mono break-all" style={{ color: "var(--text-secondary)" }}>
                    {value}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {result.details && result.details.length > 0 && (
          <div>
            <h3 className="mb-2 font-medium" style={{ color: "var(--text-primary)" }}>
              详细信息:
            </h3>
            <div className="space-y-1">
              {result.details.map((detail, index) => (
                <p
                  key={index}
                  className="p-2 text-sm rounded"
                  style={{
                    color: "var(--text-secondary)",
                    backgroundColor: "var(--bg-secondary)",
                  }}
                >
                  {detail}
                </p>
              ))}
            </div>
          </div>
        )}
      </Card.Content>
      <Card.Footer>
        <div className="flex justify-center gap-3">
          <Button variant="primary" onClick={onBack}>
            返回主菜单
          </Button>
          <Button variant="ghost" onClick={onRefresh}>
            刷新当前 ID
          </Button>
        </div>
      </Card.Footer>
    </Card>
  );
};
