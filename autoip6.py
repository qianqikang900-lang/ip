import concurrent.futures
import ipaddress
import os
import re
import socket
import time
import requests

# 目标URL列表
urls = [
    'https://raw.githubusercontent.com/Xiaobei09/proxyip/refs/heads/main/data/valid/all_ltd.txt'

]
#    'https://cf.090227.xyz', 
#    'https://stock.hostmonit.com/CloudFlareYes',
#    'https://addressesapi.090227.xyz/ip.164746.xyz',
#    'https://api.uouin.com/cloudflare.html',

# 检查文件是否存在并删除
if os.path.exists('ip.txt'):
  os.remove('ip.txt')
if os.path.exists('ipv6.txt'):
  os.remove('ipv6.txt')

# 使用集合去重（存储原始的整行或 "ip:port" 结构）
unique_ipv4_entries = set()
unique_ipv6_entries = set()

# 优化的正则表达式：匹配 IP 以及后面可能自带的 :port 和 #备注
# 兼容 IPv4 和 IPv6 (IPv6 带有方括号如 [2400::1]:8443)
ipv4_line_pattern = r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?::[0-9]+)?(?:#[\w-]*)?'
ipv6_line_pattern = (r'(?:\[(?:[A-F0-9a-f]{1,4}:){1,7}[A-F0-9a-f]{1,4}\]'r'|(?:[A-F0-9a-f]{1,4}:){1,7}[A-F0-9a-f]{1,4})(?::[0-9]+)?(?:#[\w-]*)?')

print("正在从各个源抓取并解析 IP 地址...")
for url in urls:
    try:
        response = requests.get(url, timeout=7)
        if response.status_code == 200:
            html_content = response.text
            v4_matches = re.findall(ipv4_line_pattern, html_content)
            v6_matches = re.findall(ipv6_line_pattern, html_content)
            
            for entry in v4_matches:
                ip_part = entry.split(':')[0].split('#')[0]
                try:
                    ipaddress.IPv4Address(ip_part)
                    unique_ipv4_entries.add(entry.strip())
                except ValueError:
                    continue
                    
            for entry in v6_matches:
                ip_part = (
                    entry.split(']')[0]
                    .replace('[', '')
                    .split(':')[0]
                    .split('#')[0]
                )
                try:
                    ipaddress.IPv6Address(ip_part)
                    unique_ipv6_entries.add(entry.strip().lower())
                except ValueError:
                    continue
    except requests.exceptions.RequestException as e:
        print(f'请求 {url} 失败: {e}')
        continue

print(f"抓取完成！共收集到 {len(unique_ipv4_entries)} 个唯一 IPv4，{len(unique_ipv6_entries)} 个唯一 IPv6。")


def get_country_code(ip):
    """获取 IP 对应的国家代码（带简单重试）"""
    url = f"https://api.ipinfo.io/lite/{ip}?token=6f75ff6b8f013b"
    for _ in range(2):
        try:
            resp = requests.get(url, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("country_code") or data.get("country") or "ZZ"
        except Exception:
            time.sleep(0.2)
    return "ZZ"


def process_entry(entry, default_port=443, timeout=2):
    """通用解析、测速与查归属地函数（支持动态端口解析）"""
    try:
        # 1. 兼容带方括号的 IPv6 (如 [2400::1]:8443) 和普通 IPv4 (如 1.2.3.4:443)
        if entry.startswith('['):
            parts = entry.split(']')
            ip = parts[0].replace('[', '')
            remainder = parts[1]
        else:
            parts = entry.split(':')
            ip = parts[0]
            remainder = ':'.join(parts[1:]) if len(parts) > 1 else ''

        # 2. 提取端口：如果链接或文本中自带了端口号则使用自带的，否则使用默认端口
        port = default_port
        port_match = re.search(r':(\d+)', remainder)
        if port_match:
            port = int(port_match.group(1))

        # 3. TCP 连通性测试（使用解析出来的实际端口）
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
            except socket.error:
                s.close()
                continue
        
        # 4. 连通成功后查询归属地，并把真实的端口拼接并写入文件
        if connected:
            country = get_country_code(ip)
            if ":" in ip:  # IPv6 格式
                return f"[{ip}]:{port}#{country}"
            else:          # IPv4 格式
                return f"{ip}:{port}#{country}"
    except Exception:
        pass
    return None


# 使用线程池并发处理 IPv4 测速
valid_ipv4_results = []
if unique_ipv4_entries:
    print("正在并发测试 IPv4 连通性及获取归属地...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(process_entry, entry) for entry in unique_ipv4_entries]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                valid_ipv4_results.append(res)

    with open('ip.txt', 'w', encoding='utf-8') as f:
        for line in sorted(valid_ipv4_results):
            f.write(line + '\n')
    print(f"IPv4 处理完毕，有效节点已写入 ip.txt，共 {len(valid_ipv4_results)} 个。")


# 使用线程池并发处理 IPv6 测速
valid_ipv6_results = []
if unique_ipv6_entries:
    print("正在并发测试 IPv6 连通性及获取归属地...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(process_entry, entry) for entry in unique_ipv6_entries]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                valid_ipv6_results.append(res)

    with open('ipv6.txt', 'w', encoding='utf-8') as f:
        for line in sorted(valid_ipv6_results):
            f.write(line + '\n')
    print(f"IPv6 处理完毕，有效节点已写入 ipv6.txt，共 {len(valid_ipv6_results)} 个。")
    
