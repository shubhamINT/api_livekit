# Reference: Java / Kotlin — Spring Boot

Contract and rules: [`../SKILL.md`](../SKILL.md). This file is syntax only.

Concurrency: `CompletableFuture.supplyAsync` on a bounded pool (or virtual
threads on Java 21+). Timeout: `orTimeout` per probe, plus the HTTP client's own.

## Do not just use Actuator

Spring Boot ships `/actuator/health`, and it is a reasonable starting point —
but out of the box it **violates two rules of this contract**:

1. It returns **`503 SERVICE_UNAVAILABLE`** when any indicator is `DOWN`. That is
   exactly the cascade this skill exists to prevent.
2. Its default `HealthIndicator`s auto-register for every datasource on the
   classpath, including ones no request path uses.

Two ways forward. Pick one, do not half-do both:

- **Actuator, corrected** — keep the indicators, but map every status to 200 and
  expose it at `/health`:
  ```yaml
  management:
    endpoints.web:
      base-path: /
      exposure.include: health
    endpoint.health:
      show-details: always
      status.http-mapping:
        DOWN: 200
        OUT_OF_SERVICE: 200
        UNKNOWN: 200
  ```
  You still owe `version`, `uptime_s`, and per-check `latency_ms` — Actuator
  supplies none of them — via a custom `HealthIndicator` per dependency that puts
  them in `withDetail`. And you must audit which indicators auto-registered.
- **A plain `@RestController`** — the code below. Fewer moving parts, exactly the
  contract, no framework behaviour to fight. Prefer this unless the org already
  standardises on Actuator scraping.

## The controller — `api/HealthController.java`

```java
/**
 * GET /health — one deep probe of every dependency a request needs.
 *
 * <p>Always answers HTTP 200: a degraded dependency shows up in the body, never
 * as a 5xx, so a downstream blip can't cascade into this service being pulled
 * out of rotation. Read status/checks, not the status code.
 */
@RestController
public class HealthController {

  private static final Logger log = LoggerFactory.getLogger(HealthController.class);
  private final long started = System.nanoTime();

  private final DbPinger db;
  private final HttpClient http;
  private final AppConfig cfg;
  private final Executor pool;   // Executors.newVirtualThreadPerTaskExecutor() on 21+

  // ... constructor injection

  /** Runs a probe, reports ok/latency, turns any failure into `error` text. */
  private CompletableFuture<Map<String, Object>> timed(Runnable probe) {
    long t0 = System.nanoTime();
    return CompletableFuture.supplyAsync(() -> { probe.run(); return true; }, pool)
        .orTimeout(cfg.healthProbeTimeoutSeconds(), TimeUnit.SECONDS)
        .handle((ok, ex) -> {
          var out = new LinkedHashMap<String, Object>();
          out.put("ok", ex == null);
          out.put("latency_ms",
                  Math.round((System.nanoTime() - t0) / 1e5) / 10.0);
          if (ex != null) {
            Throwable c = ex instanceof CompletionException ? ex.getCause() : ex;
            out.put("error", c.getClass().getSimpleName() + ": " + c.getMessage());
          }
          return out;
        });
  }

  /**
   * Reachability check only. These are POST-only business endpoints with no
   * health route, so ANY HTTP status (404, 405, 401...) means a server answered
   * and counts as up. Only a transport failure — connect refused, DNS, TLS,
   * timeout — is a failure. Do not "fix" this into a status-code assertion.
   */
  private Runnable probe(String url) {
    return () -> {
      try {
        http.send(HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(cfg.healthProbeTimeoutSeconds()))
                .GET().build(),
            HttpResponse.BodyHandlers.discarding());
      } catch (IOException | InterruptedException e) {
        throw new CompletionException(e);
      }
    };
  }
}
```

## The endpoint

