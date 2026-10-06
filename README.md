# Satoshi Hunt

Satoshi Hunt is a lightweight public-puzzle intelligence dashboard with an optional local CPU worker.

## Architecture
The website is the control center. A small local worker can connect over localhost and execute lightweight candidate-generation jobs on the user's machine.

## Run local worker
Python 3.10+:
```bash
pip install websockets psutil
python worker.py
```
Then open the website.

## Scope
Only use for publicly published reward puzzles/challenges that explicitly authorize solvers. An empty address balance does not by itself prove that a puzzle was solved. This project is not an ordinary Bitcoin wallet/private-key cracker.
