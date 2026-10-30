import time
import requests
import concurrent.futures
import urllib3
import os
import ipaddress
import socket
import re

# 全局禁用 HTTPS 证书验证警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 目标URL列表
urls = [
    'https://raw.githubusercontent.com/ahang39/router/refs/heads/main/all.txt',
    
]
#    'https://cf.090227.xyz', 
#    'https://stock.hostmonit.com/CloudFlareYes',
#    'https://addressesapi.090227.xyz/ip.164746.xyz',
#    'https://api.uouin.com/cloudflare.html',

# 正则表达式用于初步匹配IPV4与IPV6地址（配合ipaddress库二次过滤）
ipv4_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
ipv6_pattern = r'\b(?:[A-F0-9a-f]{1,4}:){1,7}[A-F0-9a-f]{1,4}\b'  # 加入小写支持

# 检查ip.txt和ipv6.txt文件是否存在,如果存在则删除它
if os.path.exists('ip.txt'):
    os.remove('ip.txt')
if os.path.exists('ipv6.txt'):
    os.remove('ipv6.txt')

# 使用集合存储IP地址实现自动去重
unique_ipv4 = set()
unique_ipv6 = set()

for url in urls:
    try:
        # 发送HTTP请求获取网页内容
        response = requests.get(url, timeout=7)
        
        # 确保请求成功
        if response.status_code == 200:
            # 获取网页的文本内容
            html_content = response.text
            
            # 使用正则表达式查找IP地址
            ipv4_matches = re.findall(ipv4_pattern, html_content)
            ipv6_matches = re.findall(ipv6_pattern, html_content)
            
            # 用ipaddress校验并去重
            for ip in ipv4_matches:
                try:
                    ipaddress.IPv4Address(ip)
                    unique_ipv4.add(ip)
                except ValueError:
                    continue
            for ip in ipv6_matches:
                try:
                    # 粗略过滤后进一步用ipaddress校验
                    ip_obj = ipaddress.IPv6Address(ip)
                    unique_ipv6.add(ip.lower())
                except ValueError:
                    continue
    except requests.exceptions.RequestException as e:
        print(f'请求 {url} 失败: {e}')
        continue

# 查询每个IP的country_code
def get_country_code(ip):
    try:
        url = f'https://api.ipinfo.io/lite/{ip}?token=6f75ff6b8f013b'
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('country_code') or data.get('country') or 'ZZ'
        else:
            return 'ZZ'
    except Exception as e:
        print(f"查询IP {ip} country_code失败: {e}")
        return 'ZZ'
        
def test_ip_speed(ip_port_str, timeout=3):
    """
    通用测速函数：支持 IPv4 和 IPv6，自带防错与超时保护
    """
    try:
        raw_line = str(ip_port_str).strip()
        if not raw_line or raw_line.startswith('#'):
            return None
            
        # 智能解析 IPv6 带端口格式：[ip]:port
        if ']' in raw_line:
            parts = raw_line.split(']')
            ip = parts[0].strip('[')
            port = int(parts[1].lstrip(':')) if len(parts) > 1 and ':' in parts[1] else 443
            url_prefix = f"https://[{ip}]:{port}"
        # 智能解析 IPv4 带端口格式：ip:port
        elif raw_line.count(':') == 1:
            ip, port_str = raw_line.split(':')
            ip = ip.strip()
            port = int(port_str.strip())
            url_prefix = f"https://{ip}:{port}"
        else:
            ip = raw_line.strip('[]')
            port = 443
            url_prefix = f"https://{ip}:{port}"
            
        # 1. 动态拼接测速路径
        test_url = f"{url_prefix}/__down?bytes=524288"
        
        start_time = time.time()
        # 2. 必须保留正确的目标域名 Host 头（Cloudflare 节点需要它来识别分发）
        headers = {
            'Host': 'speed.cloudflare.com', 
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        }
        
        # 3. 使用 verify=False 忽略直连 IP 证书不匹配问题
        response = requests.get(test_url, headers=headers, timeout=timeout, verify=False, stream=True)
        
        if response.status_code == 200:
            downloaded_bytes = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded_bytes += len(chunk)
                    # 收到 512KB 数据即可提前跳出，计算平均速度
                    if downloaded_bytes >= 512 * 1024:
                        break
            
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                # 计算速度 (KB/s)
                speed_kbps = (downloaded_bytes / 1024) / elapsed_time
                print(f"IP {ip}:{port} 测速成功，速度: {speed_kbps:.2f} KB/s")
                
                # 【关键修复】必须返回结果字典，供主程序排序和写入 bestip.txt
                return {
                    'ip': ip,
                    'port': port,
                    'speed': speed_kbps
                }
    except Exception as e:
        # 单个节点测速失败不影响其他节点
        pass
    
    return None
    
def get_country_code(ip):
    """
    获取 IP 对应的国家代码
    """
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode", timeout=2)
        if response.status_code == 200:
            # 如果接口查到了国家代码就返回它，没查到则默认返回 "wu"
            return response.json().get("countryCode", "wu")
    except Exception:
        pass
    # 当网络请求异常或超时时，默认返回 "wu"
    return "wu"
    
