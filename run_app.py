"""
Streamlit launcher — fixes Python 3.14 + Windows asyncio crash.

Python 3.14 on Windows uses ProactorEventLoop by default. When a browser tab
refreshes or the WebSocket is dropped abruptly, asyncio raises:
    ConnectionResetError: [WinError 10054] An existing connection was
    forcibly closed by the remote host
inside _ProactorBasePipeTransport._call_connection_lost(), which propagates
up through Uvicorn and kills the whole server.

Switching to WindowsSelectorEventLoopPolicy before Streamlit starts its event
loop prevents this crash. Run with: python run_app.py
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from streamlit.web import cli as stcli  # noqa: E402

sys.argv = ["streamlit", "run", "app.py"]
sys.exit(stcli.main())
