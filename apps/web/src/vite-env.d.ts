/// <reference types="vite/client" />

// .env.sample 참고. 비워두면 동일 오리진(vite dev proxy)을 쓴다.
interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_WS_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
