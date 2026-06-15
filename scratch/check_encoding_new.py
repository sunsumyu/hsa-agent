import sys, os
import io

# Force stdout to be utf-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import clickhouse_driver

client = clickhouse_driver.Client(host='localhost', port=9000)
res = client.execute("SELECT med_type, dise_name, oprn_oprt_name, fixmedins_name, psn_name, start_date, end_date FROM default.fqz_gz_jzsj_all_ql LIMIT 10")
for idx, row in enumerate(res):
    print(f"--- Row {idx} ---")
    for col_idx, val in enumerate(row):
        val_str = str(val)
        print(f"Col {col_idx}: {val_str!r}")
        if isinstance(val, str):
            # Let's inspect the Unicode code points of the characters
            code_points = [ord(c) for c in val]
            print(f"  code_points: {code_points}")
            # Try to see if we can convert it to raw bytes by encoding to latin-1 or utf-8 or by treating code points as bytes
            try:
                # If it's a decodable string stored incorrectly, maybe the code points are actually bytes
                byte_list = []
                for c in val:
                    o = ord(c)
                    if o < 256:
                        byte_list.append(o)
                    else:
                        # Character code is larger than 255. Let's see if we can break it down or if it's utf-8 bytes read as something else
                        pass
                if len(byte_list) == len(val):
                    raw_bytes = bytes(byte_list)
                    print(f"  raw_bytes from code points < 256: {raw_bytes}")
                    for enc in ['utf-8', 'gbk', 'gb18030']:
                        try:
                            print(f"    decoded as {enc}: {raw_bytes.decode(enc)}")
                        except Exception:
                            pass
            except Exception as e:
                print(f"  failed treating code points as bytes: {e}")
