# Dashboard screenshots

Demo-mode captures of the single-dashboard frontend (1920×1080), one per state:

| File | State |
|------|-------|
| `dashboard-morning.png`   | Morning mode (`?fixture=morning`) — Disruptions & Alerts in the left column, OVERALL RISK HIGH |
| `dashboard-afternoon.png` | Afternoon mode — PM Commute promoted in the left column |
| `dashboard-degraded.png`  | Degraded state — per-card banners, map staleness overlay, "Degraded" source list |

Note: the interactive map's **base and radar tiles are blank** in these captures
because the external CARTO/IEM tile services were unreachable in the capture
sandbox (TLS interception). The NWS alert polygons (served from the loopback
`/api/alerts.geojson`) do render. On the kiosk, with normal outbound network,
the dark base map and animated radar load as expected.
