import WebSocket from 'ws';
import { discoverCdpPort, findPageTarget } from './cdp-discovery';

export type BrowserActivatedCallback = (url: string) => void;
export type FrameCallback = (base64Data: string, sessionId: number) => void;

export class PageWatcher {
  private ws: WebSocket | undefined;
  private currentUrl = 'about:blank';
  private cmdId = 0;
  private onBrowserActivated: BrowserActivatedCallback | null = null;
  private onFrame: FrameCallback | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private disposed = false;

  setOnActivated(cb: BrowserActivatedCallback) {
    this.onBrowserActivated = cb;
  }

  setOnFrame(cb: FrameCallback) {
    this.onFrame = cb;
  }

  async connect(): Promise<void> {
    this.closeWs();
    const port = await discoverCdpPort();
    const target = await findPageTarget(port);

    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(target.webSocketDebuggerUrl);

      this.ws.on('open', () => {
        this.sendCommand('Page.enable');
        this.sendCommand('Runtime.enable');
        resolve();
      });

      this.ws.on('message', (raw: Buffer) => {
        const msg = JSON.parse(raw.toString());
        this.handleMessage(msg);
      });

      this.ws.on('close', () => {
        if (!this.disposed) this.scheduleReconnect();
      });

      this.ws.on('error', (err) => {
        reject(err);
      });
    });
  }

  private handleMessage(msg: any) {
    if (msg.method === 'Page.frameNavigated') {
      const frame = msg.params.frame;
      if (frame.parentId) return;
      const url = frame.url;
      if (url && url !== 'about:blank' && url !== this.currentUrl) {
        this.currentUrl = url;
        this.onBrowserActivated?.(url);
      }
    }

    if (msg.method === 'Page.screencastFrame') {
      const { data, sessionId } = msg.params;
      this.onFrame?.(data, sessionId);
      this.sendCommand('Page.screencastFrameAck', { sessionId });
    }
  }

  startScreencast(quality: number, maxWidth: number, maxHeight: number) {
    this.sendCommand('Page.startScreencast', {
      format: 'jpeg', quality, maxWidth, maxHeight,
    });
  }

  stopScreencast() {
    this.sendCommand('Page.stopScreencast');
  }

  sendCommand(method: string, params?: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ id: ++this.cmdId, method, params }));
    }
  }

  private scheduleReconnect() {
    if (this.disposed) return;
    this.reconnectTimer = setTimeout(() => {
      this.connect().catch(() => {
        this.scheduleReconnect();
      });
    }, 5000);
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private closeWs() {
    if (this.ws) {
      this.ws.removeAllListeners();
      this.ws.close();
      this.ws = undefined;
    }
  }

  dispose() {
    this.disposed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.closeWs();
  }
}
