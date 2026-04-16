#!/usr/bin/env python3
"""
ct-chess — Constraint Theory Chess Dojo
Text-based chess for PLATO-OS agent sparring.
Two players with configurable models, time controls, and ESP32 constraints.
Scripts play autonomously. Results tracked. Losers adapt.
"""
import time, random, copy, json, sys, os

# ═══════════════════════════════════════════════════════════
# BOARD REPRESENTATION
# ═══════════════════════════════════════════════════════════
PIECES = {
    'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
    'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟',
}
EMPTY = '·'

INITIAL_BOARD = [
    ['r','n','b','q','k','b','n','r'],
    ['p','p','p','p','p','p','p','p'],
    ['·','·','·','·','·','·','·','·'],
    ['·','·','·','·','·','·','·','·'],
    ['·','·','·','·','·','·','·','·'],
    ['·','·','·','·','·','·','·','·'],
    ['P','P','P','P','P','P','P','P'],
    ['R','N','B','Q','K','B','N','R'],
]

def is_white(p): return p.isupper()
def is_black(p): return p.islower()
def piece_color(p): return 'w' if p.isupper() else 'b' if p.islower() else None
def in_bounds(r, c): return 0 <= r < 8 and 0 <= c < 8

def render(board, last_move=None):
    """Render board as text"""
    lines = []
    lines.append("    a  b  c  d  e  f  g  h")
    lines.append("  ╔════════════════════════════╗")
    for r in range(8):
        row_str = f"{8-r} ║"
        for c in range(8):
            p = board[r][c]
            if last_move and last_move[0] == r and last_move[1] == c:
                row_str += f"\033[7m{PIECES.get(p, EMPTY):2s}\033[0m║"
            else:
                row_str += f"{PIECES.get(p, EMPTY):2s}║"
        row_str += f" {8-r}"
        lines.append(row_str)
        if r < 7:
            lines.append("  ╠══════════════════════════╣")
    lines.append("  ╚══════════════════════════╝")
    lines.append("    a  b  c  d  e  f  g  h")
    return '\n'.join(lines)

def parse_pos(s):
    """e.g. 'e2' -> (6, 4)"""
    if len(s) != 2: return None
    c = ord(s[0]) - ord('a')
    r = 8 - int(s[1])
    if in_bounds(r, c): return (r, c)
    return None

def pos_to_str(r, c):
    return chr(ord('a') + c) + str(8 - r)

# ═══════════════════════════════════════════════════════════
# MOVE GENERATION (simplified — no en passant, no castling yet)
# ═══════════════════════════════════════════════════════════
def get_moves(board, r, c):
    """Get legal moves for piece at (r,c)"""
    p = board[r][c]
    if p == EMPTY: return []
    color = piece_color(p)
    moves = []
    pt = p.upper()
    
    def add_if_valid(tr, tc):
        if in_bounds(tr, tc):
            target = board[tr][tc]
            if target == EMPTY or piece_color(target) != color:
                moves.append((tr, tc))
            return target == EMPTY  # can continue sliding
        return False
    
    if pt == 'P':
        d = -1 if color == 'w' else 1
        start = 6 if color == 'w' else 1
        # Forward
        if in_bounds(r+d, c) and board[r+d][c] == EMPTY:
            moves.append((r+d, c))
            if r == start and board[r+2*d][c] == EMPTY:
                moves.append((r+2*d, c))
        # Captures
        for dc in [-1, 1]:
            if in_bounds(r+d, c+dc) and board[r+d][c+dc] != EMPTY:
                if piece_color(board[r+d][c+dc]) != color:
                    moves.append((r+d, c+dc))
    elif pt == 'N':
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            add_if_valid(r+dr, c+dc)
    elif pt == 'B':
        for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
            for i in range(1, 8):
                if not add_if_valid(r+dr*i, c+dc*i): break
    elif pt == 'R':
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            for i in range(1, 8):
                if not add_if_valid(r+dr*i, c+dc*i): break
    elif pt == 'Q':
        for dr, dc in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
            for i in range(1, 8):
                if not add_if_valid(r+dr*i, c+dc*i): break
    elif pt == 'K':
        for dr in [-1,0,1]:
            for dc in [-1,0,1]:
                if dr == 0 and dc == 0: continue
                add_if_valid(r+dr, c+dc)
    return moves