if unique_ipv4:
    sorted_ipv4 = sorted(unique_ipv4, key=lambda ip: [int(part) for part in ip.split('.')])
    results_v4 = []
    for ip in sorted_ipv4:
        country_code = get_country_code(ip)
        results_v4.append(f"{ip}:8443#{country_code}")
        time.sleep(1)
    with open('ip.txt', 'w', encoding='utf-8') as file:
        for line in results_v4:
            file.write(line + '\n')
    print(f'已保存 {len(results_v4)} 个唯一IPv4地址及country_code到ip.txt文件。')
else:
    print('未找到有效的IPv4地址。')

if 'unique_ipv6' in globals() and unique_ipv6:
    sorted_ipv6 = sorted(unique_ipv6)
    results_v6 = []
    for ip in sorted_ipv6:
        country_code = get_country_code(ip)
        results_v6.append(f"[{ip}]:8443#{country_code}-IPV6")
        time.sleep(1)
    
    with open('ipv6.txt', 'w', encoding='utf-8') as file:
        for line in results_v6:
            file.write(line + '\n')
    print(f'已成功保存 {len(results_v6)} 个IPv6地址到 ipv6.txt 文件。')
else:
    # 即使没有找到 IPv6，也强制创建一个带有说明的文件，防止 GitHub Actions 提交时报错
    with open('ipv6.txt', 'w', encoding='utf-8') as file:
        file.write("# No valid IPv6 addresses found\n")
    print('未找到有效的IPv6地址，已强制生成空的 ipv6.txt 以防提交报错。')
    
if __name__ == "__main__":
    try:
        # 1. 安全读取 ip.txt 和 ipv6.txt（指定 encoding='utf-8' 防乱码/报错）
        all_targets = []
        for filename in ['ip.txt', 'ipv6.txt']:
            if os.path.exists(filename):
                print(f"正在读取文件: {filename}")
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            # 清洗脏数据：过滤空行和注释行
                            if line and not line.startswith('#'):
                                all_targets.append(line)
                except Exception as e:
                    print(f"读取文件 {filename} 时出现异常: {e}")
            else:
                print(f"提示: 未找到文件 {filename}（可能未生成），已自动跳过。")

        # 列表去重
        all_targets = list(set(all_targets))
        print(f"合并去重后共发现 {len(all_targets)} 个待测速节点，开始多线程并发测速...")

        if all_targets:
            tested_results = []
            # 2. 多线程并发测速（控制最大并发 30，平衡速度与稳定性）
            with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
                future_to_ip = {executor.submit(test_ip_speed, item, 3): item for item in all_targets}
                for future in concurrent.futures.as_completed(future_to_ip):
                    try:
                        res = future.result()
                        if res is not None:
                            tested_results.append(res)
                    except Exception:
                        pass

            if tested_results:
                # 3. 按照下载速度从大到小【降序排序】（速度最快的排在最前面）
                sorted_results = sorted(tested_results, key=lambda x: x['speed'], reverse=True)
                
                # 4. 只对最终入选的前 50 个最优 IP 查询国家代码，避免触发 API 限流
                top_50 = sorted_results[:50]
                print(f"测速完成！正在获取前 {len(top_50)} 个最优节点的国家归属地...")
                
                results_best = []
                for item in top_50:
                    ip = item['ip']
                    port = item['port']
                    speed = item['speed']
                    
                    country_code = get_country_code(ip)
                    time.sleep(0.1) # 稍微缓一口气，防止请求过快
                    
                    # 智能识别：IPv6 加上中括号 [ip]:port，IPv4 保持 ip:port
                    if ':' in ip:
                        results_best.append(f"[{ip}]:{port}#{country_code}-{speed}KB/s")
                    else:
                        results_best.append(f"{ip}:{port}#{country_code}-{speed}KB/s")
                
                # 5. 安全写入 bestip.txt 文件
                with open('bestip.txt', 'w', encoding='utf-8') as file:
                    for line in results_best:
                        file.write(line + '\n')
                        
                print(f'✅ 筛选完成！已成功将双文件里速度最快的前 {len(results_best)} 个优质 IP 写入 bestip.txt。')
            else:
                with open('bestip.txt', 'w', encoding='utf-8') as file:
                    file.write("# No high-speed IPs found\n")
                print('⚠️ 所有节点的测速均未通过，已生成空的 bestip.txt。')
        else:
            with open('bestip.txt', 'w', encoding='utf-8') as file:
                file.write("# No IP addresses found in source files\n")
            print('❌ 源码文件中未找到可用的 IP 节点，已生成空的 bestip.txt。')
            
    except Exception as e:
        print(f"❌ 运行过程中发生未捕获的严重错误: {e}")
        with open('bestip.txt', 'w', encoding='utf-8') as file:
            file.write(f"# Critical error: {e}\n")
        
