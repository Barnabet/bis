"""Optional precision previews of already generated Office bytes.

The helper cannot compose prose or read source datasets. It copies the frozen
artifact into a fresh temporary directory, converts with a configured local
Office backend, verifies the result, and returns provenance for that preview.
Deployment still needs a process/container sandbox appropriate to its trust
boundary; this local subprocess helper is not an untrusted-document sandbox.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader

from . import ExportError

FILTERS = {".docx": "writer_pdf_Export", ".xlsx": "calc_pdf_Export", ".pptx": "impress_pdf_Export"}


def _check_generated_office(data: bytes):
    if len(data) > 64 * 1024 * 1024:
        raise ExportError("The preview input exceeds the local renderer size limit.", "preview_size_limit")
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 256 * 1024 * 1024:
                raise ExportError("The expanded Office artifact exceeds the preview size limit.", "preview_size_limit")
            for item in archive.infolist():
                name = item.filename
                if name.startswith("/") or ".." in Path(name).parts or item.flag_bits & 1:
                    raise ExportError("The preview artifact has an unsafe archive entry.", "preview_unsafe_artifact")
                if any(term in name.lower() for term in ["vbaproject", "externallink", "activex", "oleobject"]):
                    raise ExportError("This preview profile rejects active or externally linked Office content.", "preview_unsafe_artifact")
                if name.endswith(".rels"):
                    xml = archive.read(name)
                    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                        raise ExportError("The preview profile rejects XML entity declarations.", "preview_unsafe_artifact")
                    for relation in ET.fromstring(xml):
                        if relation.get("TargetMode", "").lower() == "external":
                            raise ExportError("The preview profile rejects external relationships.", "preview_external_relationship")
    except (BadZipFile, ET.ParseError) as error:
        raise ExportError("The Office artifact is not a valid generated archive.", "preview_invalid_artifact") from error


def render_office_preview(artifact_path: Path, output_dir: Path, *, timeout_seconds: float = 30) -> dict:
    """Return a PDF rendered from this exact DOCX, XLSX or PPTX artifact.

    Set FOUNDRY_SOFFICE to a controlled executable in production. A local PATH
    lookup is a convenience for developer installs. No shell is involved.
    The output explicitly certifies only this backend, never Microsoft Office.
    """
    artifact_path = Path(artifact_path)
    extension = artifact_path.suffix.lower()
    if extension not in FILTERS:
        raise ExportError("An Office precision preview requires DOCX, XLSX, or PPTX.", "preview_unsupported_format")
    if not 0 < timeout_seconds <= 120:
        raise ExportError("The preview timeout must be between zero and 120 seconds.", "preview_timeout_policy")
    executable = os.environ.get("FOUNDRY_SOFFICE") or shutil.which("soffice")
    if not executable or not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise ExportError("Office precision preview is unavailable. Configure FOUNDRY_SOFFICE with a supported local LibreOffice executable.", "preview_backend_unavailable", 503)
    data = artifact_path.read_bytes()
    _check_generated_office(data)
    source_digest = hashlib.sha256(data).hexdigest()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_-]", "-", artifact_path.stem)[:90]
    filename = f"{name}-preview.pdf"
    destination = output_dir / filename
    if destination.exists():
        raise ExportError("A precision preview already exists in this job directory.", "artifact_exists", 409)
    try:
        version_result = subprocess.run([str(executable), "--version"], capture_output=True, text=True,
                                        timeout=min(5, timeout_seconds), check=False)
        if version_result.returncode != 0 or not version_result.stdout.strip():
            raise ExportError("The configured preview backend did not identify its version.", "preview_backend_failed", 503)
        version = version_result.stdout.strip().splitlines()[0][:200]
        with tempfile.TemporaryDirectory(prefix="foundry-office-preview-") as temp:
            root = Path(temp)
            frozen = root / ("frozen" + extension)
            frozen.write_bytes(data)
            rendered = root / "rendered"
            rendered.mkdir()
            profile = (root / "profile").as_uri()
            command = [str(executable), f"-env:UserInstallation={profile}", "--headless", "--invisible",
                       "--norestore", "--nodefault", "--nolockcheck", "--convert-to", f"pdf:{FILTERS[extension]}",
                       "--outdir", str(rendered), str(frozen)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
            converted = rendered / "frozen.pdf"
            if result.returncode != 0 or not converted.is_file():
                raise ExportError("The Office backend could not produce the requested precision preview.", "preview_render_failed")
            pdf_data = converted.read_bytes()
            if not pdf_data.startswith(b"%PDF-"):
                raise ExportError("The Office backend did not return a PDF.", "preview_invalid_pdf")
            reader = PdfReader(BytesIO(pdf_data))
            if not reader.pages:
                raise ExportError("The rendered precision preview has no pages.", "preview_invalid_pdf")
            destination.write_bytes(pdf_data)
            return {
                "path": str(destination), "filename": filename, "media_type": "application/pdf",
                "sha256": hashlib.sha256(pdf_data).hexdigest(), "size_bytes": len(pdf_data),
                "source_sha256": source_digest, "source_format": extension[1:],
                "renderer": "LibreOffice", "renderer_version": version,
                "origin": "exact_office_artifact", "page_count": len(reader.pages),
                "microsoft_office_certification": "not_certified",
            }
    except subprocess.TimeoutExpired as error:
        raise ExportError("The Office precision preview exceeded its time limit.", "preview_timeout", 504) from error


__all__ = ["render_office_preview"]
