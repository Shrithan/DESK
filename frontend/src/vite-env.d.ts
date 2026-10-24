/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WS_URL?: string;
  readonly VITE_CARTESIA_PROXY_URL?: string;
  readonly VITE_CONVEX_URL?: string;
  readonly VITE_KEYS_WS_URL?: string;
  readonly VITE_CARTESIA_STT_WS_URL?: string;
  readonly VITE_VOICECONTROL_PROXY_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
