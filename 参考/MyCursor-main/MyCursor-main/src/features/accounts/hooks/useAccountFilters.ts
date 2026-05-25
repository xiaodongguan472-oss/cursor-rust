/** 账号筛选与多选 hook */
import { useState, useMemo, useCallback } from "react";

interface AccountLike {
  email: string;
  subscription_type?: string | null;
  tags?: string[];
}

/** 账号筛选 hook（按订阅类型、标签、搜索关键词过滤） */
export function useAccountFilters<T extends AccountLike>(accounts: T[]) {
  const [search, setSearch] = useState("");
  const [planFilter, setPlanFilter] = useState<string>("all");
  const [tagFilter, setTagFilter] = useState<string>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    return accounts
      .filter((a) =>
        planFilter === "all" || a.subscription_type === planFilter
      )
      .filter((a) =>
        tagFilter === "all" ||
        (tagFilter === "__untagged__" && (!a.tags || a.tags.length === 0)) ||
        (a.tags && a.tags.includes(tagFilter))
      )
      .filter((a) =>
        !search || a.email.toLowerCase().includes(search.toLowerCase())
      );
  }, [accounts, planFilter, tagFilter, search]);

  const planOptions = useMemo(() => {
    const plans = new Set(accounts.map((a) => a.subscription_type || "unknown"));
    return Array.from(plans);
  }, [accounts]);

  const tagOptions = useMemo(() => {
    const tags = new Set(accounts.flatMap((a) => a.tags || []));
    return Array.from(tags);
  }, [accounts]);

  const toggleSelect = useCallback((email: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(email)) next.delete(email);
      else next.add(email);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelected((prev) => {
      if (prev.size === filtered.length) return new Set();
      return new Set(filtered.map((a) => a.email));
    });
  }, [filtered]);

  return {
    search, setSearch,
    planFilter, setPlanFilter,
    tagFilter, setTagFilter,
    selected, toggleSelect, toggleSelectAll,
    filtered,
    planOptions, tagOptions,
  };
}
