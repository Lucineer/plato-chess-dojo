"""Chess engine bridge for git-native MUD.
Reads world/commands/*.yaml, processes chess moves, updates world/ state.
Compatible with SuperInstance/git-native-mud protocol.
"""
import os, sys, glob, random, yaml, json
from datetime import datetime, timezone

WORLD = "world"
COMMANDS = f"{WORLD}/commands"
ROOMS = f"{WORLD}/rooms"
AGENTS = f"{WORLD}/agents"
LOGS = f"{WORLD}/logs"

def load(path):
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except: return {}

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def get_turn_number():
    logs = sorted(glob.glob(f"{LOGS}/turn-*.md"))
    return len(logs) + 1

def process_commands():
    """Process pending agent commands."""
    commands = {}
    for cmdf in glob.glob(f"{COMMANDS}/*.yaml"):
        agent_id = os.path.basename(cmdf).removesuffix(".yaml")
        cmd = load(cmdf)
        if cmd:
            commands[agent_id] = cmd
    
    if not commands:
        print("No commands pending. Exiting.")
        return False
    
    turn = get_turn_number()
    log_lines = [f"# Chess Dojo — Turn {turn}\n",
                 f"**Time**: {datetime.now(timezone.utc).isoformat()}\n",
                 f"**Agents acting**: {', '.join(commands.keys())}\n"]
    
    # Load room state
    room = load(f"{ROOMS}/chess-dojo.yaml")
    
    for agent_id, cmd in commands.items():
        agent = load(f"{AGENTS}/{agent_id}.yaml")
        if not agent or not agent.get("alive", True):
            log_lines.append(f"\n## {agent_id}: SKIPPED (not alive)")
            continue
        
        action = cmd.get("action", "move")
        log_lines.append(f"\n## {agent_id}: {action}")
        
        if action == "move":
            fr = cmd.get("from", "?")
            to = cmd.get("to", "?")
            log_lines.append(f"- Move: {fr} → {to}")
            # Move validation would go here in full engine
            # For now, log the move
            
        elif action == "join_tournament":
            tier = cmd.get("esp32_tier", "S3")
            script = cmd.get("script_type", "random")
            log_lines.append(f"- Joined tournament (tier={tier}, script={script})")
            if agent_id not in room.get("active_games", []):
                room.setdefault("active_games", []).append(agent_id)
        
        elif action == "query_standings":
            log_lines.append(f"- ELO: {agent.get('elo', 1000)}")
            log_lines.append(f"- Record: {agent.get('wins',0)}W {agent.get('losses',0)}L {agent.get('draws',0)}D")
        
        # Remove processed command
        cmdf = f"{COMMANDS}/{agent_id}.yaml"
        if os.path.exists(cmdf):
            os.remove(cmdf)
    
    # Save updated room
    save(f"{ROOMS}/chess-dojo.yaml", room)
    
    # Save turn log
    log_lines.append(f"\n---\n*Processed by Chess Dojo Engine via GitHub Actions*")
    save(f"{LOGS}/turn-{turn:03d}.md", {"content": "\n".join(log_lines)})
    
    print(f"Turn {turn} processed. {len(commands)} agents acted.")
    return True

if __name__ == "__main__":
    action = os.environ.get("ACTION", "process")
    if action == "process":
        if not process_commands():
            sys.exit(0)
    elif action == "standings":
        print("Standings:")
        for af in sorted(glob.glob(f"{AGENTS}/*.yaml")):
            a = load(af)
            name = a.get("name", "?")
            elo = a.get("elo", 1000)
            w = a.get("wins", 0)
            l = a.get("losses", 0)
            d = a.get("draws", 0)
            print(f"  {name}: {elo} ELO ({w}W/{l}L/{d}D)")
