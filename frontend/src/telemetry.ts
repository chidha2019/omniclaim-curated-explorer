import { W3CTraceContextPropagator } from "@opentelemetry/core";
import {
  context,
  defaultTextMapSetter,
  SpanKind,
  SpanStatusCode,
  trace,
} from "@opentelemetry/api";
import {
  BatchSpanProcessor,
  TraceIdRatioBasedSampler,
  TracerProvider,
} from "@opentelemetry/sdk-trace";
import type { ReadableSpan, SpanExporter } from "@opentelemetry/sdk-trace";
import { token } from "./auth";

class SafeBrowserExporter implements SpanExporter {
  export(spans: ReadableSpan[], done: (r: { code: number }) => void) {
    void (async () => {
      const access = await token();
      if (!access) {
        done({ code: 1 });
        return;
      }
      const result = await fetch("/api/v1/telemetry/browser", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${access}`,
        },
        body: JSON.stringify({
          spans: spans.slice(0, 20).map((s) => ({
            name: s.name,
            trace_id: s.spanContext().traceId,
            span_id: s.spanContext().spanId,
            start_ns: Math.round(s.startTime[0] * 1e9 + s.startTime[1]),
            duration_ns: Math.round(s.duration[0] * 1e9 + s.duration[1]),
            error: s.status.code === SpanStatusCode.ERROR,
          })),
        }),
        signal: AbortSignal.timeout(5000),
      });
      done({ code: result.ok ? 0 : 1 });
    })().catch(() => done({ code: 1 }));
  }
  async shutdown() {}
}
let provider: TracerProvider | undefined;
export function initTelemetry(ratio: number) {
  provider = new TracerProvider({
    sampler: new TraceIdRatioBasedSampler(ratio),
    spanProcessors: [
      new BatchSpanProcessor({
        exporter: new SafeBrowserExporter(),
        maxQueueSize: 200,
        maxExportBatchSize: 20,
        scheduledDelayMillis: 3000,
        exportTimeoutMillis: 6000,
      }),
    ],
  });
}
export function requestSpan(path: string, headers: Record<string, string>) {
  const tracer = provider?.getTracer("omniclaim-browser");
  const span = tracer?.startSpan(`GET ${path}`, { kind: SpanKind.CLIENT });
  if (span)
    new W3CTraceContextPropagator().inject(
      trace.setSpan(context.active(), span),
      headers,
      defaultTextMapSetter,
    );
  return span;
}
