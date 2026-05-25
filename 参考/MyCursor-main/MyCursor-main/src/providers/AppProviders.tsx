import { ReactNode } from "react";
import { QueryProvider } from "./QueryProvider";
import { ThemeProvider } from "../context/ThemeContext";
import ErrorBoundary from "../components/ErrorBoundary";

/**
 * 组合所有全局 Provider
 *
 * 包装顺序：ErrorBoundary → ThemeProvider → QueryProvider
 */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <QueryProvider>{children}</QueryProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
