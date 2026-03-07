# Phase 6 — Dashboard UI

## Goal
React dashboard showing today's full game slate with player predictions, stat distribution
visualizations, O/U line comparisons, and fantasy value rankings. Auto-refreshes when injury
status changes.

## Depends On
Phase 4 + Phase 5 complete — all API endpoints working.

## Unlocks
Phase 7 (Automation) — dashboard is the consumer that validates the full pipeline end-to-end.

## Skill Files to Read First
- `.claude/skills/api-patterns/SKILL.md` — API response schemas (know what data is available)

---

## Tech Stack

- React 18 + TypeScript
- Recharts — for distribution charts
- TanStack Query (React Query) — API data fetching + caching + auto-refresh
- Tailwind CSS — styling
- Lucide React — icons

All in `dashboard/` directory at repo root.

---

## Design Direction

**Aesthetic:** Dark theme, data-dense, professional sports analytics feel.
Think: ESPN Analytics meets Bloomberg Terminal.
Colors: Dark navy background (#0F1624), orange accent (#E8531A for Chalk brand),
white text, green for value plays (#22C55E), red for fades (#EF4444).

**NOT:** Generic light-mode SaaS dashboard. This is a tool for serious users.

---

## App Structure

```
dashboard/
├── src/
│   ├── App.tsx
│   ├── api/
│   │   └── chalk.ts           ← typed API client wrapping fetch calls
│   ├── components/
│   │   ├── SlateView/          ← today's games list
│   │   ├── PlayerCard/         ← single player prediction card
│   │   ├── StatDistribution/   ← p10–p90 range bar chart
│   │   ├── PropsBoard/         ← O/U edge value board
│   │   ├── FantasyBoard/       ← DK/FD value rankings table
│   │   └── InjuryBadge/        ← injury status indicator
│   ├── hooks/
│   │   ├── useGameSlate.ts
│   │   ├── usePlayerPrediction.ts
│   │   └── useFantasyBoard.ts
│   └── types/
│       └── chalk.ts            ← TypeScript types matching API schemas
```

---

## Step 1 — TypeScript API Types

### `dashboard/src/types/chalk.ts`

Mirror the Pydantic schemas from Phase 4/5 exactly:

```typescript
interface StatPrediction {
  stat: string;
  p10: number;
  p25: number;
  p50: number;   // median / primary prediction
  p75: number;
  p90: number;
  confidence: "high" | "medium" | "low";
}

interface FantasyScores {
  draftkings: number;
  fanduel: number;
  yahoo: number;
}

interface InjuryContext {
  playerStatus: string;
  absentTeammates: string[];
  opportunityAdjustment: number;
}

interface PlayerPrediction {
  playerId: number;
  playerName: string;
  gameId: string;
  opponentTeam: string;
  asOfTs: string;
  modelVersion: string;
  predictions: StatPrediction[];
  fantasyScores: FantasyScores;
  injuryContext: InjuryContext;
}

interface OverUnderLine {
  playerId: number;
  playerName: string;
  stat: string;
  line: number;
  sportsbook: string;
  overProbability: number;
  underProbability: number;
  impliedOverProb: number;
  edge: number;
  confidence: "high" | "medium" | "low";
}
```

---

## Step 2 — API Client

### `dashboard/src/api/chalk.ts`

```typescript
const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const chalkApi = {
  async getPlayerPrediction(playerId: number, gameId: string): Promise<PlayerPrediction>,
  async getGamePredictions(gameId: string): Promise<PlayerPrediction[]>,
  async getGameProps(gameId: string): Promise<OverUnderLine[]>,
  async getFantasyBoard(gameId: string, platform: string): Promise<FantasyBoardEntry[]>,
  async getTodaysGames(): Promise<Game[]>,
  async getHealth(): Promise<HealthResponse>,
}
```

---

## Step 3 — Slate View (Main Page)

### `dashboard/src/components/SlateView/`

Top-level view. Shows today's games.

**Layout:**
- Header: "Chalk" logo, current date, last updated timestamp
- Grid of game cards — each showing home vs. away team, game time, key injury flags
- Clicking a game opens the GameDetailView

**Data:** Poll `/v1/games/today` every 5 minutes for lineup changes.

---

## Step 4 — Player Prediction Card

### `dashboard/src/components/PlayerCard/`

The core visualization unit.

**Shows:**
- Player name, team, position, opponent matchup
- Injury status badge (Active / Questionable / Out)
- For each key stat (pts, reb, ast, fg3m): StatDistribution component
- Fantasy scores (DK / FD / Yahoo) with color coding vs. salary value
- Confidence badge (HIGH / MED / LOW)

**Absent teammate callout:**
If `injuryContext.absentTeammates.length > 0`, show orange banner:
"Usage spike likely — [names] are out"

---

## Step 5 — Stat Distribution Chart

### `dashboard/src/components/StatDistribution/`

The most important visual component. Shows the prediction range for a stat.

**Design:** Horizontal range bar.
- Thin background bar: p10 → p90 (full range, gray)
- Thicker inner bar: p25 → p75 (IQR, brand color)
- Circle marker at p50 (median)
- If Vegas line available: vertical dashed line at the line value
- Line color: green if model edge > 0.04, red if edge < -0.04, gray otherwise

```
pts:  10 ──[══════●══════]── 45
                ↑          ↑
              p25         p75
                    ↑
                   p50
              |
           Vegas line (28.5)
```

**Labels:** Show p10, p50, p90 values. Show Vegas line if available.

**Implementation:** Use Recharts ComposedChart or build with pure CSS/SVG for precision.

---

## Step 6 — Props Board (Betting Value Board)

### `dashboard/src/components/PropsBoard/`

Table of all player props for the day's slate, sorted by |edge|.

**Columns:**
- Player, Stat, Vegas Line, Model Proj (p50), Edge, Over%, Confidence
- Color rows: green background if edge > 0.06, red if edge < -0.06
- Filter controls: by stat, by confidence tier, by team

**High-edge plays:** Flag rows with |edge| ≥ 0.08 with a ⭐ icon.

---

## Step 7 — Fantasy Value Board

### `dashboard/src/components/FantasyBoard/`

DFS lineup building helper.

**Columns:**
- Player, Position, Salary (DK), Projected DK Pts, Value (pts/$1k), Floor, Ceiling, Ownership%
- Sortable by any column
- Position filter (PG / SG / SF / PF / C / FLEX)
- Toggle: show all vs. value plays only (value > 5.0 pts/$1k)

**Value color coding:**
- Value ≥ 6.0: green (elite value)
- Value 4.5–6.0: yellow (solid)
- Value < 4.5: gray (avoid)

---

## Step 8 — Auto-Refresh on Injury Updates

Use React Query with the following refetch intervals:

```typescript
// Today's games — check for lineup changes
useQuery({ queryKey: ['games', 'today'], refetchInterval: 5 * 60 * 1000 })

// Player predictions — refetch if injury status changed
useQuery({
  queryKey: ['prediction', playerId, gameId],
  refetchInterval: 10 * 60 * 1000,  // 10 minutes
  staleTime: 5 * 60 * 1000,
})

// Props board — Vegas lines update frequently
useQuery({ queryKey: ['props', gameId], refetchInterval: 3 * 60 * 1000 })
```

Show a "Updated X minutes ago" timestamp on each section. Flash orange when data refreshes.

---

## Phase 6 Completion Checklist

- [ ] `npm run dev` — dashboard loads without errors
- [ ] Today's slate shows all games
- [ ] Player prediction cards load for any active player
- [ ] StatDistribution chart renders p10–p90 range correctly
- [ ] Vegas line shown on chart when available
- [ ] Props board sorts by edge correctly, green/red coloring applied
- [ ] Fantasy board value scores compute correctly vs. manual check
- [ ] Auto-refresh works — update timestamp advances every few minutes
- [ ] Injury badge shows correctly for Out/Questionable players
- [ ] `TODO.md` updated — all Phase 6 checkboxes marked done
