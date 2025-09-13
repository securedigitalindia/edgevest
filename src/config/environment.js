const config = {
  apiUrl: process.env.REACT_APP_API_URL || 'http://localhost:8000/api',
  wsUrl: process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws',
  useMock: process.env.REACT_APP_USE_MOCK === 'true' || true, // Default to mock for development
  appName: 'EdgeVest',
  appVersion: process.env.REACT_APP_VERSION || '1.0.0',
  environment: process.env.NODE_ENV || 'development',
  defaultRefreshInterval: 30000,
  tokenKey: 'edgevest_token',
  debug: process.env.NODE_ENV === 'development',
};

export default config;
