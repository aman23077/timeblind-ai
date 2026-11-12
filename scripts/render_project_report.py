"""Use the packaged DOCX rasterizer with a PDF exported by native Word."""
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runtime = Path("C:/Users/Aman/.cache/codex-runtimes/codex-primary-runtime/dependencies")
os.environ["PATH"] = str(runtime / "native/poppler/Library/bin") + os.pathsep + os.environ["PATH"]
skill = Path("C:/Users/Aman/.codex/plugins/cache/openai-primary-runtime/documents/26.1007.11041/skills/documents")
spec = importlib.util.spec_from_file_location("document_renderer", skill / "render_docx.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
pdf = ROOT / "docs/report_qa/reviewed.pdf"
assert pdf.exists()
renderer.convert_to_pdf = lambda *args, **kwargs: (str(pdf), "PDF exported by native Word")
pages = renderer.rasterize(str(ROOT / "docs/TimeBlindAI_Project_Explanation.docx"),
                           str(ROOT / "docs/report_qa/pages"), 120, False, False)
print(f"Rendered {len(pages)} document pages")
