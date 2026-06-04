"""Manual runner for the ESPN/Gemini injury agent."""

# BEFORE RUNNING: set GEMINI_API_KEY in your .env file
# Get a free key at: https://aistudio.google.com/app/apikey

import asyncio
from datetime import date

from sqlalchemy import select

from chalk.db.models import Injury, Player
from chalk.db.session import async_session_factory
from chalk.ingestion.injury_fetcher import fetch_and_store_injuries


async def main() -> None:
    async with async_session_factory() as session:
        summary = await fetch_and_store_injuries(session)
        print(f"\nSummary: {summary}\n")

        result = await session.execute(
            select(Player.name, Injury.status, Injury.injury_type, Injury.return_date, Injury.notes)
            .join(Injury, Injury.player_id == Player.player_id)
            .where(Injury.report_date == date.today())
            .order_by(Player.name)
        )
        rows = result.all()

    if not rows:
        print("No injury rows stored for today.")
        return

    headers = ("Player", "Status", "Injury", "Return", "Notes")
    widths = [24, 13, 18, 12, 48]
    print(" | ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("-+-".join("-" * w for w in widths))
    for name, status, injury_type, return_date, notes in rows:
        values = (
            name,
            status,
            injury_type or "",
            return_date.isoformat() if return_date else "",
            (notes or "")[:48],
        )
        print(" | ".join(v.ljust(w) for v, w in zip(values, widths)))


if __name__ == "__main__":
    asyncio.run(main())
