import { Component, ReactNode, ErrorInfo } from "react";
import { logger } from "../utils/logger";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    logger.error("应用错误边界捕获到错误", { error, errorInfo });
    this.setState({ error, errorInfo });
  }

  handleReset = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen bg-gradient-to-br from-bgStart to-bgEnd flex items-center justify-center p-6">
          <div className="bg-white rounded-xl shadow-card max-w-2xl w-full p-8">
            <div className="flex items-center mb-6">
              <div className="w-12 h-12 bg-danger-500 rounded-full flex items-center justify-center mr-4">
                <span className="text-2xl text-white">⚠️</span>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  应用发生错误
                </h1>
                <p className="text-sm text-gray-600">Something went wrong</p>
              </div>
            </div>

            <div className="mb-6">
              <p className="text-gray-700 mb-4">
                应用遇到了意外错误。您可以尝试重新加载页面，如果问题持续存在，请联系技术支持。
              </p>

              {import.meta.env.DEV && this.state.error && (
                <details className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <summary className="cursor-pointer font-medium text-gray-700 mb-2">
                    错误详情（仅开发环境可见）
                  </summary>
                  <div className="mt-2 space-y-2">
                    <div>
                      <p className="text-xs font-semibold text-gray-600">
                        错误信息:
                      </p>
                      <pre className="text-xs text-red-600 mt-1 whitespace-pre-wrap">
                        {this.state.error.toString()}
                      </pre>
                    </div>
                    {this.state.errorInfo && (
                      <div>
                        <p className="text-xs font-semibold text-gray-600">
                          堆栈跟踪:
                        </p>
                        <pre className="text-xs text-gray-700 mt-1 overflow-auto max-h-60">
                          {this.state.errorInfo.componentStack}
                        </pre>
                      </div>
                    )}
                  </div>
                </details>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={this.handleReset}
                className="px-6 py-2 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-lg font-medium hover:shadow-btn-orange transition-all duration-300"
              >
                重试
              </button>
              <button
                onClick={() => window.location.reload()}
                className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition-all duration-300"
              >
                重新加载页面
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
