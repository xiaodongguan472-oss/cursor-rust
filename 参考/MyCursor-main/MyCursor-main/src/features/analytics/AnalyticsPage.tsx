import { Card, Button, Icon, UsageDisplay } from "@/components";
import { useAnalyticsPageState } from "./hooks/useAnalyticsPageState";
import { useAnalyticsPageActions } from "./hooks/useAnalyticsPageActions";
import { useAnalyticsPageEffects } from "./hooks/useAnalyticsPageEffects";

const AnalyticsPage = () => {
  const {
    token,
    setToken,
    currentAccount,
    setCurrentAccount,
    setLoading,
  } = useAnalyticsPageState();

  const { loadCurrentAccount } = useAnalyticsPageActions({
    setToken,
    setCurrentAccount,
    setLoading,
  });

  useAnalyticsPageEffects({ loadCurrentAccount });

  return (
    <div className="space-y-6">
      {token ? (
        <UsageDisplay
          token={token}
          email={currentAccount?.email}
          className="animate-fadeIn"
        />
      ) : (
        <Card className="p-12 text-center">
          <div className="mb-4 flex justify-center">
            <Icon name="chart" size={64} color="var(--text-secondary)" />
          </div>
          <h3 className="text-xl font-bold mb-2" style={{ color: "var(--text-primary)" }}>
            暂无数据
          </h3>
          <p className="mb-4" style={{ color: "var(--text-secondary)" }}>
            请先在账号管理页面登录账户
          </p>
          <Button variant="primary" onClick={loadCurrentAccount}>
            加载当前账户
          </Button>
        </Card>
      )}
    </div>
  );
};

export default AnalyticsPage;
