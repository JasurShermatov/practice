# P08 experiment summary (Observed)

```text
Date (UTC): 2026-11-21 07:50:46
Machine: Linux container, kernel 6.18.44-fc-v726, 2 vCPU (Intel(R) Xeon(R) Processor @ 2.10GHz), 8024 MiB RAM
Python 3.13.18; starlette 1.7.0, pydantic 2.13.5, uvicorn 0.54.0, SQLite 3.53.1
Redis server v=7.0.15 sha=00000000:0 malloc=jemalloc-5.3.0 bits=64 build=d064f9f48c901a92
App: python main.py (uvicorn, 1 process, access log on), database: SQLite file; measurement tool on the same machine (client and server share the CPUs)
```

Median (min-max) over the runs.

| Scenario | Cache | Runs | Database queries | Cache hits / misses | Average ms | p95 ms | p99 ms | Searches/s | App CPU s | Redis CPU s |
|---|---|---|---|---|---|---|---|---|---|---|
| course | off | 5 | 2000 | 0 / 0 | 0.92 (0.79-1.04) | 1.31 (1.25-1.39) | 1.47 (1.41-1.70) | 1080.82 (961.46-1261.07) | 0.76 (0.71-0.88) | 0.00 (0.00-0.00) |
| course | redis | 5 | 2 | 999 / 1 | 0.72 (0.66-0.76) | 1.13 (0.97-1.17) | 1.31 (1.14-1.35) | 1389.28 (1319.36-1509.26) | 0.60 (0.58-0.64) | 0.05 (0.04-0.05) |
| course | memory | 5 | 2 | 999 / 1 | 0.57 (0.51-0.65) | 0.89 (0.61-0.95) | 1.08 (0.70-1.10) | 1755.42 (1539.64-1959.67) | 0.51 (0.47-0.55) | 0.00 (0.00-0.00) |
| rooms40 | off | 3 | 40000 | 0 / 0 | 1.51 (1.41-1.53) | 1.86 (1.65-1.94) | 2.10 (2.04-2.41) | 661.47 (650.64-707.09) | 1.30 (1.20-1.33) | 0.01 (0.00-0.01) |
| rooms40 | redis | 3 | 40 | 999 / 1 | 0.89 (0.78-0.91) | 1.22 (1.13-1.25) | 1.44 (1.33-1.46) | 1122.03 (1101.95-1283.69) | 0.74 (0.66-0.74) | 0.05 (0.04-0.05) |
| clients8 | off | 3 | 2000 | 0 / 0 | 6.39 (5.99-6.95) | 10.04 (8.99-11.03) | 11.65 (11.17-13.18) | 1228.11 (1127.65-1320.13) | 0.87 (0.87-0.97) | 0.00 (0.00-0.01) |
| clients8 | redis | 3 | 16 | 992 / 8 | 4.83 (4.79-5.35) | 7.19 (6.99-8.05) | 9.99 (8.98-10.10) | 1647.29 (1480.97-1652.47) | 0.61 (0.61-0.68) | 0.02 (0.01-0.02) |
