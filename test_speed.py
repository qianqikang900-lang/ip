import concurrent.futures
import os
import socket
import ssl
import time
import urllib.request
import urllib.error

# 输入的 IP 文件与测速后保存的输出文件
INPUT_FILE = "ip.txt"
OUTPUT_FILE = "fast_ip.txt"

# 测速专用的 URL
SPEED_TEST_URL = "https://speed.cloudflare.com/__down?bytes=1000000"

def test_single_ip(line, timeout=3):
    """测试单个 IP 节点的 TCP 延迟与实际下载速度"""
    line = line.strip()
    if not line:
        return None
        
    try:
        # 分离出 IP、端口和国家代码备注 (例如: 1.2.3.4:443#TH)
        if "#" in line:
            ip_port_part, country_tag = line.rsplit("#", 1)
        else:
            ip_port_part = line

        # 兼容 IPv6 方括号与 IPv4 端口解析
        if ip_port_part.startswith("["):
            parts = ip_port_part.split("]")
            ip = parts[0].replace("[", "")
            port = int(parts[1].replace(":", ""))
        else:
            ip, port_str = ip_port_part.rsplit(":", 1)
            port = int(port_str)

        # 1. 先进行 TCP 连通性测试（快速排除死IP）
        start_time = time.time()
        addr_info = socket.getaddrinfo(ip, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        
        connected = False
        for res in addr_info:
            af, socktype, proto, _, sa = res
            s = socket.socket(af, socktype, proto)
            s.settimeout(timeout)
            try:
                s.connect(sa)
                connected = True
                s.close()
                break
            except Exception:
                s.close()
                continue

        if not connected:
            return None

        latency = int((time.time() - start_time) * 1000)  # TCP 延迟 (ms)

        # 2. 进阶：通过真实下载测速获取网速
        speed_kbps = 0.0
        try:
            # 创建不校验证书的安全上下文
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            handler = urllib.request.HTTPSHandler(context=ctx)
            opener = urllib.request.build_opener(handler)
            
            req = urllib.request.Request(SPEED_TEST_URL)
            
            dl_start = time.time()
            with opener.open(req, timeout=timeout) as response:
                if response.status == 200:
                    # 【优化】将读取量从 300KB 调整为 150KB，提高多线程测速并发响应速度
                    chunk = response.read(150 * 1024)
                    dl_time = time.time() - dl_start
                    
                    if dl_time > 0 and len(chunk) > 0:
                        speed_bytes_per_sec = len(chunk) / dl_time
                        speed_kbps = speed_bytes_per_sec / 1024
        except Exception:
            # 下载测速失败时优雅降级，仅保留 TCP 延迟
            pass

        return latency, speed_kbps, line

    except Exception:
        pass
        
    return None

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"错误: 未找到 {INPUT_FILE} 文件！")
        return
        
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    print(f"成功加载 {INPUT_FILE}，共有 {len(lines)} 个节点，正在多线程并发测速中...")
    results = []
    
    # 使用线程池并发测试（max_workers 可根据机器性能调整）
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(test_single_ip, line): line for line in lines}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                results.append(res)  # 格式: (latency, speed_kbps, original_line)

    # 1. 排序规则：优先按下载速度从大到小排序，若速度为0则按延迟从小到大排序
    results.sort(key=lambda x: (-x[1], x[0]))
    
    print(f"\n测速完成！有效可用节点共 {len(results)} 个。")
    print("-" * 65)
    print(f"{'下载速度':<15} | {'延迟 (ms)':<12} | 节点详情")
    print("-" * 65)
    
    # 打印前 15 个最快节点的预览
    for latency, speed_kbps, line in results[:15]:
        if speed_kbps >= 1024:
            speed_str = f"{speed_kbps / 1024:.2f} MB/s"
        elif speed_kbps > 0:
            speed_str = f"{speed_kbps:.1f} KB/s"
        else:
            speed_str = f"{latency}ms (仅延迟)"
        print(f"{speed_str:<15} | {str(latency) + ' ms':<12} | {line}")

    if len(results) > 15:
        print(f"... 还有 {len(results) - 15} 个节点未展示")

    # 2. 【核心修改】只截取最优的前 50 个节点
    top_50_results = results[:50]

    # 保存结果到输出文件
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for latency, speed_kbps, line in top_50_results:
                if speed_kbps >= 1024:
                    speed_tag = f"{speed_kbps / 1024:.1f}MB/s"
                elif speed_kbps > 0:
                    speed_tag = f"{speed_kbps:.0f}KB/s"
                else:
                    speed_tag = f"{latency}ms"
                    
                if "#" in line:
                    new_line = f"{line} ({speed_tag})"
                else:
                    new_line = f"{line}#{speed_tag}"
                f.write(f"{new_line}\n")
                
        print(f"\n已成功将最优的前 {len(top_50_results)} 个节点保存至: {OUTPUT_FILE}")
    except IOError as e:
        print(f"错误: 无法写入文件 {OUTPUT_FILE}！原因: {e}")
