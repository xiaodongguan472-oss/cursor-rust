/**
 * 节流和防抖工具
 * 用于优化高频事件处理，减少不必要的函数调用
 */

/**
 * 防抖函数
 * 在事件触发后延迟执行，如果在延迟期间再次触发，则重新计时
 * 
 * @param func 要执行的函数
 * @param wait 延迟时间（毫秒）
 * @param immediate 是否立即执行第一次
 * @returns 防抖后的函数
 * 
 * @example
 * const debouncedSearch = debounce((query) => {
 *   searchAPI(query);
 * }, 300);
 * 
 * input.addEventListener('input', (e) => debouncedSearch(e.target.value));
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number = 300,
  immediate: boolean = false
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null;

  return function (this: any, ...args: Parameters<T>) {
    const context = this;

    const later = () => {
      timeout = null;
      if (!immediate) {
        func.apply(context, args);
      }
    };

    const callNow = immediate && !timeout;

    if (timeout) {
      clearTimeout(timeout);
    }

    timeout = setTimeout(later, wait);

    if (callNow) {
      func.apply(context, args);
    }
  };
}

/**
 * 节流函数
 * 限制函数在指定时间内只执行一次
 * 
 * @param func 要执行的函数
 * @param limit 时间限制（毫秒）
 * @param options 选项
 * @returns 节流后的函数
 * 
 * @example
 * const throttledScroll = throttle(() => {
 *   console.log('Scroll event');
 * }, 100);
 * 
 * window.addEventListener('scroll', throttledScroll);
 */
export function throttle<T extends (...args: any[]) => any>(
  func: T,
  limit: number = 300,
  options: {
    leading?: boolean;  // 是否在开始时立即执行
    trailing?: boolean; // 是否在结束时执行
  } = {}
): (...args: Parameters<T>) => void {
  const { leading = true, trailing = true } = options;
  
  let timeout: ReturnType<typeof setTimeout> | null = null;
  let previous = 0;
  let lastArgs: Parameters<T> | null = null;

  return function (this: any, ...args: Parameters<T>) {
    const now = Date.now();
    const context = this;

    // 第一次不执行
    if (!previous && !leading) {
      previous = now;
    }

    const remaining = limit - (now - previous);
    lastArgs = args;

    if (remaining <= 0 || remaining > limit) {
      if (timeout) {
        clearTimeout(timeout);
        timeout = null;
      }

      previous = now;
      func.apply(context, args);
      lastArgs = null;
    } else if (!timeout && trailing) {
      timeout = setTimeout(() => {
        previous = leading ? Date.now() : 0;
        timeout = null;
        if (lastArgs) {
          func.apply(context, lastArgs);
          lastArgs = null;
        }
      }, remaining);
    }
  };
}

/**
 * 请求动画帧节流
 * 使用 requestAnimationFrame 优化动画和滚动事件
 * 
 * @param func 要执行的函数
 * @returns RAF 节流后的函数
 * 
 * @example
 * const rafThrottled = rafThrottle(() => {
 *   // 更新 UI
 * });
 * 
 * window.addEventListener('scroll', rafThrottled);
 */
export function rafThrottle<T extends (...args: any[]) => any>(
  func: T
): (...args: Parameters<T>) => void {
  let rafId: number | null = null;
  let lastArgs: Parameters<T> | null = null;

  return function (this: any, ...args: Parameters<T>) {
    const context = this;
    lastArgs = args;

    if (rafId === null) {
      rafId = requestAnimationFrame(() => {
        if (lastArgs) {
          func.apply(context, lastArgs);
          lastArgs = null;
        }
        rafId = null;
      });
    }
  };
}

/**
 * 异步防抖
 * 适用于异步操作的防抖
 * 
 * @param func 异步函数
 * @param wait 延迟时间（毫秒）
 * @returns 防抖后的异步函数
 * 
 * @example
 * const debouncedFetch = asyncDebounce(async (url) => {
 *   const response = await fetch(url);
 *   return response.json();
 * }, 500);
 */
export function asyncDebounce<T extends (...args: any[]) => Promise<any>>(
  func: T,
  wait: number = 300
): (...args: Parameters<T>) => Promise<ReturnType<T>> {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  let latestResolve: ((value: any) => void) | null = null;
  let latestReject: ((reason: any) => void) | null = null;

  return function (this: any, ...args: Parameters<T>): Promise<ReturnType<T>> {
    const context = this;

    return new Promise<ReturnType<T>>((resolve, reject) => {
      if (timeout) {
        clearTimeout(timeout);
      }

      // 保存最新的 resolve/reject
      latestResolve = resolve;
      latestReject = reject;

      timeout = setTimeout(async () => {
        try {
          const result = await func.apply(context, args);
          if (latestResolve) {
            latestResolve(result);
          }
        } catch (error) {
          if (latestReject) {
            latestReject(error);
          }
        }
      }, wait);
    });
  };
}

/**
 * 取消防抖/节流
 * 为防抖和节流函数添加 cancel 方法
 */
export interface CancellableFunction<T extends (...args: any[]) => any> {
  (...args: Parameters<T>): ReturnType<T>;
  cancel: () => void;
}

/**
 * 创建可取消的防抖函数
 */
export function cancellableDebounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number = 300
): CancellableFunction<T> {
  let timeout: ReturnType<typeof setTimeout> | null = null;

  const debouncedFunc = function (this: any, ...args: Parameters<T>) {
    const context = this;

    if (timeout) {
      clearTimeout(timeout);
    }

    timeout = setTimeout(() => {
      func.apply(context, args);
    }, wait);
  } as CancellableFunction<T>;

  debouncedFunc.cancel = () => {
    if (timeout) {
      clearTimeout(timeout);
      timeout = null;
    }
  };

  return debouncedFunc;
}

/**
 * 创建可取消的节流函数
 */
export function cancellableThrottle<T extends (...args: any[]) => any>(
  func: T,
  limit: number = 300
): CancellableFunction<T> {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  let previous = 0;

  const throttledFunc = function (this: any, ...args: Parameters<T>) {
    const now = Date.now();
    const context = this;
    const remaining = limit - (now - previous);

    if (remaining <= 0 || remaining > limit) {
      if (timeout) {
        clearTimeout(timeout);
        timeout = null;
      }
      previous = now;
      func.apply(context, args);
    } else if (!timeout) {
      timeout = setTimeout(() => {
        previous = Date.now();
        timeout = null;
        func.apply(context, args);
      }, remaining);
    }
  } as CancellableFunction<T>;

  throttledFunc.cancel = () => {
    if (timeout) {
      clearTimeout(timeout);
      timeout = null;
    }
    previous = 0;
  };

  return throttledFunc;
}

/**
 * React Hook: 使用防抖
 */
export function useDebouncedCallback<T extends (...args: any[]) => any>(
  callback: T,
  delay: number = 300
): T {
  // 注意：这个函数需要配合 React.useCallback 使用
  // 实际使用时应该在组件中配合 useCallback 和 useRef
  return debounce(callback, delay) as T;
}

/**
 * React Hook: 使用节流
 */
export function useThrottledCallback<T extends (...args: any[]) => any>(
  callback: T,
  limit: number = 300
): T {
  // 注意：这个函数需要配合 React.useCallback 使用
  return throttle(callback, limit) as T;
}
