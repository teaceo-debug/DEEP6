import sqlite3
path=r'/mnt/c/Users/Tea/Documents/NinjaTrader 8/db/NinjaTrader.sqlite'
con=sqlite3.connect(path)
con.execute('PRAGMA foreign_keys=OFF')
cur=con.cursor()
classname='NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy'
ids=[row[0] for row in cur.execute('SELECT Id FROM Strategies WHERE Classname=?',(classname,))]
print('deep6strategy ids', len(ids))
if ids:
    cur.execute('CREATE TEMP TABLE IF NOT EXISTS _purge_ids(id INTEGER PRIMARY KEY)')
    cur.executemany('INSERT OR IGNORE INTO _purge_ids(id) VALUES (?)', [(i,) for i in ids])
    for table,col in [
        ('Strategy2Account','Strategy'),
        ('Strategy2Execution','Strategy'),
        ('Strategy2Instrument','Strategy'),
        ('Strategy2Order','Strategy')
    ]:
        cur.execute(f'DELETE FROM {table} WHERE {col} IN (SELECT id FROM _purge_ids)')
        print(table, 'deleted', cur.rowcount)
    cur.execute('DELETE FROM Strategies WHERE Id IN (SELECT id FROM _purge_ids)')
    print('Strategies deleted', cur.rowcount)
con.commit()
print('remaining deep6strategy', cur.execute('SELECT COUNT(*) FROM Strategies WHERE Classname=?',(classname,)).fetchone()[0])
print('integrity', cur.execute('PRAGMA integrity_check').fetchall()[:5])
con.close()
