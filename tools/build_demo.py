"""가짜 데이터로 사이트 전체를 빌드한다 (API 비용 0원).
    python tools/build_demo.py && python tools/serve.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
config.SNAPSHOT_DIR = os.path.join(config.DATA_DIR, "demo", "snapshots")
import pipeline.ledger as ledger
ledger.LEDGER = os.path.join(config.DATA_DIR, "demo", "ledger.json")
from render import build
build.build_site()
print("→ python tools/serve.py 로 확인")
