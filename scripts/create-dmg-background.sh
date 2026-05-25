#!/bin/bash
# 生成 DMG 背景图片（660x400）

BG_WIDTH=660
BG_HEIGHT=400
OUTPUT="${1:-/tmp/dmg-background.png}"

python3 - "$OUTPUT" "$BG_WIDTH" "$BG_HEIGHT" << 'PYTHON_SCRIPT'
import sys
import struct
import zlib

output = sys.argv[1]
W, H = int(sys.argv[2]), int(sys.argv[3])

def create_png(width, height, filename):
    rows = []
    for y in range(height):
        row = b'\x00'
        for x in range(width):
            t = y / height
            r = int(248 + (255 - 248) * t)
            g = int(250 + (255 - 250) * t)
            b = int(252 + (255 - 252) * t)
            
            cx, cy = width // 2, height // 2
            rect_w, rect_h = 480, 260
            if abs(x - cx) < rect_w // 2 and abs(y - cy) < rect_h // 2:
                r = min(255, r + 5)
                g = min(255, g + 5)
                b = min(255, b + 5)
            
            if (x % 40 == 0 and y % 40 == 0 and 
                abs(x - cx) < rect_w // 2 + 40 and abs(y - cy) < rect_h // 2 + 40):
                r = max(0, r - 15)
                g = max(0, g - 15)
                b = max(0, b - 15)

            arrow_x, arrow_y = cx, cy
            if abs(y - arrow_y) < 2 and (arrow_x - 30) < x < (arrow_x + 30):
                r, g, b = 120, 120, 160
            dx = x - (arrow_x + 30)
            dy = y - arrow_y
            if 0 <= dx <= 15 and abs(dy) <= 15 - dx:
                r, g, b = 120, 120, 160

            row += bytes([r, g, b, 255])
        rows.append(row)
    
    raw = b''.join(rows)
    
    def make_png(w, h, raw_data):
        def chunk(ctype, data):
            c = ctype + data
            return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        header = b'\x89PNG\r\n\x1a\n'
        ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
        compressed = zlib.compress(raw_data, 9)
        return header + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    
    png_data = make_png(width, height, raw)
    with open(filename, 'wb') as f:
        f.write(png_data)
    print(f"Background created: {filename}")

create_png(W, H, output)
PYTHON_SCRIPT

echo "DMG background: $OUTPUT"
