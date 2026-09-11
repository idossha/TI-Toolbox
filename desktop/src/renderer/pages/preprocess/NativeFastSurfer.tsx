import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { usePageActive } from "../../app/pageActivity";

export const NATIVE_FASTSURFER_STATUS_KEY = ["native-fastsurfer"];

export function useNativeFastSurferStatus() {
  const bridge = window.tit?.fastsurfer;
  const active = usePageActive();
  return useQuery({
    queryKey: NATIVE_FASTSURFER_STATUS_KEY,
    queryFn: () => bridge!.status(),
    enabled: Boolean(bridge) && active,
    refetchInterval: active ? 5_000 : false,
    staleTime: 0,
    retry: false,
  });
}

export function NativeFastSurfer() {
  const status = useNativeFastSurferStatus();
  if (!window.tit?.fastsurfer || !status.data?.supported) return null;
  return (
    <p className="field-help">
      {status.data.enabled ? "Apple GPU enabled." : status.data.preferenceEnabled
        ? "Apple GPU is enabled in your settings; connecting…"
        : "Apple Silicon detected. Enable GPU support in"}{" "}
      <Link to="/settings#preprocessing">Settings → Pre-processing</Link>.
    </p>
  );
}
