"""Simple load test — measure p99 latency for player prediction endpoint."""
import asyncio
import statistics
import time

import httpx

URL = "http://127.0.0.1:8000/v1/players/1627741/predict"
PARAMS = {"game_id": "0022301192", "as_of": "2024-04-14T00:00:00"}
N_REQUESTS = 100
CONCURRENCY = 5


async def make_request(client: httpx.AsyncClient) -> float:
    start = time.perf_counter()
    resp = await client.get(URL, params=PARAMS)
    elapsed = time.perf_counter() - start
    resp.raise_for_status()
    return elapsed


async def main():
    # Warm up — first request (populates cache)
    async with httpx.AsyncClient(timeout=30.0) as client:
        warmup = await make_request(client)
        print(f"Warmup request: {warmup*1000:.0f}ms")

    # Run load test
    sem = asyncio.Semaphore(CONCURRENCY)
    latencies: list[float] = []

    async def bounded_request(client):
        async with sem:
            lat = await make_request(client)
            latencies.append(lat)

    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [bounded_request(client) for _ in range(N_REQUESTS)]
        await asyncio.gather(*tasks)

    # Compute stats
    latencies_ms = [l * 1000 for l in latencies]
    latencies_ms.sort()

    p50 = latencies_ms[len(latencies_ms) // 2]
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)]
    mean = statistics.mean(latencies_ms)
    minimum = min(latencies_ms)
    maximum = max(latencies_ms)

    print(f"\nLoad Test Results ({N_REQUESTS} requests, concurrency={CONCURRENCY})")
    print(f"{'='*50}")
    print(f"  Min:  {minimum:.0f}ms")
    print(f"  Mean: {mean:.0f}ms")
    print(f"  p50:  {p50:.0f}ms")
    print(f"  p95:  {p95:.0f}ms")
    print(f"  p99:  {p99:.0f}ms")
    print(f"  Max:  {maximum:.0f}ms")
    print(f"{'='*50}")

    if p99 < 500:
        print(f"PASS — p99 {p99:.0f}ms < 500ms target")
    else:
        print(f"FAIL — p99 {p99:.0f}ms >= 500ms target")


if __name__ == "__main__":
    asyncio.run(main())
