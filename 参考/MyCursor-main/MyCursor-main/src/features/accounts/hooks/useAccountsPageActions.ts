import type { AccountsPageActionsContext } from "./accountsPageActionTypes.ts";
import { useAccountsPageBatchActions } from "./useAccountsPageBatchActions.ts";
import { useAccountsPageCrudActions } from "./useAccountsPageCrudActions.ts";
import { useAccountsPageImportExportActions } from "./useAccountsPageImportExportActions.ts";
import { useAccountsPageSessionActions } from "./useAccountsPageSessionActions.ts";

export function useAccountsPageActions(context: AccountsPageActionsContext) {
  const crudActions = useAccountsPageCrudActions(context);
  const sessionActions = useAccountsPageSessionActions(context);
  const importExportActions = useAccountsPageImportExportActions(context);
  const batchActions = useAccountsPageBatchActions(context);

  return {
    ...crudActions,
    ...sessionActions,
    ...importExportActions,
    ...batchActions,
  };
}
