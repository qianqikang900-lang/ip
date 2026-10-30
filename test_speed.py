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

# 修改 test_single_ip 的默认超时时间，提高容错
def test_single_ip(line, timeout=5):
    line = line.strip()
    if not line:
        return None
    try:
        # ... (中间的解析和 TCP 测试代码保持不变) ...
        
        if not connected:
            return None
            
        latency = int((time.time() - start_time) * 1000)
        
        # 即使下载测速失败，也先返回延迟，确保有节点可用
        speed_kbps = 0.0
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handler = urllib.request.HTTPSHandler(context=ctx)
            opener = urllib.request.build_opener(handler)
            req = urllib.request.Request(SPEED_TEST_URL)
            
            dl_start = time.time()
            with opener.open(req, timeout=timeout) as response:
                if response.status == 200:
                    chunk = response.read(150 * 1024)
                    dl_time = time.time() - dl_start
                    if dl_time > 0 and len(chunk) > 0:
                        speed_kbps = (len(chunk) / 1024) / dl_time
        except Exception as e:
            # 打印单个节点的下载测速异常（可选，方便排查）
            # print(f"节点 {line} 下载测速跳过: {e}")
            pass
            
        return latency, speed_kbps, line
    except Exception as e:
        # print(f"节点 {line} 解析异常: {e}")
        return None

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"错误: 未找到 {INPUT_FILE} 文件！")
        return
        
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    # 【新增优化】去除空白行以及完全相同的重复 IP 节点，避免重复测速
    lines = list(dict.fromkeys([line.strip() for line in lines if line.strip()]))
        
    print(f"成功加载 {INPUT_FILE}，去重后共有 {len(lines)} 个有效节点，正在多线程并发测速中...")
    results = []
    
    # 将线程数从 25 提高到 50，加快并发测速（可根据需要调整）
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(test_single_ip, line): line for line in lines}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                results.append(res)  # 格式: (latency, speed_kbps, original_line)
                
    # 后续的排序、预览和写入逻辑保持不变...
    # 【可选优化】如果你只想保留下载速度大于 0 的有效测速节点：
    # results = [res for res in results if res[1] > 0]

    # 1. 排序规则：纯粹按延迟从小到大排序（x[0] 代表延迟）
    results.sort(key=lambda x: x[0])

    print(f"\n测速完成！有效可用节点共 {len(results)} 个。")
    print("-" * 65)
    print(f"{'延迟 (ms)':<12} | {'下载速度':<15} | 节点详情")
    print("-" * 65)
    
    # 打印前 15 个最低延迟节点的预览
    for latency, speed_kbps, line in results[:15]:
        if speed_kbps >= 1024:
            speed_str = f"{speed_kbps / 1024:.2f} MB/s"
        elif speed_kbps > 0:
            speed_str = f"{speed_kbps:.1f} KB/s"
        else:
            speed_str = "0 KB/s"
        print(f"{str(latency) + ' ms':<12} | {speed_str:<15} | {line}")

    if len(results) > 15:
        print(f"... 还有 {len(results) - 15} 个节点未展示")

    # 2. 截取延迟最优的前 50 个节点用于写入文件
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
                
        print(f"\n已成功将最优的前 {len(top_50_results)} 个节点保存至: [fast_ip.txt](https://github.com/qianqikang900-lang/ip/blob/main/fast_ip.txt)")
    except IOError as e:
        print(f"错误: 无法写入文件 {OUTPUT_FILE}！原因: {e}")
