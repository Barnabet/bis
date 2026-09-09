import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { Spinner } from "./ui";

export function ImagePreview({
  src,
  alt,
  className = "",
  onInspect,
  inspectLabel,
}: {
  src: string;
  alt: string;
  className?: string;
  onInspect?: () => void;
  inspectLabel?: string;
}) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setLoaded(false);
    setFailed(false);
  }, [src]);
  const image = (
    <img
      src={src}
      alt={alt}
      onLoad={() => setLoaded(true)}
      onError={() => setFailed(true)}
    />
  );
  return (
    <div
      className={`image-preview ${className}${loaded ? " loaded" : ""}${failed ? " failed" : ""}`}
    >
      {failed ? (
        <div className="image-preview-error" role="status">
          <ImageOff size={23} />
          <p>This image preview could not be loaded.</p>
        </div>
      ) : (
        <>
          {!loaded && (
            <div className="image-preview-loading">
              <Spinner label="Loading image…" />
            </div>
          )}
          {onInspect ? (
            <button
              type="button"
              className="image-inspect-button"
              aria-label={inspectLabel ?? "Inspect image source"}
              onClick={onInspect}
            >
              {image}
            </button>
          ) : (
            image
          )}
        </>
      )}
    </div>
  );
}