def get_all_moves(board, color):
    """Get all moves for a color"""
    moves = []
    for r in range(8):
        for c in range(8):
            if piece_color(board[r][c]) == color:
                for tr, tc in get_moves(board, r, c):
                    moves.append((r, c, tr, tc))
    return moves

def find_king(board, color):
    k = 'K' if color == 'w' else 'k'
    for r in range(8):
        for c in range(8):
            if board[r][c] == k:
                return (r, c)
    return None

def is_in_check(board, color):
    """Is color's king in check?"""
    king = find_king(board, color)
    if not king: return True
    opp = 'b' if color == 'w' else 'w'
    for r in range(8):
        for c in range(8):
            if piece_color(board[r][c]) == opp:
                if king in [(mr, mc) for mr, mc in get_moves(board, r, c)]:
                    return True
    return False

def make_move(board, fr, fc, tr, tc):
    """Returns new board after move"""
    b = copy.deepcopy(board)
    p = b[fr][fc]
    b[tr][tc] = p
    b[fr][fc] = EMPTY
    # Pawn promotion
    if p.upper() == 'P' and (tr == 0 or tr == 7):
        b[tr][tc] = 'Q' if p.isupper() else 'q'
    return b

# ═══════════════════════════════════════════════════════════
# ESP32-CONSTRAINED SCRIPTABLE PLAYERS
# ═══════════════════════════════════════════════════════════

class ESP32Constraint:
    """Simulates ESP32 resource limits"""
    def __init__(self, name="ESP32-S3", flash_kb=4096, sram_kb=520, budget_tokens=500):
        self.name = name
        self.flash_kb = flash_kb
        self.sram_kb = sram_kb
        self.budget_tokens = budget_tokens  # tokens per move decision
        self.tokens_used = 0
        self.total_tokens = 0
        self.script_size_bytes = 0
    
    def check(self, script_bytes):
        """Can this script fit?"""
        self.script_size_bytes = script_bytes
        return script_bytes <= (self.flash_kb * 1024 * 0.8)  # 80% flash for script
    
    def spend(self, tokens):
        """Spend thinking tokens"""
        self.tokens_used = tokens
        self.total_tokens += tokens
        if tokens > self.budget_tokens:
            return False  # over budget — forced move
        return True

class ScriptedPlayer:
    """A player that runs a constrained script to choose moves.
    
    The script is a simple decision function that must fit in ESP32 flash.
    This is the Greenhorn concept: distilled chess instinct.
    """
    def __init__(self, name, color, esp32, script_fn):
        self.name = name
        self.color = color  # 'w' or 'b'
        self.esp32 = esp32
        self.script_fn = script_fn  # fn(board, color, esp32) -> (fr,fc,tr,tc)
        self.games_played = 0
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.total_moves = 0
        self.script_bytes = 0
    
    def choose_move(self, board, move_history):
        """Ask the script for a move. Enforces ESP32 constraints."""
        moves = get_all_moves(board, self.color)
        if not moves:
            return None  # checkmate or stalemate
        
        # Filter out moves that leave king in check
        legal = []
        for fr, fc, tr, tc in moves:
            nb = make_move(board, fr, fc, tr, tc)
            if not is_in_check(nb, self.color):
                legal.append((fr, fc, tr, tc))
        
        if not legal:
            return None  # checkmate
        
        # ESP32 constraint: if over token budget, pick random
        self.esp32.tokens_used = 0
        start = time.time()
        result = self.script_fn(board, legal, self.color, self.esp32, move_history)
        elapsed = time.time() - start
        
        if result and result in legal:
            self.total_moves += 1
            return result
        elif result:  # illegal move from script
            return random.choice(legal)
        else:
            return random.choice(legal)

