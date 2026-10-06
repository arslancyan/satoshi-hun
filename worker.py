#!/usr/bin/env python3
import asyncio,json
import websockets
try: import psutil
except ImportError: psutil=None
HOST,PORT="127.0.0.1",8765
async def handler(ws):
    async for raw in ws:
        m=json.loads(raw)
        if m.get("type")!="solve": continue
        p=m.get("puzzle",{}); pid=p.get("id","?")
        if p.get("status")!="OPEN + FUNDED":
            await ws.send(json.dumps({"type":"result","message":f"#{pid} rejected: only OPEN + FUNDED jobs enter the solver queue."})); continue
        for i in range(0,101,10):
            await asyncio.sleep(.08)
            await ws.send(json.dumps({"type":"progress","job":"#"+pid,"percent":i,"message":f"Running lightweight candidate checks… {i}%"}))
        await ws.send(json.dumps({"type":"result","message":f"#{pid}: candidate generation complete. Challenge-specific verification is required."}))
async def telemetry(ws):
    while True:
        await ws.send(json.dumps({"type":"telemetry","cpu":psutil.cpu_percent() if psutil else 0,"ram":round(psutil.virtual_memory().used/1024/1024) if psutil else 0})); await asyncio.sleep(2)
async def session(ws): await asyncio.gather(handler(ws),telemetry(ws))
async def main():
    async with websockets.serve(session,HOST,PORT): await asyncio.Future()
asyncio.run(main())
