import concurrent.futures
import ipaddress
import os
import re
import socket
import time
import requests
import sys

# 目标URL列表
urls = [
    'https://bestcf.pages.dev/random-region/JP/50.txt',
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

def process_entry(entry, timeout=2):
    """通用解析、测速与查归属地函数：严格保留源数据自带的端口"""
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

        # 2. 提取源数据中自带的端口
        # 如果源数据本身没有写端口，可以给一个默认兜底；如果写了，则严格使用源数据的端口
        port = 443  # 基础兜底端口（仅当源数据完全没写端口时生效）
        port_match = re.search(r':(\d+)', remainder)
        if port_match:
            port = int(port_match.group(1))

        # 3. 使用提取出来的真实端口进行 TCP 连通性测试
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
        
        # 4. 连通成功后，使用源数据的真实端口拼接并返回
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
else:
    # 即使没有有效的 IPv4 节点，也创建一个空文件，防止 git 提交时报错找不到文件
    open('ip.txt', 'w', encoding='utf-8').close()


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
else:
    # 即使没有 IPv6，也创建一个空文件，防止 git 提交时报错找不到文件
    open('ipv6.txt', 'w', encoding='utf-8').close()


# ==================== 结尾：自动调用测速脚本 ====================
import subprocess
sys.modules # 确保环境正常

def run_speed_test():
    if not os.path.exists("test_speed.py"):
        print("提示: 未在当前目录下找到 test_speed.py 文件，跳过自动测速。")
        return

    print("=" * 40)
    print("正在自动运行测速脚本 test_speed.py...")
    print("=" * 40)
    
    try:
        # 确保缓冲区的数据完全写入磁盘
        sys.stdout.flush()
        
        # 使用当前解释器运行 test_speed.py
        result = subprocess.run(
            [sys.executable, "test_speed.py"], 
            check=True
        )
        print("\n[成功] 测速脚本执行完毕！")
        
    except subprocess.CalledProcessError as e:
        print(f"\n[错误] 测速脚本执行失败，退出码: {e.returncode}")
        sys.exit(e.returncode)
    except Exception as ex:
        print(f"\n[异常] 启动测速脚本时发生未知错误: {ex}")
        sys.exit(1)

# 主程序结束前直接进行落盘等待并调用测速
if __name__ == "__main__":
    time.sleep(1)  # 确保前面的 ip.txt / ipv6.txt 完全写入磁盘
    run_speed_test()
    
