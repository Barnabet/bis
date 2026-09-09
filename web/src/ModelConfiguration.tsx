import { Info } from "lucide-react";
import type { ModelStatus } from "./types";
import { pretty } from "./ui";

export function ModelConfiguration({
  model,
}: {
  model: ModelStatus | undefined;
}) {
  return (
    <div className="model-configuration">
      {model?.configured ? (
        <p className="muted-small">
          {model.provider || "OpenAI"} · {model.model || "Configured model"}.
          Model calls use the local service configuration.
        </p>
      ) : (
        <div className="notice info">
          <Info size={17} />
          <div>
            <strong>AI is not configured for this workspace.</strong>
            <p>
              Set <code>OPENAI_API_KEY</code> and{" "}
              <code>FOUNDRY_OPENAI_MODEL</code> in the service environment,
              restart Report Foundry, then refresh this workspace. Deterministic
              learning and manual revisions remain available.
            </p>
          </div>
        </div>
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
