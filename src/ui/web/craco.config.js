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
        
        // Add webpack-dev-server to exclude list if not already present
        const excludePattern = /node_modules[\\/]webpack-dev-server/;
        const hasExclude = rule.exclude.some(
          (excl) => excl instanceof RegExp && excl.source === excludePattern.source
        );
        
        if (!hasExclude) {
          rule.exclude.push(excludePattern);
          return true;
        }
        return false;
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
                  console.log('✅ CRACO: Excluded webpack-dev-server from source-map-loader');
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
                      console.log('✅ CRACO: Excluded webpack-dev-server from source-map-loader (oneOf)');
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
    
    // Ensure setupMiddlewares is present (should already be set by patched webpackDevServer.config.js)
    // If not, we log a warning but don't add it here since it requires specific middleware setup
    if (!devServerConfig.setupMiddlewares) {
      console.warn('⚠️  CRACO: setupMiddlewares not found in devServer config. This may cause issues.');
    } else {
      console.log('✅ CRACO: setupMiddlewares is present in devServer config');
    }
    
    return devServerConfig;
  },
};

