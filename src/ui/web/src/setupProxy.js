const { createProxyMiddleware } = require('http-proxy-middleware');

// v2.0.1 round 3 (NEW3-P1-01): governed operational writes require the
// operator write credential (X-Maiw-Operator-Token). The browser bundle NEVER
// holds it (never use a REACT_APP_* variable for it). When this development
// server is used as a trusted, localhost-only operator console, the operator
// may set MAIW_UI_OPERATOR_WRITE_TOKEN in the environment of THIS Node process;
// the proxy then adds the header server-side for the three equipment write
// routes only. Anyone who can reach this dev server can then perform governed
// writes — bind it to localhost (HOST=127.0.0.1) and put real operator
// authentication in front of any shared deployment. Unset = the UI cannot
// perform operational writes (the API answers 403 and the UI says so).
const OPERATOR_WRITE_PATHS = new Set([
  '/api/v1/equipment/assign',
  '/api/v1/equipment/release',
  '/api/v1/equipment/maintenance',
]);

module.exports = function(app) {
  console.log('Setting up proxy middleware...');
  if (process.env.MAIW_UI_OPERATOR_WRITE_TOKEN) {
    console.warn('MAIW_UI_OPERATOR_WRITE_TOKEN is set: this dev server will add the operator write credential to equipment write requests. Bind it to localhost only.');
  }
  
  // Use pathRewrite to add /api prefix back when forwarding
  // Express strips /api when using app.use('/api', ...), so we need to restore it
  // Security: HTTP protocol is acceptable for localhost in development/testing only
  // For production deployments, HTTPS must be used to encrypt API communications
  // SonarQube may flag HTTP usage, but it's acceptable for:
  // - localhost (127.0.0.1, 0.0.0.0) - development/testing only
  // Production external services must use HTTPS
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8001',
      changeOrigin: true,
      secure: false,
      logLevel: 'debug',
      timeout: 600000, // 10 minutes (doubled) - increased for complex reasoning queries
      proxyTimeout: 600000, // 10 minutes (doubled) - timeout for proxy connection
      // Increase socket timeout to handle long-running queries
      socketTimeout: 600000, // 10 minutes (doubled)
      pathRewrite: (path, req) => {
        // path will be like '/v1/version' (without /api)
        // Add /api back to get '/api/v1/version'
        const newPath = '/api' + path;
        console.log('Rewriting path:', path, '->', newPath);
        return newPath;
      },
      onError: function (err, req, res) {
        console.log('Proxy error:', err.message);
        res.status(500).json({ error: 'Proxy error: ' + err.message });
      },
      onProxyReq: function (proxyReq, req, res) {
        // Never forward an operator credential supplied by the browser.
        proxyReq.removeHeader('x-maiw-operator-token');
        const operatorToken = process.env.MAIW_UI_OPERATOR_WRITE_TOKEN;
        const targetPath = (proxyReq.path || '').split('?')[0];
        if (operatorToken && req.method === 'POST' && OPERATOR_WRITE_PATHS.has(targetPath)) {
          proxyReq.setHeader('X-Maiw-Operator-Token', operatorToken);
        }
        console.log('Proxying request:', req.method, req.url, '->', proxyReq.path);
      },
      onProxyRes: function (proxyRes, req, res) {
        console.log('Proxy response:', proxyRes.statusCode, 'for', req.url);
      }
    })
  );
  
  console.log('Proxy middleware configured for /api -> http://localhost:8001');
};
