import os
import hashlib, math
import base64
import hmac
import re
import json
import logging
import secrets
import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import jwt
import psycopg
import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from verifier import verify_candidate_hash
from settlement import build_reward_event
from protocol_v1 import proof_hash, capability_score, adaptive_ranges, reliability_score, economic_priority
from anti_cheat import security_flags, reputation_score
from payouts import validate_external_txid
from owner_config import OWNER_PLATFORM_FEE_BTC_ADDRESS
from challenge_adapters import runtime_contract
