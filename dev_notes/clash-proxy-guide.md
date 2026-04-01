# FlClash 代理模式与配置指南

## 两种代理模式

### 系统代理（System Proxy）

- 修改 macOS 系统网络代理设置（`127.0.0.1:7890`）
- 只对**遵守系统代理设置**的应用有效（浏览器、curl 等）
- 工作在应用层（HTTP/HTTPS）
- **不支持按进程分流**

### TUN 模式（虚拟网卡）

- 创建虚拟网卡设备（`utun`），修改路由表截获所有 IP 包
- **真正的全局代理**，所有 TCP/UDP 流量都会被截获
- 工作在网络层（L3）
- **支持按进程名分流**（`PROCESS-NAME` 规则）

## 让特定应用绕过代理（TUN 模式）

TUN 模式下可通过 Clash 的 `PROCESS-NAME` 规则按进程名直连：

```javascript
const main = (config) => {
    config.rules.unshift('DOMAIN-SUFFIX,ap-east-1.rds.amazonaws.com,DIRECT');
    config.rules.unshift('PROCESS-NAME,java,DIRECT');  // IDEA 直连

    if (config.dns && config.dns['fake-ip-filter']) {
        config.dns['fake-ip-filter'].unshift('+.ap-east-1.rds.amazonaws.com');
    }

    return config;
};
```

常用进程名参考：

| 应用 | 进程名 |
|------|--------|
| IntelliJ IDEA | `java` |
| VS Code | `code` / `electron` |
| Terminal 程序 | 具体二进制名 |

## 只用正向 HTTP 代理（手动模式）

关闭系统代理和 TUN，Clash 仅作为被动的本地代理服务器，只有显式设置了环境变量的程序才走代理：

```bash
# 临时开启
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890

# 单条命令
http_proxy=http://127.0.0.1:7890 https_proxy=http://127.0.0.1:7890 curl https://google.com
```

可在 `~/.zshrc` 中加快捷函数：

```bash
proxy_on() {
  export http_proxy=http://127.0.0.1:7890
  export https_proxy=http://127.0.0.1:7890
  export no_proxy=localhost,127.0.0.1
  echo "代理已开启"
}

proxy_off() {
  unset http_proxy https_proxy no_proxy
  echo "代理已关闭"
}
```

## Git 代理配置

```bash
# 全局设置（所有仓库生效）
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890

# 取消
git config --global --unset http.proxy
git config --global --unset https.proxy

# 只对 GitHub 生效
git config --global http.https://github.com.proxy http://127.0.0.1:7890
```

> **注意**：git 的 `http.proxy` 只对 HTTPS 协议的仓库地址有效（`https://github.com/...`）。SSH 协议（`git@github.com:...`）不走 HTTP 代理，需要在 `~/.ssh/config` 中配置：
>
> ```
> Host github.com
>     ProxyCommand nc -X connect -x 127.0.0.1:7890 %h %p
> ```
