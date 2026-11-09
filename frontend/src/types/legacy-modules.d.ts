declare module '*DashboardLayout.jsx' {
  import type { ComponentType } from 'react';

  const component: ComponentType<Record<string, unknown>>;
  export default component;
}

declare module '*apiClient.js' {
  import type { AxiosInstance } from 'axios';

  const apiClient: AxiosInstance;
  export default apiClient;
}
