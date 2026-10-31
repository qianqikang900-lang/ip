import concurrent.futures
import os
import socket
import time
import requests

# 输入的 IP 文件与测速后保存的输出文件
INPUT_FILE = "ip.txt"
OUTPUT_FILE = "fast_ip.txt"

# 你的自建测速网站
SPEED_TEST_URL = "https://sp33d.b3st1p.kdns.fr/"

def test_single_ip(line, timeout=3):
    """测试单个 IP 节点的 TCP 延迟以及通过自建测速网站的 HTTP 响应延迟"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    
    try:
        # 分离出 IP、端口和国家代码备注 (例如: 1.2.3.4:443#TH 或 [2001:db8::1]:443)
        if "#" in line:
            ip_port_part, country_tag = line.rsplit("#", 1)
            country_tag = "#" + country_tag
        else:
            ip_port_part = line
            country_tag = ""

        # 兼容 IPv6 方括号与 IPv4 端口解析
        if ip_port_part.startswith("["):
            parts = ip_port_part.split("]")
            ip = parts[0].replace("[", "")
            port = int(parts[1].replace(":", ""))
        else:
            ip, port_str = ip_port_part.rsplit(":", 1)
            port = int(port_str)

        # 1. 第一步：基础 TCP 连通性快速过滤
        addr_info = socket.getaddrinfo(ip, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        connected = False
        for res in addr_info:
            af, socktype, proto, _, sa = res
            try:
                with socket.socket(af, socktype, proto) as s:
                    s.settimeout(timeout)
                    s.connect(sa)
                    connected = True
                    break
            except (socket.error, OSError):
                continue

        if not connected:
            return None

        # 2. 第二步：通过你的自建测速网站进行 HTTP 延迟与可用性综合测试
        # 注：如果需要让请求精准落到当前测试的 IP 上，可以使用 requests 的 TransportAdapter 
        # 这里先以直接对测速网址发起请求、综合计算耗时为例：
        start_time = time.time()
        try:
            # 如果你的测速网站需要忽略自签证书警告，可以加上 verify=False
            response = requests.get(SPEED_TEST_URL, timeout=timeout, verify=False)
            if response.status_code == 200:
                latency = int((time.time() - start_time) * 1000)
                return latency, line
        except Exception:
            pass
            
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

    print(f"成功加载 {INPUT_FILE}，共有 {len(lines)} 个有效节点，正在联合测速网站进行多线程并发测速...")

    results = []
    max_workers = min(30, len(lines)) if len(lines) > 0 else 20  # 涉及 HTTP 请求，线程数适当调优
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(test_single_ip, line): line for line in lines}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception:
                pass

    # 按照延迟从小到大排序
    results.sort(key=lambda x: x[0])

    # 截取最优的前 100 个 IP
    top_results = results[:100]

    print(f"\n测速完成！有效可用节点共 {len(results)} 个，已为您选取最优的 {len(top_results)} 个节点。")
    print("-" * 45)
    print(f"{'延迟 (ms)':<12} | 节点详情")
    print("-" * 45)

    for latency, line in top_results:
        print(f"{str(latency) + ' ms':<12} | {line}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for latency, line in top_results:
            f.write(f"{line} - {latency}ms\n")

    print(f"\n最优的 {len(top_results)} 个节点已保存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
