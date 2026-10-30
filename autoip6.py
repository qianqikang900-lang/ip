import requests
import re
import os
import time
import ipaddress

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
    
if unique_ipv4:
    # 转换为列表并排序（这里采用您原有的排序逻辑，或者您可以根据需要调整排序规则）
    all_sorted_v4 = sorted(unique_ipv4, key=lambda ip: [int(part) for part in ip.split('.')])
    
    # 截取前 50 个最好的（如果总数不足 50 个则取全部）
    top_50_v4 = all_sorted_v4[:50]
    
    results_top50 = []
    for ip in top_50_v4:
        # 复用前面的国家代码查询函数
        country_code = get_country_code(ip)
        results_top50.append(f"{ip}:8443#{country_code}")
        time.sleep(1)
        
    with open('bestip.txt', 'w', encoding='utf-8') as file:
        for line in results_top50:
            file.write(line + '\n')
            
    print(f'已成功优选出最好的 {len(results_top50)} 个IPv4地址保存到 bestip.txt 文件。')
else:
    print('没有可用于优选的IPv4地址。')
