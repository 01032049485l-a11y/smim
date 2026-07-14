"""로컬 미리보기 서버.  python tools/serve.py  →  http://localhost:8000"""
import os, sys, functools, http.server, socketserver
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
os.chdir(config.SITE_DIR)
H = functools.partial(http.server.SimpleHTTPRequestHandler)
with socketserver.TCPServer(("", 8000), H) as s:
    print("SMIM preview → http://localhost:8000  (Ctrl+C 종료)")
    s.serve_forever()
