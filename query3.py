import sqlite3
c = sqlite3.connect('/data/app.db')
c.execute('UPDATE music SET analysis_status = "error", analysis_error = "Server was restarted during analysis. Please delete this track and re-upload." WHERE analysis_status = "analyzing";')
c.commit()
print("Updated stuck tracks.")
