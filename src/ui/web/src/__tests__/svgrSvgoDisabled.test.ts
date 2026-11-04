/**
 * @jest-environment node
 *
 * package.json overrides svgo to 4.x under @svgr/plugin-svgo (nSpect
 * BDSA-2026-24092 / CVE-2026-73650, -84369, -84370 in svgo 1.3.2). The
 * plugin still calls the svgo 1.x API (`new SVGO()`), which 4.x removed,
 * so the override is only safe while the SVG-component loader keeps svgo
 * disabled. These tests fail if that ever changes.
 */
import fs from 'fs';
import path from 'path';

type Rule = { oneOf?: Rule[]; use?: unknown; loader?: string; options?: Record<string, unknown> };

function svgrLoaders(rules: Rule[]): Array<{ loader: string; options?: Record<string, unknown> }> {
  const found: Array<{ loader: string; options?: Record<string, unknown> }> = [];
  for (const rule of rules) {
    if (rule.oneOf) {
      found.push(...svgrLoaders(rule.oneOf));
    }
    const uses = rule.use ? (Array.isArray(rule.use) ? rule.use : [rule.use]) : [];
    for (const use of uses as Array<{ loader?: string; options?: Record<string, unknown> }>) {
      if (use && typeof use === 'object' && use.loader && use.loader.includes(`${path.sep}@svgr${path.sep}webpack${path.sep}`)) {
        found.push({ loader: use.loader, options: use.options });
      }
    }
  }
  return found;
}

describe('svgo override under @svgr/plugin-svgo', () => {
  it('the production webpack config keeps svgo disabled in every @svgr/webpack loader', () => {
    // serialize-javascript (loaded by the CSS minimizer) needs Web Crypto,
    // which Jest 27's node environment does not expose as a global.
    const g = globalThis as { crypto?: unknown };
    if (!g.crypto) {
      g.crypto = require('crypto').webcrypto;
    }
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const configFactory = require('react-scripts/config/webpack.config');
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const craco = require('../../craco.config');
    const config = craco.webpack.configure(configFactory('production'));

    const loaders = svgrLoaders(config.module.rules);
    expect(loaders.length).toBeGreaterThan(0);
    for (const { options } of loaders) {
      expect(options?.svgo).toBe(false);
    }
  });

  it('@svgr/plugin-svgo resolves a patched svgo (>= 4.1.0)', () => {
    const pluginDir = path.dirname(require.resolve('@svgr/plugin-svgo/package.json'));
    let dir = path.dirname(require.resolve('svgo', { paths: [pluginDir] }));
    while (!fs.existsSync(path.join(dir, 'package.json'))) {
      dir = path.dirname(dir);
    }
    const { name, version } = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));

    expect(name).toBe('svgo');
    const [major, minor] = version.split('.').map(Number);
    expect(major > 4 || (major === 4 && minor >= 1)).toBe(true);
  });
});
