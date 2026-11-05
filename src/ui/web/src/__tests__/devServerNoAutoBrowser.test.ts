/**
 * @jest-environment node
 *
 * react-dev-utils 12.0.1 (react-scripts 5) builds its browser-launch
 * command in a way that permits OS command injection on macOS
 * (CVE-2026-14802, GHSA-g9g6-gvq9-j4vp; nSpect BDSA-2026-18203), and has no
 * fixed release. `npm start` defaults BROWSER=none so the development server
 * never launches a browser. These tests fail if that default is dropped.
 */
import fs from 'fs';
import path from 'path';

const pkg = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../package.json'), 'utf8'));

describe('development server browser launch', () => {
  it('npm start defaults BROWSER to none and still lets it be overridden', () => {
    expect(pkg.scripts.start).toMatch(/(^|\s)BROWSER=\$\{BROWSER:-none\}\s/);
  });

  it('react-dev-utils does not launch anything when BROWSER is none', () => {
    const childProcess = require('child_process');
    const spawn = jest.spyOn(childProcess, 'spawn');
    const execSync = jest.spyOn(childProcess, 'execSync');
    const saved = process.env.BROWSER;
    process.env.BROWSER = 'none';
    try {
      jest.isolateModules(() => {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const openBrowser = require('react-dev-utils/openBrowser');
        expect(openBrowser('http://localhost:3001')).toBe(false);
      });
      expect(spawn).not.toHaveBeenCalled();
      expect(execSync).not.toHaveBeenCalled();
    } finally {
      if (saved === undefined) {
        delete process.env.BROWSER;
      } else {
        process.env.BROWSER = saved;
      }
      spawn.mockRestore();
      execSync.mockRestore();
    }
  });
});
