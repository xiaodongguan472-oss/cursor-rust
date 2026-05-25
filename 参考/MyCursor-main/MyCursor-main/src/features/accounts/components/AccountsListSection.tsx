import { VirtualizedAccountList } from "./VirtualizedAccountList";
import type { AccountInfo, AccountListResult } from "@/types/account";

interface AccountsListSectionProps {
  accountData: AccountListResult | null;
  filteredAccounts: AccountInfo[];
  selectedAccounts: Set<string>;
  subscriptionFilter: string;
  tagFilter: string;
  isAllSelected: boolean;
  shouldUseVirtualScroll: boolean;
  onToggleSelectAll: () => void;
  renderAccountCard: (account: AccountInfo, index: number) => React.ReactNode;
}

export function AccountsListSection({
  accountData,
  filteredAccounts,
  selectedAccounts,
  subscriptionFilter,
  tagFilter,
  isAllSelected,
  shouldUseVirtualScroll,
  onToggleSelectAll,
  renderAccountCard,
}: AccountsListSectionProps) {
  return (
    <div className="px-4 py-4" style={{ overflow: "visible" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <input
            type="checkbox"
            checked={isAllSelected}
            onChange={onToggleSelectAll}
            style={{
              width: "16px",
              height: "16px",
              accentColor: "var(--primary-color)",
              cursor: "pointer",
            }}
          />
          <h4 className="font-medium text-md" style={{ color: "var(--text-primary)" }}>
            账户列表 {selectedAccounts.size > 0 && `(已选 ${selectedAccounts.size})`}
          </h4>
        </div>
        {accountData?.accounts && accountData.accounts.length > 0 && (
          <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {subscriptionFilter === "all" && tagFilter === "all"
              ? `共 ${accountData.accounts.length} 个账户`
              : `显示 ${filteredAccounts.length} / ${accountData.accounts.length} 个账户`}
          </span>
        )}
      </div>

      {accountData?.accounts && accountData.accounts.length > 0 ? (
        shouldUseVirtualScroll ? (
          <VirtualizedAccountList
            accounts={filteredAccounts}
            renderItem={renderAccountCard}
            height={600}
            itemSize={60}
            style={{ borderRadius: "var(--border-radius)" }}
            overscanCount={5}
          />
        ) : (
          <div className="space-y-2" style={{ overflow: "visible" }}>
            {filteredAccounts.map((account, index) => renderAccountCard(account, index))}
          </div>
        )
      ) : (
        <div className="py-12 text-center" style={{ color: "var(--text-secondary)" }}>
          <p>暂无账户，点击"添加账户"开始</p>
        </div>
      )}
    </div>
  );
}