# ═══════════════════════════════════════════════════════════
# SCRIPT STRATEGIES (must fit in ~4KB "flash")
# ═══════════════════════════════════════════════════════════

PIECE_VALUES = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 20000,
                'p': 100, 'n': 320, 'b': 330, 'r': 500, 'q': 900, 'k': 20000}

def script_random(board, legal, color, esp32, history):
    """Random mover — baseline"""
    esp32.spend(1)
    return random.choice(legal)

def script_material(board, legal, color, esp32, history):
    """Greedy: always capture the highest-value piece"""
    esp32.spend(5)
    captures = [(fr,fc,tr,tc) for fr,fc,tr,tc in legal if board[tr][tc] != EMPTY]
    if captures:
        captures.sort(key=lambda m: PIECE_VALUES.get(board[m[2]][m[3]], 0), reverse=True)
        return captures[0]
    return random.choice(legal)

def script_center(board, legal, color, esp32, history):
    """Control the center"""
    esp32.spend(8)
    center_bonus = {}
    for r in range(8):
        for c in range(8):
            center_bonus[(r,c)] = 4 - max(abs(r-3.5), abs(c-3.5))
    
    best = None
    best_score = -999
    for fr, fc, tr, tc in legal:
        score = center_bonus[(tr, tc)] * 10
        if board[tr][tc] != EMPTY:
            score += PIECE_VALUES.get(board[tr][tc], 0)
        esp32.spend(1)
        if score > best_score:
            best_score = score
            best = (fr, fc, tr, tc)
    return best

def script_minimax_1ply(board, legal, color, esp32, history):
    """1-ply minimax: consider opponent's best response"""
    esp32.spend(50)  # more expensive
    opp = 'b' if color == 'w' else 'w'
    
    best = None
    best_score = -999999
    
    for fr, fc, tr, tc in legal:
        nb = make_move(board, fr, fc, tr, tc)
        esp32.spend(1)
        
        # My capture value
        score = PIECE_VALUES.get(board[tr][tc], 0)
        
        # Check if opponent can recapture
        opp_moves = get_all_moves(nb, opp)
        for ofr, ofc, otr, otc in opp_moves:
            if (otr, otc) == (tr, tc):
                score -= PIECE_VALUES.get(board[tr][tc], 0) * 0.9  # lose piece
                esp32.spend(1)
                break
        
        # Center control
        score += (4 - max(abs(tr-3.5), abs(tc-3.5))) * 5
        
        if score > best_score:
            best_score = score
            best = (fr, fc, tr, tc)
    
    return best

def script_development(board, legal, color, esp32, history):
    """Opening focus: develop pieces, control center"""
    esp32.spend(15)
    
    # Piece-square tables (simplified for ESP32)
    KNIGHT_PREF = [(2,1),(2,6),(5,1),(5,6),(3,3),(3,4),(4,3),(4,4)]
    BISHOP_PREF = [(2,2),(2,5),(5,2),(5,5)]
    
    move_count = len(history)
    
    if move_count < 20:  # Opening
        best = None
        best_score = -999
        for fr, fc, tr, tc in legal:
            score = 0
            p = board[fr][fc]
            
            # Develop knights and bishops first
            if p.upper() == 'N' and (fr,fc) in [(0,1),(0,6),(7,1),(7,6)]:
                score += 30 if (tr,tc) in KNIGHT_PREF else -5
            if p.upper() == 'B' and (fr,fc) in [(0,2),(0,5),(7,2),(7,5)]:
                score += 30 if (tr,tc) in BISHOP_PREF else -5
            
            # Center control
            score += (4 - max(abs(tr-3.5), abs(tc-3.5))) * 8
            
            # Don't move queen early
            if p.upper() == 'Q' and move_count < 10:
                score -= 20
            
            # Captures
            if board[tr][tc] != EMPTY:
                score += PIECE_VALUES.get(board[tr][tc], 0) * 0.5
            
            # Penalize moving pawns (they can't move back)
            if p.upper() == 'P':
                score -= 3
            
            esp32.spend(1)
            if score > best_score:
                best_score = score
                best = (fr, fc, tr, tc)
        return best
    else:
        # Fall back to material + center
        return script_minimax_1ply(board, legal, color, esp32, history)

