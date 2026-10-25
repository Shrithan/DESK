"""Start all four DESK agents in one process.

    Terminal 1:  python -m agents.run specialists
    Terminal 2:  python -m agents.run coach
    (prefix both with DESK_DEMO_MODE=1 for a simulated player, no cameras needed)

Only the Coach is exposed to ASI:One (through an Agentverse mailbox). The
Setup, Tuning and Doctor agents talk to the Coach with agent messages.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import sys
from pathlib import Path

from uagents import Bureau

from uagents.crypto import Identity

from agents.coach import build_coach
from agents.local_resolver import LocalFirstResolver
from agents.specialists import HANDLERS, build_specialists

SEED_FILE = Path(__file__).with_name(".seed")


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def seed_base() -> str:
    """Stable secret seed: DESK_AGENT_SEED, else a random one saved to agents/.seed (gitignored)."""
    if os.environ.get("DESK_AGENT_SEED"):
        return os.environ["DESK_AGENT_SEED"]
    if not SEED_FILE.exists():
        SEED_FILE.write_text(secrets.token_hex(24))
        SEED_FILE.chmod(0o600)
    return SEED_FILE.read_text().strip()


def build_specialist_bureau() -> Bureau:
    """Setup, Tuning and Doctor agents together on one local port (default 8000)."""
    base = seed_base()
    coach_port = int(os.environ.get("DESK_COACH_PORT", "8001"))
    coach_addr = Identity.from_seed(f"{base}-coach", 0).address
    specialists = build_specialists(base, LocalFirstResolver({coach_addr: f"http://127.0.0.1:{coach_port}/submit"}))
    port = int(os.environ.get("DESK_AGENT_PORT", "8000"))
    for role, a in specialists.items():
        logging.getLogger("desk").info("%s agent address: %s", role, a.address)
    return Bureau(agents=list(specialists.values()), port=port, endpoint=[f"http://127.0.0.1:{port}/submit"])


def build_standalone_coach():
    """The Coach runs alone (Agentverse's Inspector can't connect a mailbox to a Bureau)."""
    base = seed_base()
    # Constructing Agent objects here registers local dispatcher sinks, which
    # silently swallow Coach messages intended for the separate Bureau.
    specialists = {role: Identity.from_seed(f"{base}-{role}", 0).address for role in HANDLERS}
    mailbox = os.environ.get("DESK_NO_MAILBOX", "").lower() not in ("1", "true", "yes")
    port = int(os.environ.get("DESK_COACH_PORT", "8001"))
    spec_port = int(os.environ.get("DESK_AGENT_PORT", "8000"))
    local = {address: f"http://127.0.0.1:{spec_port}/submit" for address in specialists.values()}
    # testing hook: DESK_EXTRA_LOCAL="agent1...=http://127.0.0.1:8009/submit,..."
    for pair in filter(None, os.environ.get("DESK_EXTRA_LOCAL", "").split(",")):
        addr, url = pair.split("=", 1)
        local[addr.strip()] = url.strip()
    coach = build_coach(f"{base}-coach", specialists, mailbox=mailbox, port=port,
                        resolve=LocalFirstResolver(local))
    logging.getLogger("desk").info("DESK Coach address: %s", coach.address)
    logging.getLogger("desk").info(
        "Connect the mailbox here: https://agentverse.ai/inspect/?uri=http%%3A//127.0.0.1%%3A%d&address=%s", port, coach.address)
    return coach


def main() -> None:
    # Python 3.12+/3.14 no longer auto-creates an event loop; uagents needs one at Agent() creation.
    asyncio.set_event_loop(asyncio.new_event_loop())
    _load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    demo = " in DEMO MODE (simulated player)" if os.environ.get("DESK_DEMO_MODE") else ""
    if role == "coach":
        print("DESK Coach starting" + demo)
        build_standalone_coach().run()
    elif role == "specialists":
        print("DESK Setup/Tuning/Doctor agents starting" + demo)
        build_specialist_bureau().run()
    else:
        run_all()


def run_all() -> None:
    """One command: (fake player if DESK_DEMO_MODE) + specialists + coach, each in its own process."""
    import subprocess
    import time

    env = dict(os.environ)
    procs = []
    if env.pop("DESK_DEMO_MODE", "").lower() in ("1", "true", "yes"):
        print("Starting simulated player...")
        procs.append(subprocess.Popen([sys.executable, "-m", "agents.demo_desk"], env=env))
        time.sleep(1.5)
    procs.append(subprocess.Popen([sys.executable, "-m", "agents.run", "specialists"], env=env))
    time.sleep(1.5)
    procs.append(subprocess.Popen([sys.executable, "-m", "agents.run", "coach"], env=env))
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
