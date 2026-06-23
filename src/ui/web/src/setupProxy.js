const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  const backendUrl = process.env.BACKEND_URL || 'http://backend:8001';

  console.log('Setting up proxy middleware...');
  
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
      target: backendUrl,
      changeOrigin: true,
      secure: false,
      logLevel: 'debug',
      timeout: 300000, // 5 minutes - increased for complex reasoning queries
      proxyTimeout: 300000, // 5 minutes - timeout for proxy connection
      // Increase socket timeout to handle long-running queries
      socketTimeout: 300000, // 5 minutes
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
        console.log('Proxying request:', req.method, req.url, '->', proxyReq.path);
      },
      onProxyRes: function (proxyRes, req, res) {
        console.log('Proxy response:', proxyRes.statusCode, 'for', req.url);
      }
    })
  );
  
  console.log(`Proxy middleware configured for /api -> ${backendUrl}`);
};
