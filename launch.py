import os, runpy
from pathlib import Path
if not os.environ.get('ADMIN_PASSWORD') or len(os.environ['ADMIN_PASSWORD']) < 12:
    raise SystemExit('Set ADMIN_PASSWORD in the hosting dashboard (at least 12 characters).')
os.environ.setdefault('HOST','0.0.0.0')
os.environ.setdefault('COOKIE_SECURE','1')
runpy.run_path(str(Path(__file__).with_name('server.py')),run_name='__main__')
