import sqlite3
import re
from datetime import datetime

def parse_whatsapp_date(ts_str):
    if not ts_str:
        return None
    
    # Clean up narrow no-break space \u202f
    ts_str = ts_str.replace('\u202f', ' ').strip()
    
    # Try different formats
    formats = [
        "%d/%m/%y, %I:%M %p",   # 01/01/26, 6:56 pm
        "%d/%m/%Y, %I:%M %p",   # 01/01/2026, 6:56 pm
        "%d/%m/%y, %H:%M",      # 01/01/26, 18:56
        "%d/%m/%Y, %H:%M",      # 01/01/2026, 18:56
        "%d/%m/%y, %I:%M:%S %p",# 01/01/26, 6:56:00 pm
        "%d/%m/%Y, %I:%M:%S %p",# 01/01/2026, 6:56:00 pm
        "%d/%m/%y, %H:%M:%S",   # 01/01/26, 18:56:00
        "%d/%m/%Y, %H:%M:%S",   # 01/01/2026, 18:56:00
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
            
    # Try MM/DD/YY fallback just in case
    mm_formats = [f.replace("%d/%m/", "%m/%d/") for f in formats]
    for fmt in mm_formats:
        try:
            return datetime.strptime(ts_str, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
            
    return ts_str  # Return original if parsing fails

conn = sqlite3.connect('data/resources.db')
cur = conn.cursor()
cur.execute("SELECT id, timestamp FROM messages WHERE timestamp IS NOT NULL")
rows = cur.fetchall()

updates = 0
for row_id, ts in rows:
    # If already ISO, skip
    if re.match(r"^\d{4}-\d{2}-\d{2}", ts):
        continue
    new_ts = parse_whatsapp_date(ts)
    if new_ts != ts:
        cur.execute("UPDATE messages SET timestamp = ? WHERE id = ?", (new_ts, row_id))
        updates += 1

print(f"Updated {updates} rows in data/resources.db")
conn.commit()
conn.close()
