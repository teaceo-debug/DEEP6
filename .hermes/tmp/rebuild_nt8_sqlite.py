import sqlite3, os, sys, shutil
SRC = r'/mnt/c/Users/Tea/Documents/NinjaTrader 8/db/NinjaTrader.sqlite'
DST = r'/mnt/c/Users/Tea/Documents/NinjaTrader 8/db/NinjaTrader.rebuilt.sqlite'
if os.path.exists(DST):
    os.remove(DST)

src = sqlite3.connect(SRC)
src.row_factory = sqlite3.Row
dst = sqlite3.connect(DST)
dst.execute('PRAGMA foreign_keys=OFF')
dst.execute('PRAGMA journal_mode=DELETE')
dst.execute('PRAGMA synchronous=OFF')

# Create tables first
schema_rows = src.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, name").fetchall()
tables = [r for r in schema_rows if r['type'] == 'table']
indexes = [r for r in schema_rows if r['type'] == 'index' and not r['name'].startswith('sqlite_autoindex_')]

for r in tables:
    dst.execute(r['sql'])

dst.commit()

copy_report = []
for r in tables:
    tbl = r['name']
    cols = [row[1] for row in src.execute(f'PRAGMA table_info("{tbl}")').fetchall()]
    if not cols:
        copy_report.append((tbl, 'no_columns', 0, ''))
        continue
    quoted_cols = ','.join(f'"{c}"' for c in cols)
    placeholders = ','.join(['?'] * len(cols))
    ins = f'INSERT INTO "{tbl}" ({quoted_cols}) VALUES ({placeholders})'
    count = 0
    try:
        cur = src.execute(f'SELECT {quoted_cols} FROM "{tbl}"')
        batch = []
        for row in cur:
            batch.append(tuple(row[c] for c in cols))
            if len(batch) >= 500:
                dst.executemany(ins, batch)
                count += len(batch)
                batch.clear()
        if batch:
            dst.executemany(ins, batch)
            count += len(batch)
        dst.commit()
        copy_report.append((tbl, 'ok', count, ''))
    except Exception as e:
        dst.commit()
        copy_report.append((tbl, 'error', count, repr(e)))

for r in indexes:
    try:
        dst.execute(r['sql'])
    except Exception as e:
        copy_report.append((r['name'], 'index_error', 0, repr(e)))

dst.commit()
check = dst.execute('PRAGMA integrity_check').fetchall()
print('COPY_REPORT_START')
for row in copy_report:
    print('\t'.join(map(str, row)))
print('COPY_REPORT_END')
print('INTEGRITY', check[:10])
print('DST', DST)
src.close()
dst.close()
