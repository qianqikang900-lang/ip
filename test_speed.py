import concurrent.futures
import os
import shutil
import socket
import subprocess
import sys
import time

# 输入的 IP 文件与测速后保存的输出文件
INPUT_FILE = "ip.txt"
OUTPUT_FILE = "fast_ip.txt"

# 接入 cfnb 标准测速域名和测速包大小
SPEED_DOMAIN = "speed.cloudflare.com"
SPEED_PATH = "/__down"
SPEED_BYTES = 2 * 1024 * 1024  # 2MB 测速包

def get_curl_command() -> str | None:
    """获取系统可用的 curl 命令路径"""
    if sys.platform == "win32":
        return shutil.which("curl.exe") or shutil.which("curl")
    return shutil.which("curl")

def parse_curl_speed(stdout: str) -> float:
    """解析 curl 返回的下载速度 (Mbps)"""
    try:
        parts = stdout.strip().split()
        if len(parts) < 2:
            return 0.0
        size_text, time_text = parts[0], parts[1]
        size_bytes = float(size_text)
        time_total = float(time_text)
    except ValueError:
        return 0.0

    if size_bytes <= 0 or time_total <= 0:
        return 0.0
    return round((size_bytes * 8) / (time_total * 1_000_000), 2)

def measure_speed_with_curl(ip: str, port: int, timeout: float = 3.0) -> float:
    """使用 curl 对指定 IP 和端口进行真实下载测速"""
    curl = get_curl_command()
    if not curl:
        return 0.0

    url = f"https://{SPEED_DOMAIN}:{port}{SPEED_PATH}?bytes={SPEED_BYTES}"
    cmd = [
        curl,
        "-s",
        "-o", "NUL" if sys.platform == "win32" else "/dev/null",
        "-w", "%{size_download} %{time_total}",
        "--resolve", f"{SPEED_DOMAIN}:{port}:{ip}",
        "--connect-timeout", str(min(3.0, timeout)),
        "--max-time", str(timeout),
        "--insecure",
        url,
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 2,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0 and result.stdout.strip():
            return parse_curl_speed(result.stdout)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return 0.0

def test_single_ip(line, timeout=3):
    """
    单节点综合测试：
    1. TCP 端口连通与延迟测试
    2. curl 真实下载带宽测速
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    
    try:
        # 分离出 IP、端口和国家代码备注 (例如: 1.2.3.4:443#TH 或 [2001:db8::1]:443)
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

        # 1. 第一步：TCP 连通性与延迟测试
        start_time = time.perf_counter()
        
        # 优化：通过 socket 直接连接，避免不必要的 getaddrinfo 阻塞
        connected = False
        addr_family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        
        try:
            with socket.socket(addr_family, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((ip, port))
                connected = True
        except (socket.error, OSError):
            # 如果直连失败，尝试用 getaddrinfo 兼容多协议
            try:
                addr_info = socket.getaddrinfo(ip, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for res in addr_info:
                    af, socktype, proto, _, sa = res
                    with socket.socket(af, socktype, proto) as s:
                        s.settimeout(timeout)
                        s.connect(sa)
                        connected = True
                        break
            except (socket.error, OSError):
                pass

        if not connected:
            return None

        tcp_latency = int((time.perf_counter() - start_time) * 1000)

        # 2. 第二步：通过 curl 测速接口测试真实下载带宽 (Mbps)
        speed_mbps = measure_speed_with_curl(ip, port, timeout=3.0)
        
        return tcp_latency, speed_mbps, line
            
    except (ValueError, TypeError):
        pass
    except Exception:
        pass
        
    return None

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"错误: 未找到 {INPUT_FILE} 文件！请先运行 autoip6.py 生成节点。")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = list(set([line.strip() for line in f if line.strip() and not line.strip().startswith("#")]))

    if not lines:
        print(f"错误: {INPUT_FILE} 文件中没有有效的节点数据！")
        return

    print(f"成功加载 {INPUT_FILE}，共有 {len(lines)} 个有效节点，正在使用 cfnb 标准测速接口进行多线程测速...")

    results = []
    max_workers = min(20, len(lines)) if len(lines) > 0 else 10
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(test_single_ip, line): line for line in lines}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                if res:
                    results.append(res)  # 结构: (latency, speed_mbps, line)
            except Exception:
                pass

    # 优先按照下载速度从大到小排序，其次按 TCP 延迟从小到大排序
    results.sort(key=lambda x: (-x[1], x[0]))

    # 截取最优的前 100 个节点
    top_results = results[:100]

    print(f"\n测速完成！有效可用节点共 {len(results)} 个，已为您选取最优的 {len(top_results)} 个节点。")
    print("-" * 65)
    print(f"{'TCP延迟':<10} | {'下载速度':<12} | 节点详情")
    print("-" * 65)

    for latency, speed, line in top_results:
        print(f"{str(latency) + ' ms':<10} | {str(speed) + ' Mbps':<12} | {line}")

    # 将结果按“节点 - 延迟ms - 速度Mbps”的格式写入输出文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for latency, speed, line in top_results:
            f.write(f"{line} - {latency}ms - {speed}Mbps\n")

    print(f"\n最优的 {len(top_results)} 个节点（含延迟与下载速度）已保存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
