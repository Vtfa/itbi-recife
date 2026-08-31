import os
import sys
import webbrowser
import threading
import time
from scripts.app_servidor import run_server

def open_browser():
    time.sleep(1.2)
    print("Abrindo navegador em http://localhost:8050...")
    webbrowser.open('http://localhost:8050')

if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    run_server(8050)
