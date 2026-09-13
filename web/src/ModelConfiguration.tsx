import { Info } from "lucide-react";
import type { ModelStatus } from "./types";
import { pretty } from "./ui";

export const modelProviderLabel = (provider: string | undefined) =>
  provider === "cliproxyapi"
    ? "CLIProxyAPI"
    : provider === "openai"
      ? "OpenAI"
      : provider || "Configured provider";

export function ModelConfiguration({
  model,
}: {
  model: ModelStatus | undefined;
}) {
  return (
    <div className="model-configuration">
      {model?.configured ? (
        <p className="muted-small">
          {modelProviderLabel(model.provider)} ·{" "}
          {model.model || "Configured model"}. Selected evidence is sent to this
          provider when you request model assistance.
        </p>
      ) : (
        <div className="notice info">
          <Info size={17} />
          <div>
            <strong>AI is not configured for this workspace.</strong>
            <p>
              Configure a model provider in the service environment, restart
              Report Foundry, then refresh this workspace. Deterministic
              learning and manual revisions remain available.
            </p>
            <details className="technical-details">
              <summary>Provider setup</summary>
              <p>For the local CLIProxyAPI service:</p>
              <pre>
                {
                  "FOUNDRY_MODEL_PROVIDER=cliproxyapi\nFOUNDRY_MODEL_BASE_URL=http://127.0.0.1:8317/v1\nFOUNDRY_MODEL_NAME=claude-opus-5\nFOUNDRY_MODEL_API_KEY=<local client key>"
                }
              </pre>
              <p>
                For the default OpenAI provider, existing{" "}
                <code>OPENAI_API_KEY</code> and{" "}
                <code>FOUNDRY_OPENAI_MODEL</code> settings remain supported.
                Configure credentials in the service environment.
              </p>
            </details>
          </div>
        </div>
      )}
      {model?.base_url && (
        <details className="technical-details">
          <summary>Configured model connection</summary>
          <p>
            {modelProviderLabel(model.provider)} ·{" "}
            {model.model || "Model not selected"}
          </p>
          <p>
            <code>{model.base_url}</code> ·{" "}
            {model.protocol === "responses"
              ? "Responses API"
              : "Configured protocol"}
          </p>
        </details>
      )}
      {model?.limits && (
        <details className="technical-details">
          <summary>Model request limits</summary>
          <pre>{pretty(model.limits)}</pre>
        </details>
      )}
    </div>
  );
}
