import React, { useMemo, useCallback, useRef, useEffect } from "react";
import { FixedSizeList, ListChildComponentProps } from "react-window";
import type { AccountInfo } from "@/types/account";

interface VirtualizedAccountListProps {
  accounts: AccountInfo[];
  renderItem: (account: AccountInfo, index: number) => React.ReactNode;
  height?: number;
  itemSize?: number;
  className?: string;
  style?: React.CSSProperties;
  overscanCount?: number;
  onScroll?: (scrollOffset: number) => void;
}

const DEFAULT_HEIGHT = 600;
const DEFAULT_ITEM_SIZE = 60;
const DEFAULT_OVERSCAN = 5;

export const VirtualizedAccountList: React.FC<VirtualizedAccountListProps> = ({
  accounts,
  renderItem,
  height = DEFAULT_HEIGHT,
  itemSize = DEFAULT_ITEM_SIZE,
  className = "",
  style = {},
  overscanCount = DEFAULT_OVERSCAN,
  onScroll,
}) => {
  const listRef = useRef<FixedSizeList>(null);

  const itemCount = useMemo(() => accounts.length, [accounts.length]);

  const containerHeight = useMemo(() => {
    const maxHeight = typeof window !== "undefined" ? window.innerHeight * 0.7 : height;
    const contentHeight = itemCount * itemSize;
    return Math.min(contentHeight, maxHeight, height);
  }, [itemCount, itemSize, height]);

  const Row = useCallback(
    ({ index, style: rowStyle }: ListChildComponentProps) => {
      const account = accounts[index];

      if (!account) {
        return null;
      }

      const adjustedStyle: React.CSSProperties = {
        ...rowStyle,
        paddingBottom: "8px",
      };

      return <div style={adjustedStyle}>{renderItem(account, index)}</div>;
    },
    [accounts, renderItem]
  );

  const handleScroll = useCallback(
    ({ scrollOffset }: { scrollOffset: number }) => {
      if (onScroll) {
        onScroll(scrollOffset);
      }
    },
    [onScroll]
  );

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTo(0);
    }
  }, [accounts.length]);

  return (
    <div className={className} style={style}>
      <FixedSizeList
        ref={listRef}
        height={containerHeight}
        itemCount={itemCount}
        itemSize={itemSize}
        width="100%"
        overscanCount={overscanCount}
        onScroll={handleScroll}
        style={{
          scrollbarWidth: "thin",
          scrollbarColor: "var(--border-primary) transparent",
        }}
      >
        {Row}
      </FixedSizeList>
    </div>
  );
};
