# Reference: Go — net/http, chi, Gin

Contract and rules: [`../SKILL.md`](../SKILL.md). This file is syntax only.

Concurrency: a `WaitGroup` over goroutines writing into a pre-sized map guarded
by a mutex. Timeout: `context.WithTimeout` per probe. No dependency needed —
`net/http` and `sync` cover it.

## The handler — `internal/api/health.go`

```go
// Package api serves GET /health: one deep probe of every dependency a request
// needs.
//
// Always answers HTTP 200: a degraded dependency shows up in the body, never as
// a 5xx, so a downstream blip can't cascade into this service being pulled out
// of rotation. Read status/checks, not the status code.
package api

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"sync"
	"time"
)

var started = time.Now()

type Check struct {
	OK        bool     `json:"ok"`
	LatencyMS *float64 `json:"latency_ms,omitempty"`
	Error     string   `json:"error,omitempty"`
	Skipped   bool     `json:"skipped,omitempty"`
}

type probeFunc func(context.Context) error

// timed runs a probe and converts any error into a Check. It never returns an
// error: one broken probe must not fail the endpoint that reports breakage.
func timed(ctx context.Context, p probeFunc) Check {
	t0 := time.Now()
	err := p(ctx)
	ms := float64(time.Since(t0).Microseconds()) / 1000
	ms = float64(int(ms*10)) / 10
	if err != nil {
		return Check{OK: false, LatencyMS: &ms, Error: err.Error()}
	}
	return Check{OK: true, LatencyMS: &ms}
}

// probeReachable is a reachability check only. These are POST-only business
// endpoints with no health route, so ANY HTTP status (404, 405, 401...) means a
// server answered and counts as up. Only a transport failure — connect refused,
// DNS, TLS, timeout — is a failure. Do not "fix" this into a status-code check.
func probeReachable(url string) probeFunc {
	return func(ctx context.Context) error {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return err
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			return err
		}
		return resp.Body.Close()
	}
}
```

## The route

```go
func (s *Server) Health(w http.ResponseWriter, r *http.Request) {
	probes := map[string]probeFunc{
		"postgres":   s.DB.Ping,
		"orders_api": probeReachable(s.Cfg.OrdersAPIURL),
	}
	// Optional feature — an empty URL means it is off, not broken.
	if s.Cfg.AnalyticsURL != "" {
		probes["analytics"] = probeReachable(s.Cfg.AnalyticsURL)
	}

	checks := make(map[string]Check, len(probes)+1)
	var mu sync.Mutex
	var wg sync.WaitGroup
	for name, p := range probes {
		wg.Add(1)
		go func(name string, p probeFunc) {
			defer wg.Done()
			// Per-probe timeout, not one budget shared across the batch.
			ctx, cancel := context.WithTimeout(r.Context(), s.Cfg.HealthProbeTimeout)
			defer cancel()
			c := timed(ctx, p)
			mu.Lock()
			checks[name] = c
			mu.Unlock()
		}(name, p)
	}
	wg.Wait()
	if _, ok := checks["analytics"]; !ok {
		checks["analytics"] = Check{OK: true, Skipped: true}
	}

	healthy := true
	var failed []string
	for name, c := range checks {
		if !c.OK {
			healthy = false
			failed = append(failed, name)
		}
	}
	if !healthy {
		slog.Warn("health degraded", "failed", failed)
	}
	status := "ok"
	if !healthy {
		status = "degraded"
	}

	// Always 200 — see SKILL.md. Do not WriteHeader(503) here.
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"success": healthy,
		"message": status,
		"data": map[string]any{
			"status":   status,
			"version":  Version,
			"uptime_s": float64(int(time.Since(started).Seconds()*10)) / 10,
			"checks":   checks,
		},
	})
}
```

## The ping helper — owned by the DB layer

`*sql.DB` already has the right method; wrap it only if you need a different
statement. The handler never touches the driver directly.

```go
// internal/db/db.go
func (d *DB) Ping(ctx context.Context) error {
	if d.pool == nil {
		return errors.New("database pool not initialised")
	}
	return d.pool.PingContext(ctx)
}
```

## Wiring

Registered outside the auth middleware group.

```go
r.Get("/health", srv.Health)                     // chi: no middleware
r.Route("/v1", func(r chi.Router) {
	r.Use(srv.RequireTenant)
	// ...
})
```

## Config and version

```go
// Version is set at build time; never a second hardcoded copy.
//   go build -ldflags "-X main.Version=$(git describe --tags)"
var Version = "dev"

// Deliberately far below the 30–60s call timeouts.
cfg.HealthProbeTimeout = envDuration("HEALTH_PROBE_TIMEOUT_S", 3*time.Second)
```

Go 1.24+ can read the VCS revision from `debug.ReadBuildInfo()` instead of an
ldflag — either is fine, one source is the rule.

## Tests — `internal/api/health_test.go`

`httptest.NewServer` for upstreams, an interface or func field for the DB ping.

```go
func TestA404FromDownstreamStillCountsAsReachable(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer up.Close()
	// ... build server with OrdersAPIURL: up.URL, DB ping returning nil
	rec := httptest.NewRecorder()
	srv.Health(rec, httptest.NewRequest(http.MethodGet, "/health", nil))

	require.Equal(t, http.StatusOK, rec.Code)
	require.Equal(t, "ok", body(rec)["data"].(map[string]any)["status"])
}

func TestTransportFailureDegradesButReturns200(t *testing.T) {
	// point OrdersAPIURL at a closed port
	rec := httptest.NewRecorder()
	srv.Health(rec, httptest.NewRequest(http.MethodGet, "/health", nil))

	require.Equal(t, http.StatusOK, rec.Code)   // never 503
	require.Equal(t, "degraded", status(rec))
}
```

## Gotchas

- **Close the response body**, even on a reachability probe. A leaked body leaks
  a connection, and `/health` is the most-polled route in the service.
- **Do not use `http.DefaultClient` unbounded** — the per-probe `context` supplies
  the timeout here. If you swap in a shared client, give it a `Timeout` too.
- **The map write needs the mutex.** Concurrent map writes are a runtime panic in
  Go, and this is the one route where a panic is unacceptable.
- **`time.Since(started)`, not wall-clock subtraction** — `time.Time` carries a
  monotonic reading, so a clock adjustment cannot produce a negative uptime.
- Skip `gopkg.in/healthz` and friends. This is one file.
