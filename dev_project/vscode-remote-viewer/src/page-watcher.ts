import WebSocket from 'ws';
import { discoverCdpPort, findBrowserWsUrl, findAllPageTargets, type CdpTarget } from './cdp-discovery';

export type BrowserActivatedCallback = (url: string) => void;
export type FrameCallback = (base64Data: string, sessionId: number) => void;
export type ReconnectedCallback = () => void;
export type TabsChangedCallback = (tabs: TabInfo[]) => void;

export interface TabInfo {
  targetId: string;
  url: string;
  title: string;
}

export class PageWatcher {
  // 浏览器级 WebSocket（用于 Target domain 事件）
  private browserWs: WebSocket | undefined;
  // 当前活跃页面的 WebSocket（用于 screencast）
  private pageWs: WebSocket | undefined;
  private activeTargetId: string | undefined;
  private currentUrl = 'about:blank';
  private cmdId = 0;
  private disposed = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private cdpPort: number | undefined;

  // Tab 列表
  private tabs: Map<string, TabInfo> = new Map();

  // 回调
  private onBrowserActivated: BrowserActivatedCallback | null = null;
  private onFrame: FrameCallback | null = null;
  private onReconnected: ReconnectedCallback | null = null;
  private onTabsChanged: TabsChangedCallback | null = null;

  setOnActivated(cb: BrowserActivatedCallback) { this.onBrowserActivated = cb; }
  setOnFrame(cb: FrameCallback) { this.onFrame = cb; }
  setOnReconnected(cb: ReconnectedCallback) { this.onReconnected = cb; }
  setOnTabsChanged(cb: TabsChangedCallback) { this.onTabsChanged = cb; }

  /** 获取当前所有 tab */
  getTabs(): TabInfo[] {
    return Array.from(this.tabs.values()).filter(
      t => t.url !== 'about:blank' && !t.url.startsWith('chrome://')
    );
  }

  getActiveTargetId(): string | undefined {
    return this.activeTargetId;
  }

  async connect(): Promise<void> {
    this.closeBrowserWs();
    this.closePageWs();

    this.cdpPort = await discoverCdpPort();
    const browserWsUrl = await findBrowserWsUrl(this.cdpPort);

    // 1. 建立浏览器级连接（监听 Target 事件）
    await this.connectBrowserWs(browserWsUrl);

    // 2. 初始化 tab 列表
    await this.refreshTabs();

    // 3. 连接到第一个可用页面
    const visibleTabs = this.getTabs();
    if (visibleTabs.length > 0) {
      await this.switchToTarget(visibleTabs[0].targetId);
    }
  }