# ═══════════════════════════════════════════════════════════
# GAME ENGINE
# ═══════════════════════════════════════════════════════════

def evaluate(board):
    """Simple board evaluation (positive = white advantage)"""
    score = 0
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p == EMPTY: continue
            v = PIECE_VALUES.get(p, 0)
            score += v if p.isupper() else -v
            # Center bonus
            cb = (4 - max(abs(r-3.5), abs(c-3.5))) * 3
            score += cb if p.isupper() else -cb
    return score

class ChessGame:
    def __init__(self, white, black, max_moves=150, verbose=True):
        self.white = white
        self.black = black
        self.board = copy.deepcopy(INITIAL_BOARD)
        self.turn = 'w'
        self.history = []
        self.move_num = 0
        self.max_moves = max_moves
        self.verbose = verbose
        self.result = None
        self.move_log = []
    
    def play(self):
        if self.verbose:
            print(f"\n{'═'*50}")
            print(f"  {self.white.name} (white) vs {self.black.name} (black)")
            print(f"  {self.white.esp32.name} vs {self.black.esp32.name}")
            print(f"{'═'*50}\n")
            print(render(self.board))
            print()
        
        while self.move_num < self.max_moves:
            player = self.white if self.turn == 'w' else self.black
            
            # Get move from script
            move = player.choose_move(self.board, self.history)
            
            if move is None:
                # No legal moves — checkmate or stalemate
                if is_in_check(self.board, self.turn):
                    winner = 'b' if self.turn == 'w' else 'w'
                    self.result = f"{'White' if winner=='w' else 'Black'} wins by checkmate"
                else:
                    self.result = "Draw by stalemate"
                break
            
            fr, fc, tr, tc = move
            captured = self.board[tr][tc]
            self.board = make_move(self.board, fr, fc, tr, tc)
            self.history.append((fr, fc, tr, tc))
            self.move_num += 1
            
            # Log
            notation = f"{pos_to_str(fr,fc)}{pos_to_str(tr,tc)}"
            if captured != EMPTY:
                notation += f"x{PIECES.get(captured, 'x')}"
            
            self.move_log.append(f"{self.move_num}. {'W' if self.turn=='w' else 'B'}: {notation}")
            
            if self.verbose and (self.move_num <= 10 or self.move_num % 10 == 0):
                side = "White" if self.turn == 'w' else "Black"
                cap = f" captures {PIECES.get(captured, '')}" if captured != EMPTY else ""
                print(f"  {self.move_num:3d}. {side}: {pos_to_str(fr,fc)}→{pos_to_str(tr,tc)}{cap}")
            
            # Check for insufficient material (simplified)
            pieces = [p for r in self.board for p in r if p != EMPTY]
            if len(pieces) <= 2:
                self.result = "Draw — insufficient material"
                break
            
            self.turn = 'b' if self.turn == 'w' else 'w'
            
            # 50-move rule (simplified)
            if self.move_num >= self.max_moves:
                self.result = f"Draw — {self.max_moves} move limit"
                break
        
        if not self.result:
            ev = evaluate(self.board)
            if abs(ev) < 50:
                self.result = f"Draw — position evaluation {ev:+d}"
            else:
                self.result = f"{'White' if ev > 0 else 'Black'} wins by evaluation {ev:+d}"
        
        if self.verbose:
            print(f"\n  Result: {self.result}")
            print(f"  Moves: {self.move_num}")
            print(f"  Final position:")
            print(render(self.board))
        
        return self.result

