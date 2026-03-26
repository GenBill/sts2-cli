#!/usr/bin/env python3
"""
Reusable client for sts2-cli headless engine.

Wraps the stdin/stdout JSON protocol exposed by src/Sts2Headless.
Designed for Telegram / web / remote control adapters.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

from game_log import GameLogger
from play import ensure_setup, DOTNET, PROJECT


JsonDict = Dict[str, Any]


@dataclass
class RunConfig:
    character: str = "Ironclad"
    ascension: int = 0
    seed: Optional[str] = None
    lang: str = "zh"
    log: bool = True


class HeadlessClient:
    def __init__(self, config: RunConfig):
        self.config = config
        self.proc: Optional[subprocess.Popen[str]] = None
        self.state: Optional[JsonDict] = None
        self.logger: Optional[GameLogger] = None
        self.seed = config.seed or f"tg_{random.randint(1000, 9999)}"

    def start(self) -> JsonDict:
        ensure_setup()
        self.logger = GameLogger(self.config.character, self.seed, enabled=self.config.log)
        self.proc = subprocess.Popen(
            [DOTNET, "run", "--no-build", "--project", PROJECT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        ready = self._read()
        if not ready:
            raise RuntimeError("failed to start headless simulator")
        self.state = self.send(
            {
                "cmd": "start_run",
                "character": self.config.character,
                "seed": self.seed,
                "ascension": self.config.ascension,
                "lang": self.config.lang,
            }
        )
        return self.state

    def _read(self) -> Optional[JsonDict]:
        if not self.proc or not self.proc.stdout:
            return None
        while True:
            line = self.proc.stdout.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                resp = json.loads(line)
                if self.logger:
                    self.logger.log_state(resp)
                return resp

    def send(self, cmd: JsonDict) -> JsonDict:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("process not started")
        if self.logger:
            self.logger.log_action(cmd)
        self.proc.stdin.write(json.dumps(cmd) + "\n")
        self.proc.stdin.flush()
        resp = self._read()
        if not resp:
            raise RuntimeError("no response from simulator")
        self.state = resp
        return resp

    def action(self, action: str, args: Optional[JsonDict] = None) -> JsonDict:
        payload: JsonDict = {"cmd": "action", "action": action}
        if args:
            payload["args"] = args
        return self.send(payload)

    def get_map(self) -> JsonDict:
        return self.send({"cmd": "get_map"})

    def close(self):
        try:
            if self.proc and self.proc.stdin:
                self.proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                self.proc.stdin.flush()
        except Exception:
            pass
        try:
            if self.proc:
                self.proc.terminate()
                self.proc.wait(timeout=5)
        except Exception:
            try:
                if self.proc:
                    self.proc.kill()
            except Exception:
                pass
        if self.logger:
            self.logger.close()


class SessionStore:
    """Simple in-memory session store for one-process Telegram bot."""

    def __init__(self):
        self._sessions: dict[str, HeadlessClient] = {}

    def has(self, key: str) -> bool:
        return key in self._sessions

    def get(self, key: str) -> Optional[HeadlessClient]:
        return self._sessions.get(key)

    def create(self, key: str, config: RunConfig) -> HeadlessClient:
        old = self._sessions.get(key)
        if old:
            old.close()
        cli = HeadlessClient(config)
        cli.start()
        self._sessions[key] = cli
        return cli

    def close(self, key: str):
        cli = self._sessions.pop(key, None)
        if cli:
            cli.close()
