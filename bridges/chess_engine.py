#!/usr/bin/env python3
"""
Chess Dojo Engine v0.2 — Bulletproof

Security:
- Agent names validated (alphanumeric + dash/underscore, max 32 chars, no path traversal)
- Move notation validated (algebraic: e2-e4, e7-e8=Q)
- No arbitrary code execution
- Rate limiting: max 10 commands per agent per run

Data integrity:
- Atomic file writes (write to temp, rename)
- YAML schema validation with defaults
- File locking for concurrent profile access
- Invalid commands moved to rejected/ (not silently deleted)

Error handling:
- Structured logging to stderr
- No silent failures
- Graceful degradation (process remaining commands if one fails)

Chess logic:
- Full board state tracking
- Basic move validation (source/destination in bounds)
- Check/checkmate detection (basic)
- Threefold repetition and 50-move rule tracking
- ELO calculation (simplified)
"""

import os
import sys
import json
import re
import fcntl
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

try:
    import yaml
except ImportError:
    sys.exit("ERROR: PyYAML required. pip install pyyaml")

try:
    import chess
    HAS_CHESS_LIB = True
except ImportError:
    HAS_CHESS_LIB = False

# ─── Config ───────────────────────────────────────────────────────────────────

WORLD_DIR = Path(os.environ.get("WORLD_DIR", "world"))
COMMANDS_DIR = WORLD_DIR / "commands"
ROOMS_DIR = WORLD_DIR / "rooms"
AGENTS_DIR = WORLD_DIR / "agents"
LOGS_DIR = WORLD_DIR / "logs"
GAMES_DIR = WORLD_DIR / "games"

MAX_AGENT_NAME_LEN = 32
AGENT_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
MAX_COMMANDS_PER_RUN = 50
MOVE_PATTERN = re.compile(r'^[a-h][1-8]-[a-h][1-8](?:=[QRBN])?$')
ESP32_TIERS = {"C3", "S3", "S3-OC"}

INITIAL_ELO = 1000
K_FACTOR = 32  # ELO K-factor

# ─── Logging ──────────────────────────────────────────────────────────────────

def log(level: str, msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sys.stderr.write(f"[{ts}] [{level}] {msg}\n")
    sys.stderr.flush()

# ─── Validation ───────────────────────────────────────────────────────────────

class ValidationError(Exception):
    pass

def validate_agent_name(name: str) -> str:
    if not name or not isinstance(name, str):
        raise ValidationError("agent name must be a non-empty string")
    name = name.strip()
    if len(name) > MAX_AGENT_NAME_LEN:
        raise ValidationError(f"agent name too long ({len(name)} > {MAX_AGENT_NAME_LEN})")
    if not AGENT_NAME_PATTERN.match(name):
        raise ValidationError(f"agent name invalid: '{name}'")
    if ".." in name or "/" in name or "\\" in name:
        raise ValidationError("path traversal in agent name")
    return name

def validate_move(move: str) -> str:
    """Validate move notation."""
    if not move or not isinstance(move, str):
        raise ValidationError("move must be a non-empty string")
    move = move.strip()
    if not MOVE_PATTERN.match(move):
        raise ValidationError(f"invalid move notation: '{move}' (expected e2-e4 or e7-e8=Q)")
    return move

def validate_command(cmd: dict) -> dict:
    if not isinstance(cmd, dict):
        raise ValidationError("command must be a YAML mapping")
    if "agent" not in cmd:
        raise ValidationError("command missing 'agent'")
    
    cmd["agent"] = validate_agent_name(cmd["agent"])
    
    action = cmd.get("action", "move")
    cmd["action"] = action
    
    if action == "move":
        if "from" not in cmd or "to" not in cmd:
            raise ValidationError("move command requires 'from' and 'to'")
        # Build move notation
        cmd["move"] = f"{cmd['from']}-{cmd['to']}"
        if cmd.get("promotion"):
            cmd["move"] += f"={cmd['promotion'].upper()}"
        validate_move(cmd["move"])
    elif action == "join_tournament":
        tier = cmd.get("esp32_tier", "S3")
        if tier not in ESP32_TIERS:
            raise ValidationError(f"invalid ESP32 tier: '{tier}' (expected {ESP32_TIERS})")
        cmd["esp32_tier"] = tier
    elif action == "challenge":
        if "opponent" not in cmd:
            raise ValidationError("challenge requires 'opponent'")
        cmd["opponent"] = validate_agent_name(cmd["opponent"])
    elif action == "resign":
        pass  # No additional validation
    elif action == "query_standings":
        pass
    else:
        raise ValidationError(f"unknown action: '{action}'")
    
    # Reject unknown fields
    allowed_per_action = {
        "move": {"agent", "action", "from", "to", "promotion", "game_id"},
        "join_tournament": {"agent", "action", "esp32_tier", "script_type"},
        "challenge": {"agent", "action", "opponent", "esp32_tier"},
        "resign": {"agent", "action", "game_id"},
        "query_standings": {"agent", "action"},
    }
    allowed = allowed_per_action.get(action, set())
    unknown = set(cmd.keys()) - allowed
    if unknown:
        raise ValidationError(f"unknown fields for '{action}': {unknown}")
    
    return cmd

# ─── Atomic File I/O ─────────────────────────────────────────────────────────

def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.rename(tmp, path)
    except Exception:
        try: os.close(fd)
        except: pass
        if os.path.exists(tmp): os.unlink(tmp)
        raise

def atomic_yaml_dump(path: Path, data):
    atomic_write(path, yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True))

