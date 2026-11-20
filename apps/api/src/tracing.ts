/**
 * OpenTelemetry tracing for one analysis: API submit -> queue -> worker -> ML service -> provider.
 *
 * Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set; then spans go to that collector over OTLP/HTTP
 * (deploy/docker-compose.prod.yml runs Jaeger for this). Spans are manual and few, and carry
 * ids, timings, token counts and outcomes: never document text or exception messages.
 */
import { context, propagation, trace, SpanStatusCode, type Attributes, type Span } from "@opentelemetry/api";

let shutdown: (() => Promise<void>) | undefined;

export async function startTracing(serviceName: string) {
  if (shutdown || !process.env.OTEL_EXPORTER_OTLP_ENDPOINT?.trim()) return false;
  const [{ TracerProvider, BatchSpanProcessor }, { OTLPTraceExporter }, { resourceFromAttributes }, { W3CTraceContextPropagator }, { AsyncLocalStorageContextManager }] =
    await Promise.all([import("@opentelemetry/sdk-trace"), import("@opentelemetry/exporter-trace-otlp-http"),
      import("@opentelemetry/resources"), import("@opentelemetry/core"), import("@opentelemetry/context-async-hooks")]);
  const provider = new TracerProvider({
    resource: resourceFromAttributes({ "service.name": process.env.OTEL_SERVICE_NAME || serviceName }),
    spanProcessors: [new BatchSpanProcessor({ exporter: new OTLPTraceExporter() })], // the exporter reads the endpoint itself
  });
  context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable());
  propagation.setGlobalPropagator(new W3CTraceContextPropagator());
  trace.setGlobalTracerProvider(provider);
  shutdown = () => provider.shutdown();
  return true;
}

export async function stopTracing() {
  await shutdown?.().catch(() => undefined);
}

/** The current trace as W3C headers (traceparent, tracestate), or {} when tracing is off. */
export function traceHeaders(): Record<string, string> {
  const carrier: Record<string, string> = {};
  propagation.inject(context.active(), carrier);
  return carrier;
}

/** Only well-formed W3C headers are accepted from queue data. */
export function traceCarrier(value: unknown): Record<string, string> | undefined {
  if (!value || typeof value !== "object") return undefined;
  const { traceparent, tracestate } = value as Record<string, unknown>;
  if (typeof traceparent !== "string" || !/^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/.test(traceparent)) return undefined;
  return typeof tracestate === "string" && tracestate.length <= 512 ? { traceparent, tracestate } : { traceparent };
}

/** Run `fn` in a span (a child of `parent` headers when given). Errors are recorded by type only. */
export async function inSpan<T>(name: string, attributes: Attributes, fn: (span: Span) => Promise<T>,
  parent?: Record<string, string>): Promise<T> {
  const ctx = parent ? propagation.extract(context.active(), parent) : context.active();
  return trace.getTracer("hirelens").startActiveSpan(name, { attributes }, ctx, async span => {
    try {
      return await fn(span);
    } catch (error) {
      span.setStatus({ code: SpanStatusCode.ERROR, message: error instanceof Error ? error.constructor.name : "Error" });
      throw error;
    } finally {
      span.end();
    }
  });
}
