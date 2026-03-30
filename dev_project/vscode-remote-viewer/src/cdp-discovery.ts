import { execSync } from 'child_process';

export function parseCdpPortFromProcessLine(line: string): number | null {
  const match = line.match(/--remote-debugging-port=(\d+)/);
  return match ? parseInt(match[1], 10) : null;
}

export async function discoverCdpPort(): Promise<number> {
  try {
    const output = execSync(
      'ps aux | grep -i "[c]hrome\\|[c]hromium" | grep "remote-debugging-port"',
      { encoding: 'utf-8', timeout: 5000 }
    );
    for (const line of output.trim().split('\n')) {
      const port = parseCdpPortFromProcessLine(line);
      if (port) return port;
    }
  } catch {
    // ps 命令无结果或超时
  }
  throw new Error('未发现运行中的 Chrome/Chromium CDP 端口');
}

export interface CdpTarget {
  id: string;
  type: string;
  title: string;
  url: string;
  webSocketDebuggerUrl: string;
}

export async function findCdpTargets(port: number): Promise<CdpTarget[]> {
  const resp = await fetch(`http://127.0.0.1:${port}/json/list`);
  if (!resp.ok) throw new Error(`CDP HTTP ${resp.status}`);
  return resp.json() as Promise<CdpTarget[]>;
}

export async function findPageTarget(port: number): Promise<CdpTarget> {
  const targets = await findCdpTargets(port);
  const pages = targets.filter(t => t.type === 'page');
  // 优先选非内部页面（排除 chrome://, about:blank 等）
  const page = pages.find(t => !t.url.startsWith('chrome://') && t.url !== 'about:blank') || pages[0];
  if (!page) throw new Error('未找到页面 target');
  return page;
}
