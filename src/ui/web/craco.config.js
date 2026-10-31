/**
 * CRACO configuration to fix webpack-dev-server 5.x compatibility issues
 * 
 * This configuration:
 * 1. Excludes webpack-dev-server from source-map-loader processing
 * 2. Removes deprecated webpack-dev-server options (onAfterSetupMiddleware, onBeforeSetupMiddleware)
 * 
 * Issues fixed:
 * - source-map-loader tries to process webpack-dev-server/client/index.js and fails with ENOENT error
 * - react-scripts sets deprecated options that webpack-dev-server 5.x doesn't support
 */

module.exports = {
  webpack: {
    configure: (webpackConfig) => {
      // Helper function to add exclude to a rule
      const addExclude = (rule) => {
        if (!rule.exclude) {
          rule.exclude = [];
        }
        
        // Ensure exclude is an array
        if (!Array.isArray(rule.exclude)) {
          rule.exclude = [rule.exclude];
        }
        
        let modified = false;
        
        // Add webpack-dev-server to exclude list if not already present
        const webpackDevServerPattern = /node_modules[\\/]webpack-dev-server/;
        const hasWebpackExclude = rule.exclude.some(
          (excl) => excl instanceof RegExp && excl.source === webpackDevServerPattern.source
        );
        
        if (!hasWebpackExclude) {
          rule.exclude.push(webpackDevServerPattern);
          modified = true;
        }
        
        // Add @mui packages to exclude list if not already present (they often have missing source maps)
        const muiPattern = /node_modules[\\/]@mui/;
        const hasMuiExclude = rule.exclude.some(
          (excl) => excl instanceof RegExp && excl.source === muiPattern.source
        );
        
        if (!hasMuiExclude) {
          rule.exclude.push(muiPattern);
          modified = true;
        }
        
        return modified;
      };
      
      // Process all rules
      const processRules = (rules) => {
        let modified = false;
        
        for (const rule of rules) {
          // Check if this rule uses source-map-loader
          if (rule.use) {
            const uses = Array.isArray(rule.use) ? rule.use : [rule.use];
            for (const use of uses) {
              if (
                (typeof use === 'string' && use.includes('source-map-loader')) ||
                (typeof use === 'object' && use.loader && use.loader.includes('source-map-loader'))
              ) {
                if (addExclude(rule)) {
                  modified = true;
                  console.log('✅ CRACO: Excluded webpack-dev-server and @mui from source-map-loader');
                }
                // Also configure source-map-loader to ignore missing source maps
                if (typeof use === 'object' && use.loader && use.loader.includes('source-map-loader')) {
                  use.options = use.options || {};
                  use.options.filterSourceMappingUrl = (url, resourcePath) => {
                    // Ignore missing source maps for @mui and webpack-dev-server
                    if (resourcePath.includes('@mui') || resourcePath.includes('webpack-dev-server')) {
                      return false;
                    }
                    return true;
                  };
                }
                break;
              }
            }
          }
          
          // Process oneOf rules (commonly used by react-scripts)
          if (rule.oneOf && Array.isArray(rule.oneOf)) {
            for (const oneOfRule of rule.oneOf) {
              if (oneOfRule.use) {
                const uses = Array.isArray(oneOfRule.use) ? oneOfRule.use : [oneOfRule.use];
                for (const use of uses) {
                  if (
                    (typeof use === 'string' && use.includes('source-map-loader')) ||
                    (typeof use === 'object' && use.loader && use.loader.includes('source-map-loader'))
                  ) {
                    if (addExclude(oneOfRule)) {
                      modified = true;
                      console.log('✅ CRACO: Excluded webpack-dev-server and @mui from source-map-loader (oneOf)');
                    }
                    // Also configure source-map-loader to ignore missing source maps
                    if (typeof use === 'object' && use.loader && use.loader.includes('source-map-loader')) {
                      use.options = use.options || {};
                      use.options.filterSourceMappingUrl = (url, resourcePath) => {
                        // Ignore missing source maps for @mui and webpack-dev-server
                        if (resourcePath.includes('@mui') || resourcePath.includes('webpack-dev-server')) {
                          return false;
                        }
                        return true;
                      };
                    }
                    break;
                  }
                }
              }
            }
          }
        }
        
        return modified;
      };
      
      // Process module rules
      if (webpackConfig.module && webpackConfig.module.rules) {
        processRules(webpackConfig.module.rules);
      }
      
      // Remove deprecated webpack-dev-server options from webpack config (if present)
      // Note: This may not catch all cases since devServer config is set separately
      if (webpackConfig.devServer) {
        delete webpackConfig.devServer.onAfterSetupMiddleware;
        delete webpackConfig.devServer.onBeforeSetupMiddleware;
      }
      
      return webpackConfig;
    },
  },
  // CRACO devServer configuration - intercepts devServer config from react-scripts
  // This runs AFTER webpackDevServer.config.js and removes deprecated options
  devServer: (devServerConfig) => {
    // Remove deprecated options that react-scripts might set
    // These options are not supported in webpack-dev-server 5.x
    if (devServerConfig.onAfterSetupMiddleware !== undefined) {
      console.log('✅ CRACO: Removing deprecated onAfterSetupMiddleware option');
      delete devServerConfig.onAfterSetupMiddleware;
    }
    
    if (devServerConfig.onBeforeSetupMiddleware !== undefined) {
      console.log('✅ CRACO: Removing deprecated onBeforeSetupMiddleware option');
      delete devServerConfig.onBeforeSetupMiddleware;
    }
    
    // Fix https option for webpack-dev-server 5.x
    // webpack-dev-server 5.x requires https to be under server.type and server.options
    if (devServerConfig.https !== undefined) {
      console.log('✅ CRACO: Converting deprecated https option to server.type format');
      const httpsConfig = devServerConfig.https;
      delete devServerConfig.https;
      
      // Convert to new format
      if (httpsConfig === true || (typeof httpsConfig === 'object' && httpsConfig !== null)) {
        devServerConfig.server = {
          type: 'https',
          options: typeof httpsConfig === 'object' ? httpsConfig : {},
        };
      } else {
        devServerConfig.server = {
          type: 'http',
        };
      }
    }
    
    // Ensure setupMiddlewares is present (should already be set by patched webpackDevServer.config.js)
    // If not, we need to set it up to include the proxy middleware
    if (!devServerConfig.setupMiddlewares) {
      // CRA registers src/setupProxy.js through onBeforeSetupMiddleware, which
      // is removed above, so register it here.  setupProxy.js is the single
      // /api proxy: it strips browser-supplied operator credentials, adds
      // MAIW_UI_OPERATOR_WRITE_TOKEN server-side for the equipment write routes
      // only, and honours MAIW_API_PROXY_TARGET.
      const setupProxy = require('./src/setupProxy');
      devServerConfig.setupMiddlewares = (middlewares, devServer) => {
        setupProxy(devServer.app);
        return middlewares;
      };
      console.log('✅ CRACO: /api proxy registered from src/setupProxy.js');
    } else {
      console.log('✅ CRACO: setupMiddlewares is present in devServer config');
    }
    
    return devServerConfig;
  },
};

