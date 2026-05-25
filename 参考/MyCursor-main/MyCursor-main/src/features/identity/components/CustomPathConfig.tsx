import React from "react";
import { Card, Button, Input, Alert, Icon } from "@/components";

interface CustomPathConfigProps {
  customCursorPath: string;
  currentCustomPath: string | null;
  onPathChange: (path: string) => void;
  onSetPath: () => void;
  onFillDetectedPath: () => void;
  onClearPath: () => void;
  onBrowsePath: () => void;
  onBack: () => void;
}

export const CustomPathConfig: React.FC<CustomPathConfigProps> = ({
  customCursorPath,
  currentCustomPath,
  onPathChange,
  onSetPath,
  onFillDetectedPath,
  onClearPath,
  onBrowsePath,
  onBack,
}) => {
  return (
    <Card>
      <Card.Header>
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold">自定义 Cursor 路径配置</h2>
          <Button variant="ghost" onClick={onBack} size="sm">
            ← 返回主菜单
          </Button>
        </div>
      </Card.Header>
      <Card.Content className="space-y-6">
        <Alert type="info">
          <p className="text-sm">
            如果自动检测无法找到 Cursor 安装路径，你可以手动指定。
            <br />
            路径应该指向 Cursor 的{" "}
            <code
              className="px-1"
              style={{
                backgroundColor: "rgba(74, 137, 220, 0.15)",
                borderRadius: "var(--border-radius-small)",
              }}
            >
              resources/app
            </code>{" "}
            目录。
            <br />
            例如:{" "}
            <code
              className="px-1"
              style={{
                backgroundColor: "rgba(74, 137, 220, 0.15)",
                borderRadius: "var(--border-radius-small)",
              }}
            >
              C:\Users\用户名\AppData\Local\Programs\Cursor\resources\app
            </code>
          </p>
        </Alert>

        <div
          className="p-4"
          style={{
            backgroundColor: "var(--bg-secondary)",
            borderRadius: "var(--border-radius)",
          }}
        >
          <h3 className="mb-2 font-medium flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
            <Icon name="info" size={18} />
            当前状态
          </h3>
          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {currentCustomPath ? (
              <div>
                <span className="font-medium">已设置自定义路径:</span>
                <br />
                <span
                  className="px-1 text-xs font-mono"
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    borderRadius: "var(--border-radius-small)",
                  }}
                >
                  {currentCustomPath}
                </span>
              </div>
            ) : (
              <span>未设置自定义路径，使用自动检测</span>
            )}
          </div>
        </div>

        <div className="space-y-3">
          <h3 className="font-medium flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
            <Icon name="settings" size={18} />
            设置自定义路径
          </h3>
          <div className="flex gap-2">
            <div className="flex-1">
              <Input
                value={customCursorPath}
                onChange={(e) => onPathChange(e.target.value)}
                placeholder="点击'浏览选择'按钮或手动输入完整路径"
              />
            </div>
            <Button variant="info" onClick={onBrowsePath} icon={<Icon name="download" size={16} />}>
              浏览选择
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={onSetPath} icon={<Icon name="check" size={16} />}>
              保存路径
            </Button>

            <Button variant="ghost" onClick={onFillDetectedPath} icon={<Icon name="search" size={16} />}>
              自动检测并填充
            </Button>

            <Button variant="danger" onClick={onClearPath} icon={<Icon name="trash" size={16} />}>
              清除自定义路径
            </Button>
          </div>
        </div>
      </Card.Content>
    </Card>
  );
};
