import { describe, it } from 'node:test';
import assert from 'node:assert';
import { parseCdpPortFromProcessLine } from '../cdp-discovery';

describe('parseCdpPortFromProcessLine', () => {
  it('should extract port from Chrome process line', () => {
    const line = 'user 12345 0.5 /Applications/Google Chrome.app --remote-debugging-port=59471 --headless';
    assert.strictEqual(parseCdpPortFromProcessLine(line), 59471);
  });

  it('should return null for line without port', () => {
    const line = 'user 12345 0.5 /usr/bin/node server.js';
    assert.strictEqual(parseCdpPortFromProcessLine(line), null);
  });

  it('should handle port at end of line', () => {
    const line = 'chrome --remote-debugging-port=9222';
    assert.strictEqual(parseCdpPortFromProcessLine(line), 9222);
  });
});
