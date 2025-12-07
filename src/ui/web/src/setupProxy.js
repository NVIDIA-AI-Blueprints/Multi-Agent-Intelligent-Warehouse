const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  console.log('Setting up proxy middleware...');
  
  // Use pathRewrite to add /api prefix back when forwarding
  // Express strips /api when using app.use('/api', ...), so we need to restore it
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8001',
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
  
  console.log('Proxy middleware configured for /api -> http://localhost:8001');
};
