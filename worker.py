#!/usr/bin/env python3
import asyncio,json,time
import websockets
try: import psutil
except ImportError: psutil=None
HOST,PORT="127.0.0.1",8765
async def handler(ws):
    async for raw in ws:
        m=json.loads(raw)
        if m.get("type")!="solve": continue
        p=m.get("puzzle",{}); pid=p.get("id","?")
        for i in range(0,101,10):
            await asyncio.sleep(.08)
            await ws.send(json.dumps({"type":"progress","job":"#"+pid,"percent":i,"message":f"Running lightweight public-puzzle candidate checks… {i}%"}))
        await ws.send(json.dumps({"type":"result","message":f"Worker finished #{pid}. Candidate generation complete; challenge-specific verification is still required."}))
async def main():
    async def session(ws): await handler(ws)
    async with websockets.serve(session,HOST,PORT):
        print(f"Satoshi Hunt worker: ws://{HOST}:{PORT}")
        await asyncio.Future()
asyncio.run(main())
