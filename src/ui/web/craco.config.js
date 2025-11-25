/**
 * CRACO configuration to fix webpack-dev-server 5.x compatibility issues
 * 
 * This configuration excludes webpack-dev-server from source-map-loader
 * processing to prevent build errors after upgrading to webpack-dev-server 5.x
 * 
 * Issue: source-map-loader tries to process webpack-dev-server/client/index.js
 * and fails with ENOENT error. This is a known compatibility issue between
 * react-scripts and webpack-dev-server 5.x.
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
      
      return webpackConfig;
    },
  },
};

