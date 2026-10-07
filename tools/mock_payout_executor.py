#!/usr/bin/env python3
"""Deterministic staging-only payout executor.

This is deliberately not a Bitcoin signer. It returns a fake external reference
so the Satoshi Hunt payout state machine can be tested end-to-end without funds.
"""
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer

PREFIX=os.environ.get("MOCK_PAYOUT_TX_PREFIX","staging-mock-")
PORT=int(os.environ.get("MOCK_PAYOUT_PORT","8765"))

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length=int(self.headers.get("Content-Length","0"))
        body=json.loads(self.rfile.read(length) or b"{}")
        if not body.get("withdrawal_id") or not body.get("amount_btc") or not body.get("payout_address"):
            self.send_response(400); self.end_headers(); return
        txid=PREFIX+body["withdrawal_id"].replace("-","")[:24]
        payload=json.dumps({"txid":txid,"mode":"staging-mock","custody":"none"}).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers(); self.wfile.write(payload)
    def log_message(self,*args): pass

if __name__=="__main__":
    HTTPServer(("127.0.0.1",PORT),Handler).serve_forever()