```java
  @GetMapping("/health")
  public Map<String, Object> health() {
    var probes = new LinkedHashMap<String, Runnable>();
    probes.put("postgres", db::ping);
    probes.put("orders_api", probe(cfg.ordersApiUrl()));
    // Optional feature — a blank URL means it is off, not broken.
    if (!cfg.analyticsUrl().isBlank()) {
      probes.put("analytics", probe(cfg.analyticsUrl()));
    }

    var futures = new LinkedHashMap<String, CompletableFuture<Map<String, Object>>>();
    probes.forEach((name, p) -> futures.put(name, timed(p)));
    CompletableFuture.allOf(futures.values().toArray(CompletableFuture[]::new)).join();

    var checks = new LinkedHashMap<String, Object>();
    futures.forEach((name, f) -> checks.put(name, f.join()));
    checks.putIfAbsent("analytics", Map.of("ok", true, "skipped", true));

    var failed = checks.entrySet().stream()
        .filter(e -> !(Boolean) ((Map<?, ?>) e.getValue()).get("ok"))
        .map(Map.Entry::getKey).toList();
    boolean healthy = failed.isEmpty();
    if (!healthy) log.warn("health degraded: {}", failed);
    String status = healthy ? "ok" : "degraded";

    // Always 200 — see SKILL.md. No ResponseEntity.status(503) here.
    return Map.of(
        "success", healthy,
        "message", status,
        "data", Map.of(
            "status", status,
            "version", cfg.appVersion(),
            "uptime_s", Math.round((System.nanoTime() - started) / 1e8) / 10.0,
            "checks", checks));
  }
```

## The ping helper — owned by the persistence layer

```java
@Component
public class DbPinger {
  private final JdbcTemplate jdbc;

  /** Round-trips the database. Throws if it does not answer. Used by /health. */
  public void ping() {
    jdbc.queryForObject("SELECT 1", Integer.class);
  }
}
```

## Wiring — keep it out of the security filter chain

```java
http.authorizeHttpRequests(a -> a
    .requestMatchers("/health").permitAll()
    .anyRequest().authenticated());
```

## Config and version

```yaml
# application.yml — deliberately far below the 30–60s call timeouts
health:
  probe-timeout-seconds: ${HEALTH_PROBE_TIMEOUT_S:3}
```

Version comes from the build, not a constant: enable
`spring-boot-maven-plugin`'s `build-info` goal and inject `BuildProperties`, or
read `Implementation-Version` from the manifest. One source.

## Tests — `HealthControllerTest.java`

`MockRestServiceServer` or WireMock for upstreams, `@MockBean DbPinger`.

```java
@Test
void a404FromDownstreamStillCountsAsReachable() throws Exception {
  wireMock.stubFor(get("/").willReturn(aResponse().withStatus(404)));
  mvc.perform(get("/health"))
     .andExpect(status().isOk())
     .andExpect(jsonPath("$.data.status").value("ok"));
}

@Test
void transportFailureDegradesButReturns200() throws Exception {
  doThrow(new DataAccessResourceFailureException("no connection"))
      .when(dbPinger).ping();
  mvc.perform(get("/health"))
     .andExpect(status().isOk())                       // never 503
     .andExpect(jsonPath("$.data.status").value("degraded"))
     .andExpect(jsonPath("$.data.checks.postgres.ok").value(false));
}
```

## Gotchas

- **Do not run probes on the common `ForkJoinPool`.** A blocking JDBC or HTTP call
  there starves every other parallel stream in the JVM. Use a dedicated executor
  or virtual threads.
- **`orTimeout` cancels the future, not the underlying blocking call.** Give the
  HTTP client and the JDBC statement their own timeouts too, or a hung socket
  keeps a thread forever while `/health` reports the timeout cheerfully.
- **Unwrap `CompletionException`** before formatting `error`, or every message
  reads `CompletionException: java.io.IOException: ...`.
- **`System.nanoTime()`, not `currentTimeMillis()`**, for uptime and latency.
- If the org scrapes `/actuator/health`, expose both: keep Actuator for the
  scraper and `/health` as the contract endpoint. Do not silently redefine what
  the scraper reads.
