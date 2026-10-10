"""Talks to Vesktop over the Chrome DevTools Protocol, running helpers from bridge.js in the page."""

import asyncio
import hashlib
import json
import threading
import urllib.request
from pathlib import Path

import websockets

EVENT_BINDING = "__vesktopOverlayEvent"


class VesktopBridge:
    """Runs helper functions from bridge.js inside Vesktop via the Chrome DevTools Protocol."""

    def __init__(self, port):
        self.port = port
        js = Path(__file__).with_name("bridge.js").read_text()
        # Cache key changes whenever bridge.js does, so edits take effect without a Vesktop reload.
        self.cache_key = "__vesktopOverlay_" + hashlib.sha1(js.encode()).hexdigest()[:10]
        self.js = js
        self.ws = None
        self.pending = {}
        self.next_id = 0
        self.on_event = None  # called (on the bridge's thread) with each pushed event's JSON
        self.connect_lock = None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def port_open(self):
        try:
            self._page_ws_url()
            return True
        except Exception:
            return False

    def _page_ws_url(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=1) as resp:
            tabs = json.load(resp)
        for tab in tabs:
            if tab.get("type") == "page" and "discord.com" in tab.get("url", ""):
                return tab["webSocketDebuggerUrl"]
        raise ConnectionError("Discord page not found in Vesktop")

    async def _connect(self):
        if self.connect_lock is None:
            self.connect_lock = asyncio.Lock()
        async with self.connect_lock:
            if self.ws is not None:
                return
            url = await self.loop.run_in_executor(None, self._page_ws_url)
            ws = await websockets.connect(url, max_size=None, ping_interval=None)
            self.ws = ws
            self.loop.create_task(self._read(ws))
            # bridge.js calls window.<EVENT_BINDING>(json) to push changes (e.g. typing) the moment they
            # happen; they arrive below as Runtime.bindingCalled. Bindings survive page reloads.
            self.next_id += 1
            await ws.send(json.dumps({"id": self.next_id, "method": "Runtime.addBinding",
                                      "params": {"name": EVENT_BINDING}}))

    async def _read(self, ws):
        try:
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("method") == "Runtime.bindingCalled":
                    params = msg.get("params", {})
                    if params.get("name") == EVENT_BINDING and self.on_event:
                        self.on_event(params.get("payload", ""))
                    continue
                fut = self.pending.pop(msg.get("id"), None)
                if fut and not fut.done():
                    fut.set_result(msg)
        except websockets.ConnectionClosed:
            pass
        finally:
            if self.ws is ws:
                self.ws = None
                for fut in self.pending.values():
                    if not fut.done():
                        fut.set_exception(ConnectionError("Lost connection to Vesktop"))
                self.pending.clear()

    async def _evaluate(self, expression, timeout):
        if self.ws is None:
            await self._connect()
        self.next_id += 1
        msg_id = self.next_id
        fut = self.loop.create_future()
        self.pending[msg_id] = fut
        await self.ws.send(json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True, "awaitPromise": True},
        }))
        try:
            msg = await asyncio.wait_for(fut, timeout)
        finally:
            self.pending.pop(msg_id, None)
        if "error" in msg:
            raise RuntimeError(msg["error"].get("message", "DevTools error"))
        result = msg["result"]
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            raise RuntimeError(details.get("exception", {}).get("description") or details.get("text"))
        return result["result"].get("value")

    def call(self, method, *args, timeout=10):
        """Call a bridge.js helper; returns a concurrent.futures.Future."""
        arg_list = ", ".join(json.dumps(a) for a in args)
        expression = f"(window.{self.cache_key} ??= {self.js}).{method}({arg_list})"
        return asyncio.run_coroutine_threadsafe(self._evaluate(expression, timeout), self.loop)
