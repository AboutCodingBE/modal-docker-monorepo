export const environment = {
  production: false,
  // API calls go through nginx proxy, so just use relative paths
  apiUrl: '/api',
  // Agent runs natively on the host, Angular calls it directly
  agentUrl: 'http://localhost:9090',
};
