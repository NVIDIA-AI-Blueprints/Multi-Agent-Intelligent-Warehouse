const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  console.log('Setting up proxy middleware...');
  
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8001',
      changeOrigin: true,
      secure: false,
      logLevel: 'debug',
      timeout: 60000, // Match axios timeout - 60 seconds
      onError: function (err, req, res) {
        console.log('Proxy error:', err.message);
        res.status(500).json({ error: 'Proxy error: ' + err.message });
      },
      onProxyReq: function (proxyReq, req, res) {
        console.log('Proxying request to:', proxyReq.path);
      },
      onProxyRes: function (proxyRes, req, res) {
        console.log('Proxy response:', proxyRes.statusCode, req.url);
      }
    })
  );
  
  console.log('Proxy middleware configured for /api -> http://localhost:8001');
};