# ═══════════════════════════════════════════════════════════
# TOURNAMENT RUNNER
# ═══════════════════════════════════════════════════════════

def run_tournament(players_config, games=10, verbose=False):
    """Round-robin tournament between scripted players"""
    print(f"\n{'█'*60}")
    print(f"  PLATO-OS CHESS DOJO — ESP32 CONSTRAINT TOURNAMENT")
    print(f"  {len(players_config)} players, {games} games each pairing")
    print(f"{'█'*60}\n")
    
    # Create players
    players = []
    for name, script_fn, esp32_cfg in players_config:
        esp = ESP32Constraint(**esp32_cfg)
        w = ScriptedPlayer(name, 'w', esp, script_fn)
        b = ScriptedPlayer(name, 'b', ESP32Constraint(**esp32_cfg), script_fn)
        players.append((name, script_fn, esp32_cfg, w, b))
    
    results = {}
    for n1, _, cfg1, w1, b1 in players:
        for n2, _, cfg2, w2, b2 in players:
            if n1 >= n2: continue
            key = f"{n1} vs {n2}"
            results[key] = {'w': 0, 'b': 0, 'd': 0, 'games': 0}
            
            for g in range(games):
                if g % 2 == 0:
                    white, black = w1, b2
                    wk, bk = n1, n2
                else:
                    white, black = w2, b1
                    wk, bk = n2, n1
                
                game = ChessGame(white, black, max_moves=60, verbose=verbose and g == 0)
                result = game.play()
                
                def parse_result(result):
                    try:
                        ev = int(result.split()[-1].strip('+'))
                        if ev > 50: return 'w'
                        elif ev < -50: return 'b'
                        else: return 'd'
                    except:
                        pass
                    if 'White wins' in result: return 'w'
                    if 'Black wins' in result: return 'b'
                    return 'd'

                outcome = parse_result(result)
                results[key][outcome] += 1
                if outcome == 'w':
                    (w1 if wk == n1 else w2).wins += 1
                    (b2 if wk == n1 else b1).losses += 1
                elif outcome == 'b':
                    (b2 if bk == n1 else b2).wins += 1
                    (w1 if bk == n1 else w2).losses += 1
                else:
                    w1.draws += 1; b1.draws += 1; w2.draws += 1; b2.draws += 1
                
                w1.games_played += 1; b1.games_played += 1
                w2.games_played += 1; b2.games_played += 1
                results[key]['games'] += 1
    
    # Print standings
    print(f"\n{'═'*60}")
    print(f"  TOURNAMENT RESULTS")
    print(f"{'═'*60}\n")
    
    for key, r in results.items():
        total = r['games']
        if total == 0: continue
        print(f"  {key:30s}  W:{r['w']:2d} B:{r['b']:2d} D:{r['d']:2d}  ({total} games)")
    
    print(f"\n{'─'*60}")
    print(f"  PLAYER STANDINGS")
    print(f"{'─'*60}\n")
    
    standings = []
    for n1, _, cfg1, w1, b1 in players:
        total = w1.wins + w1.losses + w1.draws
        wr = w1.wins / total * 100 if total > 0 else 0
        standings.append((n1, w1.wins + b1.wins, w1.losses + b1.losses, w1.draws + b1.draws, total, wr))
    
    standings.sort(key=lambda x: x[1], reverse=True)
    for i, (name, wins, losses, draws, total, wr) in enumerate(standings):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
        print(f"  {medal} {name:20s}  {wins:3d}W {losses:3d}L {draws:3d}D  {wr:5.1f}%  (ESP32: {cfg1['name']}, budget: {cfg1['budget_tokens']}t)")
    
    return standings

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("ct-chess v0.1 — Constraint Theory Chess Dojo\n")
        print("Usage: ct-chess <command>\n")
        print("Commands:")
        print("  demo              One game: development vs random (verbose)")
        print("  tournament [n]    Round-robin, n games per pairing (default 20)")
        print("  duel <s1> <s2>   Best of 10: two scripts head-to-head")
        print("  boards            Show final positions from last tournament")
        print("\nScripts:")
        print("  random            Pure random moves")
        print("  material          Greedy material capture")
        print("  center            Center control focus")
        print("  minimax           1-ply minimax with recapture check")
        print("  development       Opening development + center control")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    SCRIPTS = {
        'random': script_random,
        'material': script_material,
        'center': script_center,
        'minimax': script_minimax_1ply,
        'development': script_development,
    }
    
    ESP32_DEFAULT = {'name': 'ESP32-S3', 'flash_kb': 4096, 'sram_kb': 520, 'budget_tokens': 500}
    ESP32_LITE = {'name': 'ESP32-C3', 'flash_kb': 2048, 'sram_kb': 400, 'budget_tokens': 200}
    ESP32_ULTRA = {'name': 'ESP32-S3-OC', 'flash_kb': 8192, 'sram_kb': 1024, 'budget_tokens': 2000}
    
    if cmd == 'demo':
        esp = ESP32Constraint(**ESP32_DEFAULT)
        w = ScriptedPlayer("Development-Bot", 'w', esp, script_development)
        b = ScriptedPlayer("Random-Bot", 'b', ESP32Constraint(**ESP32_LITE), script_random)
        game = ChessGame(w, b, max_moves=80, verbose=True)
        game.play()
    
    elif cmd == 'tournament':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        configs = [
            ("Random", script_random, ESP32_LITE),
            ("Material", script_material, ESP32_LITE),
            ("Center", script_center, ESP32_DEFAULT),
            ("Minimax-1", script_minimax_1ply, ESP32_DEFAULT),
            ("Development", script_development, ESP32_ULTRA),
        ]
        run_tournament(configs, games=n, verbose=False)
    
    elif cmd == 'duel':
        s1 = sys.argv[2] if len(sys.argv) > 2 else 'development'
        s2 = sys.argv[3] if len(sys.argv) > 3 else 'random'
        fn1 = SCRIPTS.get(s1, script_random)
        fn2 = SCRIPTS.get(s2, script_random)
        esp1 = ESP32Constraint(**ESP32_DEFAULT)
        esp2 = ESP32Constraint(**ESP32_LITE)
        w = ScriptedPlayer(f"{s1.title()}-W", 'w', esp1, fn1)
        b = ScriptedPlayer(f"{s2.title()}-B", 'b', esp2, fn2)
        
        w_score = 0
        b_score = 0
        d_score = 0
        for i in range(10):
            if i % 2 == 0:
                game = ChessGame(w, b, max_moves=100, verbose=(i==0))
            else:
                game = ChessGame(
                    ScriptedPlayer(f"{s2.title()}", 'w', ESP32Constraint(**ESP32_LITE), fn2),
                    ScriptedPlayer(f"{s1.title()}", 'b', ESP32Constraint(**ESP32_DEFAULT), fn1),
                    max_moves=100, verbose=False
                )
            result = game.play()
            if 'White wins' in result or (result and int(result.split()[-1].strip('+')) if result and 'evaluation' in result and result.split()[-1].strip('+').lstrip('-').isdigit() else 0) > 0:
                w_score += 1
            elif 'Black wins' in result or (result and result.split()[-1].strip('+').lstrip('-').isdigit() and int(result.split()[-1].strip('+')) < 0):
                b_score += 1
            else:
                d_score += 1
        
        print(f"\n  {s1} vs {s2}: {w_score}W {b_score}L {d_score}D (10 games)")