  private connectBrowserWs(wsUrl: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.browserWs = new WebSocket(wsUrl);

      this.browserWs.on('open', () => {
        this.sendBrowserCommand('Target.setDiscoverTargets', { discover: true });
        resolve();
      });

      this.browserWs.on('message', (raw: Buffer) => {
        const msg = JSON.parse(raw.toString());
        this.handleBrowserMessage(msg);
      });

      this.browserWs.on('close', () => {
        if (!this.disposed) this.scheduleReconnect();
      });

      this.browserWs.on('error', (err) => {
        reject(err);
      });
    });
  }

  /** 刷新 tab 列表（从 HTTP 端点） */
  async refreshTabs(): Promise<void> {
    if (!this.cdpPort) return;
    try {
      const targets = await findAllPageTargets(this.cdpPort);
      this.tabs.clear();
      for (const t of targets) {
        this.tabs.set(t.id, { targetId: t.id, url: t.url, title: t.title });
      }
      this.emitTabsChanged();
    } catch {
      // 刷新失败不阻塞
    }
  }

  /** 切换 screencast 到指定 target */
  async switchToTarget(targetId: string): Promise<void> {
    if (!this.cdpPort) throw new Error('CDP 未连接');

    // 停止旧的 screencast
    this.closePageWs();

    // 从 tab 列表找到 target 的 WS URL
    const targets = await findAllPageTargets(this.cdpPort);
    const target = targets.find(t => t.id === targetId);
    if (!target) throw new Error(`Target ${targetId} 未找到`);

    return new Promise((resolve, reject) => {
      this.pageWs = new WebSocket(target.webSocketDebuggerUrl);
      this.activeTargetId = targetId;

      this.pageWs.on('open', () => {
        this.sendPageCommand('Page.enable');
        this.sendPageCommand('Runtime.enable');
        resolve();
      });

      this.pageWs.on('message', (raw: Buffer) => {
        const msg = JSON.parse(raw.toString());
        this.handlePageMessage(msg);
      });

      this.pageWs.on('close', () => {
        this.activeTargetId = undefined;
      });

      this.pageWs.on('error', (err) => {
        reject(err);
      });
    });
  }

  /** 处理浏览器级事件（Target domain） */
  private handleBrowserMessage(msg: any) {
    if (msg.method === 'Target.targetCreated') {
      const info = msg.params.targetInfo;
      if (info?.type === 'page') {
        this.tabs.set(info.targetId, {
          targetId: info.targetId,
          url: info.url || 'about:blank',
          title: info.title || '',
        });
        this.emitTabsChanged();
        // 如果是新页面且非 about:blank，通知激活
        if (info.url && info.url !== 'about:blank') {
          this.onBrowserActivated?.(info.url);
        }
      }
    }

    if (msg.method === 'Target.targetInfoChanged') {
      const info = msg.params.targetInfo;
      if (info?.type === 'page' && this.tabs.has(info.targetId)) {
        this.tabs.set(info.targetId, {
          targetId: info.targetId,
          url: info.url || 'about:blank',
          title: info.title || '',
        });
        this.emitTabsChanged();
        // URL 变化通知
        if (info.url && info.url !== 'about:blank' && info.url !== this.currentUrl) {
          this.currentUrl = info.url;
          this.onBrowserActivated?.(info.url);
        }
      }
    }

    if (msg.method === 'Target.targetDestroyed') {
      const targetId = msg.params.targetId;
      this.tabs.delete(targetId);
      this.emitTabsChanged();
      // 如果当前活跃 target 被销毁，尝试切换到其他 tab
      if (targetId === this.activeTargetId) {
        this.activeTargetId = undefined;
        const remaining = this.getTabs();
        if (remaining.length > 0) {
          this.switchToTarget(remaining[0].targetId).catch(() => {});
        }
      }
    }
  }

  /** 处理页面级事件（Page domain） */
  private handlePageMessage(msg: any) {
    if (msg.method === 'Page.frameNavigated') {
      const frame = msg.params.frame;
      if (frame.parentId) return;
      const url = frame.url;
      if (url && url !== 'about:blank' && url !== this.currentUrl) {
        this.currentUrl = url;
        // 更新 tab 信息
        if (this.activeTargetId) {
          const tab = this.tabs.get(this.activeTargetId);
          if (tab) {
            tab.url = url;
            this.emitTabsChanged();
          }
        }
        this.onBrowserActivated?.(url);
      }
    }

    if (msg.method === 'Page.screencastFrame') {
      const { data, sessionId } = msg.params;
      this.onFrame?.(data, sessionId);
      this.sendPageCommand('Page.screencastFrameAck', { sessionId });
    }
  }

  startScreencast(quality: number, maxWidth: number, maxHeight: number) {
    this.sendPageCommand('Page.startScreencast', {
      format: 'jpeg', quality, maxWidth, maxHeight,
    });
  }

  stopScreencast() {
    this.sendPageCommand('Page.stopScreencast');
  }

  private sendBrowserCommand(method: string, params?: any) {
    if (this.browserWs?.readyState === WebSocket.OPEN) {
      this.browserWs.send(JSON.stringify({ id: ++this.cmdId, method, params }));
    }
  }

  private sendPageCommand(method: string, params?: any) {
    if (this.pageWs?.readyState === WebSocket.OPEN) {
      this.pageWs.send(JSON.stringify({ id: ++this.cmdId, method, params }));
    }
  }

  /** 启动后台轮询，持续尝试连接直到成功 */
  startPolling() {
    this.scheduleReconnect();
  }

  private scheduleReconnect() {
    if (this.disposed) return;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.connect().then(() => {
        // 连接成功，通知 extension
        this.onReconnected?.();
      }).catch(() => {
        this.scheduleReconnect();
      });
    }, 3000);
  }

  isConnected(): boolean {
    return this.browserWs?.readyState === WebSocket.OPEN;
  }

  isPageConnected(): boolean {
    return this.pageWs?.readyState === WebSocket.OPEN;
  }

  private emitTabsChanged() {
    this.onTabsChanged?.(this.getTabs());
  }

  private closeBrowserWs() {
    if (this.browserWs) {
      this.browserWs.removeAllListeners();
      this.browserWs.close();
      this.browserWs = undefined;
    }
  }

  private closePageWs() {
    if (this.pageWs) {
      this.pageWs.removeAllListeners();
      this.pageWs.close();
      this.pageWs = undefined;
      this.activeTargetId = undefined;
    }
  }

  dispose() {
    this.disposed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.closeBrowserWs();
    this.closePageWs();
  }
}
