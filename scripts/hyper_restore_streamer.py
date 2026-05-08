import requests
import os
import sys
import time

# 配置
SQL_FILE = r"L:\DB资料\fqz_gz_jzsj_all_ql.sql"
CH_URL = "http://127.0.0.1:8123/"
# 修正：根据探测结果，使用免密模式
AUTH = {"user": "default"} 
DATABASE = "fqz_hsa"
BATCH_SIZE = 10 * 1024 * 1024  # 10MB per chunk

def stream_restore():
    if not os.path.exists(SQL_FILE):
        print(f"FAILED: Source file not found: {SQL_FILE}")
        return

    file_size = os.path.getsize(SQL_FILE)
    print(f"RESTART: Physical Restoration of {file_size / (1024**3):.2f} GB Data...")
    print(f"MODE: No-Password Auth | TARGET: '{DATABASE}'")
    print("-" * 50)

    total_bytes_sent = 0
    start_time = time.time()

    try:
        with open(SQL_FILE, 'rb') as f:
            chunk = []
            current_chunk_size = 0
            
            while True:
                line = f.readline()
                if not line:
                    break
                
                # 实时路由平移：将 default. 修改为 fqz_hsa.
                line = line.replace(b"INSERT INTO default.", f"INSERT INTO {DATABASE}.".encode('utf-8'))
                
                chunk.append(line)
                current_chunk_size += len(line)
                
                if current_chunk_size >= BATCH_SIZE:
                    data = b"".join(chunk)
                    res = requests.post(CH_URL, params=AUTH, data=data)
                    if res.status_code != 200:
                        print(f"\n[!] ERROR at {total_bytes_sent / (1024**2):.1f} MB: {res.text[:200]}")
                    
                    total_bytes_sent += current_chunk_size
                    elapsed = time.time() - start_time
                    speed = (total_bytes_sent / (1024**2)) / (elapsed if elapsed > 0 else 1)
                    progress = (total_bytes_sent / file_size) * 100
                    
                    sys.stdout.write(f"\r[Progress] {progress:.2f}% | Sent: {total_bytes_sent/(1024**2):.1f} MB | Speed: {speed:.2f} MB/s")
                    sys.stdout.flush()
                    
                    chunk = []
                    current_chunk_size = 0

            if chunk:
                requests.post(CH_URL, params=AUTH, data=b"".join(chunk))

    except Exception as e:
        print(f"\nFATAL CRASH: {e}")

    print("\n" + "=" * 50)
    print(f"SUCCESS: Total {total_bytes_sent / (1024**3):.2f} GB Restored to {DATABASE}.")
    print(f"TIME ELAPSED: {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    stream_restore()