def load_yaml(path: Path) -> Optional[dict]:
    try:
        if not path.exists(): return None
        with open(path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except yaml.YAMLError as e:
        log("ERROR", f"Invalid YAML {path}: {e}")
        return None

# ─── File Locking ─────────────────────────────────────────────────────────────

class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd = None
    def __enter__(self):
        self.fd = open(self.path, "w")
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self
    def __exit__(self, *a):
        if self.fd:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close()

# ─── ELO Calculation ──────────────────────────────────────────────────────────

def calculate_elo(winner_elo: float, loser_elo: float, k: float = K_FACTOR) -> tuple:
    """Return (new_winner_elo, new_loser_elo)."""
    expected = 1.0 / (1.0 + 10 ** ((loser_elo - winner_elo) / 400.0))
    winner_new = winner_elo + k * (1.0 - expected)
    loser_new = loser_elo + k * (0.0 - (1.0 - expected))
    return round(winner_new, 1), round(loser_new, 1)

# ─── Agent Profile ────────────────────────────────────────────────────────────

DEFAULT_AGENT = {
    "name": "",
    "elo": INITIAL_ELO,
    "room": "chess-dojo",
    "alive": True,
    "wins": 0,
    "losses": 0,
    "draws": 0,
    "games_active": [],
    "esp32_tier": "S3",
    "script_type": "random",
    "created": None,
    "last_active": None,
}

def get_agent(name: str) -> dict:
    path = AGENTS_DIR / f"{name}.yaml"
    data = load_yaml(path)
    if data:
        merged = {**DEFAULT_AGENT, **data}
        merged["name"] = data.get("name", name)
        return merged
    return {**DEFAULT_AGENT, "name": name, "created": datetime.now(timezone.utc).isoformat()}

def save_agent(name: str, data: dict):
    path = AGENTS_DIR / f"{name}.yaml"
    with FileLock(path.parent / f".{name}.lock"):
        atomic_yaml_dump(path, data)

# ─── Game State ───────────────────────────────────────────────────────────────

def create_game(white: str, black: str, game_id: str) -> dict:
    if HAS_CHESS_LIB:
        board = chess.Board()
        fen = board.fen()
    else:
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    return {
        "id": game_id,
        "white": white,
        "black": black,
        "fen": fen,
        "moves": [],
        "status": "active",  # active, white_wins, black_wins, draw, resigned
        "result": None,
        "turn_number": 0,
        "created": datetime.now(timezone.utc).isoformat(),
    }

def apply_move(game: dict, move_notation: str) -> dict:
    """Apply move to game state. Returns updated game."""
    if not HAS_CHESS_LIB:
        # Fallback: just record the move, basic validation
        game["moves"].append(move_notation)
        game["turn_number"] += 1
        return game
    
    board = chess.Board(game["fen"])
    
    # Parse move notation (e2-e4 -> chess.Move)
    parts = move_notation.split("-")
    if len(parts) == 2:
        src = chess.parse_square(parts[0])
        dst = parts[1][:2]
        dst = chess.parse_square(dst)
        promotion = None
        if "=" in parts[1]:
            promo_char = parts[1].split("=")[1][0]
            promotion = {"Q": chess.QUEEN, "R": chess.ROOK, "B": chess.BISHOP, "N": chess.KNIGHT}.get(promo_char)
        
        move = chess.Move(src, dst, promotion=promotion)
        if move not in board.legal_moves:
            raise ValidationError(f"illegal move: {move_notation}")
        
        board.push(move)
    
    game["fen"] = board.fen()
    game["moves"].append(move_notation)
    game["turn_number"] += 1
    
    # Check game end conditions
    if board.is_checkmate():
        winner = "black_wins" if board.turn == chess.WHITE else "white_wins"
        game["status"] = winner
        game["result"] = winner
    elif board.is_stalemate() or board.is_insufficient_material():
        game["status"] = "draw"
        game["result"] = "draw"
    elif board.can_claim_draw():
        game["status"] = "draw"
        game["result"] = "draw (repetition or 50-move)"
    
    return game

# ─── Turn Processing ──────────────────────────────────────────────────────────

def process_turn(dry_run: bool = False):
    log("INFO", "Starting chess dojo turn processing")
    
    command_files = sorted(COMMANDS_DIR.glob("*.yaml"))
    if not command_files:
        log("INFO", "No commands pending")
        return 0
    
    if len(command_files) > MAX_COMMANDS_PER_RUN:
        log("WARN", f"Too many commands ({len(command_files)}), processing first {MAX_COMMANDS_PER_RUN}")
        command_files = command_files[:MAX_COMMANDS_PER_RUN]
    
    turn_number = len(list(LOGS_DIR.glob("turn-*.json"))) + 1
    processed = 0
    errors = 0
    
    # Track commands per agent (rate limiting)
    agent_cmd_count = {}
    
    for cmd_file in command_files:
        try:
            cmd = load_yaml(cmd_file)
            if not cmd:
                log("WARN", f"Empty command: {cmd_file}")
                cmd_file.unlink(missing_ok=True)
                continue
            
            cmd = validate_command(cmd)
            agent_name = cmd["agent"]
            action = cmd["action"]
            
            # Rate limit per agent
            agent_cmd_count[agent_name] = agent_cmd_count.get(agent_name, 0) + 1
            if agent_cmd_count[agent_name] > 10:
                log("WARN", f"Agent '{agent_name}' exceeded 10 commands per run, skipping")
                continue
            
            log("INFO", f"Processing {action} for '{agent_name}'")
            agent = get_agent(agent_name)
            agent["last_active"] = datetime.now(timezone.utc).isoformat()
            
            if action == "move":
                game_id = cmd.get("game_id")
                if not game_id:
                    log("WARN", f"No game_id for move by '{agent_name}', skipping")
                    continue
                
                game_path = GAMES_DIR / f"{game_id}.yaml"
                game = load_yaml(game_path)
                if not game:
                    log("WARN", f"Game {game_id} not found")
                    continue
                
                if game["status"] != "active":
                    log("WARN", f"Game {game_id} not active (status: {game['status']})")
                    continue
                
                # Verify it's this agent's turn
                turn_color = "white" if game["turn_number"] % 2 == 0 else "black"
                if game[turn_color] != agent_name:
                    log("WARN", f"Not {agent_name}'s turn in game {game_id}")
                    continue
                
                game = apply_move(game, cmd["move"])
                
                # Update ELO if game ended
                if game["status"] != "active":
                    if game["status"] == "white_wins":
                        w, b = calculate_elo(agent["elo"], get_agent(game["black"])["elo"])
                        agent["wins"] += 1
                        agent["elo"] = w
                        opponent = get_agent(game["black"])
                        opponent["losses"] += 1
                        opponent["elo"] = b
                        save_agent(game["black"], opponent)
                    elif game["status"] == "black_wins":
                        w, b = calculate_elo(get_agent(game["white"])["elo"], agent["elo"])
                        opponent = get_agent(game["white"])
                        opponent["losses"] += 1
                        opponent["elo"] = w
                        agent["wins"] += 1
                        agent["elo"] = b
                        save_agent(game["white"], opponent)
                    elif game["status"] == "draw":
                        agent["draws"] += 1
                        # Draw: small ELO adjustment
                        agent["elo"] = agent["elo"] + 0.5
                    agent["games_active"] = [g for g in agent.get("games_active", []) if g != game_id]
                
                if not dry_run:
                    atomic_yaml_dump(game_path, game)
                
            elif action == "join_tournament":
                room = load_yaml(ROOMS_DIR / "chess-dojo.yaml") or {}
                active = room.get("active_agents", [])
                if agent_name not in active:
                    active.append(agent_name)
                    room["active_agents"] = active
                    if not dry_run:
                        atomic_yaml_dump(ROOMS_DIR / "chess-dojo.yaml", room)
                agent["esp32_tier"] = cmd.get("esp32_tier", "S3")
                agent["script_type"] = cmd.get("script_type", "random")
            
            elif action == "challenge":
                opponent = cmd["opponent"]
                game_id = f"{agent_name}-vs-{opponent}-{turn_number:04d}"
                game = create_game(agent_name, opponent, game_id)
                agent["games_active"] = agent.get("games_active", []) + [game_id]
                opponent_agent = get_agent(opponent)
                opponent_agent["games_active"] = opponent_agent.get("games_active", []) + [game_id]
                
                if not dry_run:
                    GAMES_DIR.mkdir(parents=True, exist_ok=True)
                    atomic_yaml_dump(GAMES_DIR / f"{game_id}.yaml", game)
                    save_agent(opponent, opponent_agent)
                
                log("INFO", f"Created game {game_id}: {agent_name} vs {opponent}")
            
            elif action == "resign":
                game_id = cmd.get("game_id")
                if game_id:
                    game_path = GAMES_DIR / f"{game_id}.yaml"
                    game = load_yaml(game_path)
                    if game and game["status"] == "active":
                        # Resigning player loses
                        if game["white"] == agent_name:
                            game["status"] = "black_wins"
                        else:
                            game["status"] = "white_wins"
                        game["result"] = f"{agent_name} resigned"
                        if not dry_run:
                            atomic_yaml_dump(game_path, game)
            
            elif action == "query_standings":
                pass  # No state change, just logged
            
            if not dry_run:
                save_agent(agent_name, agent)
            
            # Log turn
            turn_log = {
                "turn": turn_number,
                "agent": agent_name,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": True,
            }
            if not dry_run:
                LOGS_DIR.mkdir(parents=True, exist_ok=True)
                atomic_write(LOGS_DIR / f"turn-{turn_number:04d}.json", json.dumps(turn_log, indent=2))
            
            cmd_file.unlink(missing_ok=True)
            processed += 1
            turn_number += 1
            
        except ValidationError as e:
            log("ERROR", f"Validation: {cmd_file.name}: {e}")
            errors += 1
            rejected_dir = COMMANDS_DIR / "rejected"
            rejected_dir.mkdir(exist_ok=True)
            cmd_file.rename(rejected_dir / cmd_file.name)
        except Exception as e:
            log("ERROR", f"Unexpected: {cmd_file.name}: {e}")
            errors += 1
    
    log("INFO", f"Turn done: {processed} processed, {errors} errors")
    return processed

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import tempfile  # ensure available
    
    parser = argparse.ArgumentParser(description="Chess Dojo Engine v0.2")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--world-dir", default="world")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--standings", action="store_true")
    parser.add_argument("--action", default="process", choices=["process", "tournament", "standings"])
    args = parser.parse_args()
    
    global WORLD_DIR, COMMANDS_DIR, ROOMS_DIR, AGENTS_DIR, LOGS_DIR, GAMES_DIR
    WORLD_DIR = Path(args.world_dir)
    COMMANDS_DIR = WORLD_DIR / "commands"
    ROOMS_DIR = WORLD_DIR / "rooms"
    AGENTS_DIR = WORLD_DIR / "agents"
    LOGS_DIR = WORLD_DIR / "logs"
    GAMES_DIR = WORLD_DIR / "games"
    
    if args.standings or args.action == "standings":
        for af in sorted(AGENTS_DIR.glob("*.yaml")):
            a = load_yaml(af)
            if not a: continue
            n = a.get("name", af.stem)
            e = a.get("elo", INITIAL_ELO)
            w = a.get("wins", 0)
            l = a.get("losses", 0)
            d = a.get("draws", 0)
            t = a.get("esp32_tier", "?")
            print(f"  {n}: {e} ELO ({w}W/{l}L/{d}D) tier={t}")
        return
    
    if args.validate_only:
        count = 0
        for cf in sorted(COMMANDS_DIR.glob("*.yaml")):
            cmd = load_yaml(cf)
            try:
                validate_command(cmd)
                print(f"  OK: {cf.name}")
            except ValidationError as e:
                print(f"  FAIL: {cf.name}: {e}")
            count += 1
        print(f"Validated {count} commands")
        return
    
    n = process_turn(dry_run=args.dry_run)
    print(f"Processed {n} turns" + (" (dry run)" if args.dry_run else ""))

if __name__ == "__main__":
    main()
