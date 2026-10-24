import { useEffect, useState } from "react";

type State<T> =
  | { status: "loading" }
  | { status: "error" }
  | { status: "success"; data: T };

// The resource is tied to a route key. No previous report can flash on a new route.
export function useResource<T>(
  key: string,
  load: (signal: AbortSignal) => Promise<T>,
) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{
    key: string;
    attempt: number;
    state: State<T>;
  }>();
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted)
          setResult({ key, attempt, state: { status: "success", data } });
      },
      () => {
        if (!controller.signal.aborted)
          setResult({ key, attempt, state: { status: "error" } });
      },
    );
    return () => controller.abort();
  }, [key, attempt, load]);
  const state: State<T> =
    result?.key === key && result.attempt === attempt
      ? result.state
      : { status: "loading" };
  return { state, retry: () => setAttempt((value) => value + 1) };
}
