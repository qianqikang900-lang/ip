import concurrent.futures
import os
import socket
import time

# 输入的 IP 文件与测速后保存的输出文件
INPUT_FILE = "ip.txt"
OUTPUT_FILE = "fast_ip.txt"

def test_single_ip(line, timeout=2):
    """测试单个 IP 节点的 TCP 延迟（毫秒）"""
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

        # 开始进行 TCP 连通性与延迟测试
        start_time = time.time()
        # 获取地址信息
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

        if connected:
            latency = int((time.time() - start_time) * 1000)  # 计算毫秒延迟
            return latency, line
            
    except (ValueError, TypeError):
        # 针对解析配置错误的行进行静默忽略
        pass
    except Exception as e:
        # 其他非致命异常可在此处理（如果需要排查可打印 e）
        pass
        
    return None

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"错误: 未找到 {INPUT_FILE} 文件！请先运行 autoip6.py 生成节点。")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        # 过滤掉空行和纯注释行，去重
        lines = list(set([line.strip() for line in f if line.strip() and not line.strip().startswith("#")]))

    if not lines:
        print(f"错误: {INPUT_FILE} 文件中没有有效的节点数据！")
        return

    print(f"成功加载 {INPUT_FILE}，共有 {len(lines)} 个有效节点，正在多线程并发测速...")

    results = []
    # 使用线程池并发测试（max_workers 可根据需要调整，建议 50-100 以加快速度）
    max_workers = min(50, len(lines)) if len(lines) > 0 else 30
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(test_single_ip, line): line for line in lines}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                if res:
                    results.append(res)  # 格式: (latency, original_line)
            except Exception:
                pass

    # 按照延迟从小到大排序（延迟越低速度越快）
    results.sort(key=lambda x: x[0])

    print(f"\n测速完成！有效可用节点共 {len(results)} 个。")
    print("-" * 45)
    print(f"{'延迟 (ms)':<12} | 节点详情")
    print("-" * 45)

    # 打印前 15 个最快节点的预览
    for latency, line in results[:15]:
        print(f"{str(latency) + ' ms':<12} | {line}")

    if len(results) > 15:
        print(f"... 还有 {len(results) - 15} 个节点未展示")

    # 将所有测速通过的节点按速度排序后保存到输出文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for latency, line in results:
            f.write(f"{line}\n")

    print(f"\n所有可用节点已按延迟从快到慢保存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
