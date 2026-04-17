# PLATO Chess Dojo — Chess Optimization Room

Where chess evaluation heuristics are tested, optimized, and accumulated as tiles.

## Mission

Build a chess evaluation function that:
1. Passes all constraint gates (syntax, register pressure, occupancy, performance)
2. Uses < 32 registers (ESP32 S3 SRAM constraint)
3. Achieves > 25% occupancy on Jetson sm_87
4. Beats random play in 50+ validated games

## Bridge Pattern Stations

| Station | Role | Repo |
|---------|------|------|
| **Helmsman** | PTX kernel writer | ptx-world/ in zeroclaws |
| **Tactician** | Game player/validator | This room (chess-dojo) |
| **Lookout** | Synthesis/documentation | bridges/ in zeroclaws |

## Seed Tiles

### Material Evaluation
- **Q:** What's the simplest chess eval that beats random play?
  **A:** Pure material count. P=1, N=3, B=3, R=5, Q=9. Beats random 85%+ at depth 2.

- **Q:** How much does piece-square tables help over pure material?
  **A:** ~15% improvement. PSTs reward pieces for being on good squares (center for knights, 7th rank for rooks). Worth the lookup cost.

- **Q:** What's the king safety tile that matters most?
  **A:** Pawn shield. Count friendly pawns in front of king. Missing pawn = -30 centipawns per gap. Simple, effective, fits in 32 registers.

### ESP32 Constraints
- **Q:** What fits in 32 registers on ESP32 S3?
  **A:** Material eval (6 piece types × 2 sides = 12 registers) + piece-square table index (4) + accumulator (4) + loop counter (2) + temp (2) = ~24 registers. Room for 1-2 bonus terms.

- **Q:** Can we fit mobility evaluation?
  **A:** Barely. Pseudo-legal move generation needs ~8 extra registers. With material + PST already at 24, mobility pushes to 32. No room for error. Consider: skip mobility, add passed pawn bonus instead (cheaper).

- **Q:** What's the minimum useful eval at depth 2?
  **A:** Material + king safety. 18 registers. Leaves 14 for loop overhead and search. Proven to beat random 90%+.

### PTX Kernel Notes
- **Q:** How do I validate a PTX kernel on Jetson?
  **A:** `ptxas --gpu-name sm_87 kernel.ptx -o kernel.cubin`. Check register count in output. Then `cudaLaunchKernel` from a test harness.

- **Q:** What's the occupancy target?
  **A:** > 25% on sm_87. At 32 registers per thread, 128 max threads/SM, 128 CUDA cores → need 32+ active threads for good occupancy. 128/32 = 4 warps = 25%.

### Game Validation
- **Q:** How many games to validate an eval?
  **A:** 50 minimum for statistical significance. 100 preferred. Against random play, any eval should win 80%+. Against itself, look for 45-55% (balanced).

- **Q:** What depth should validation games run at?
  **A:** Depth 2 for ESP32 constraint testing (realistic for edge hardware). Depth 4-6 for quality evaluation (cloud GPU).

## Constraint Gates

Every evaluation kernel must pass:

1. **Syntax** — `ptxas` compiles without errors
2. **Register pressure** — < 32 registers (ESP32 S3 constraint)
3. **Occupancy** — > 25% on Jetson sm_87
4. **Performance** — > 80% win rate vs random at depth 2

## Tile → Kernel Pipeline

```
Tactician plays games → reports patterns → Lookout synthesizes
       ↓
Helmsman reads synthesis → writes PTX kernel → validates gates
       ↓
Tactician plays 50 games with kernel → reports win rate
       ↓
New tile: "kernel_v3.ptx: material+PST+king_safety, 31 regs, 87% win rate"
       ↓
Next kernel starts from accumulated tiles
```

## Cross-Pollination

- **zeroclaws** — Bridge Pattern stations, Helmsman/Lookout coordination
- **plato-forge** — GPU benchmark tiles for chess eval on Jetson
- **ct-lab** — Constraint validation methodology
- **plato-library** — Chess knowledge base entries
