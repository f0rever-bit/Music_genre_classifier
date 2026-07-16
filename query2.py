import sqlite3
c = sqlite3.connect('/data/app.db')
print(c.execute('SELECT id, source, analysis_status, substr(analysis_error, 1, 100) FROM music ORDER BY id DESC LIMIT 5;').fetchall())
