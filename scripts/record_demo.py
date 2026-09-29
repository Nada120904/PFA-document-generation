"""Record a real browser walkthrough of the local PFA 2026 demo.

Start the demo API and Vite frontend first, then run::

    python scripts/record_demo.py --output demo_assets/pfa2026_grounded_demo.mp4

The video uses only a disposable demo account and four local sample documents.
No API keys or external credentials are read by this script.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import Page, sync_playwright
except ImportError as exc:
    raise SystemExit("Install Playwright first: python -m pip install playwright") from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "demo_assets" / "pfa2026_grounded_demo.mp4"
QUESTION = "According to the uploaded files, where is the pilot team based, who is the review owner, and what does ML help classify?"


def wait_for_url(url: str, label: str, timeout: int = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError(f"{label} did not become available at {url}")


def demo_identity() -> tuple[str, str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    email = f"pfa-demo-{stamp}-{uuid.uuid4().hex[:4]}@example.test"
    password = "LocalDemo2026!"
    return email, password


def create_unique_documents(directory: Path) -> list[Path]:
    run_id = uuid.uuid4().hex[:8]
    demo_python = ROOT / ".venv-demo" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not demo_python.is_file():
        raise RuntimeError("Start the local demo first so its Python dependencies are installed.")
    subprocess.run(
        [str(demo_python), str(ROOT / "scripts" / "build_demo_samples.py"),
         "--output-dir", str(directory), "--run-id", run_id],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return [directory / name for name in
            ("project_brief.txt", "review_guide.docx", "pilot_metrics.csv", "quality_criteria.pdf")]


def hold(page: Page, milliseconds: int = 1500) -> None:
    page.wait_for_timeout(milliseconds)


def chapter(page: Page, title: str, subtitle: str, milliseconds: int = 1900) -> None:
    """Brief on-screen caption that leaves the real app visible underneath."""
    page.evaluate(
        """({title, subtitle}) => {
          document.getElementById('demo-chapter-card')?.remove();
          const card = document.createElement('div');
          card.id = 'demo-chapter-card';
          card.style.cssText = `position:fixed;z-index:2147483647;left:28px;bottom:24px;
            max-width:620px;padding:18px 24px;border-radius:16px;color:#fff;
            background:linear-gradient(135deg,rgba(12,35,62,.97),rgba(33,75,113,.94));
            box-shadow:0 16px 40px rgba(0,0,0,.23);font:16px/1.45 Segoe UI,Arial,sans-serif;
            pointer-events:none`;
          const heading = document.createElement('div');
          heading.textContent = title;
          heading.style.cssText = 'font-size:24px;font-weight:700;margin-bottom:3px';
          const detail = document.createElement('div');
          detail.textContent = subtitle;
          detail.style.cssText = 'opacity:.9';
          card.append(heading, detail);
          document.body.append(card);
        }""",
        {"title": title, "subtitle": subtitle},
    )
    hold(page, milliseconds)
    page.evaluate("document.getElementById('demo-chapter-card')?.remove()")


def title_slide(page: Page) -> None:
    page.set_content(
        """<!doctype html><html><head><meta charset="utf-8"><style>
        *{box-sizing:border-box}body{margin:0;background:#07182b;color:white;
        font-family:'Segoe UI',Arial,sans-serif}main{height:100vh;padding:80px 100px;
        background:radial-gradient(circle at 80% 20%,#2a638a 0,transparent 35%),
        linear-gradient(135deg,#08182a,#123c5c);display:flex;flex-direction:column;
        justify-content:center}.eyebrow{letter-spacing:.2em;text-transform:uppercase;
        color:#86d8e7;font-size:18px;font-weight:700}h1{font-size:70px;line-height:1.05;
        max-width:1050px;margin:22px 0}p{font-size:27px;color:#d5e8f5;max-width:900px;
        line-height:1.45}.steps{display:flex;gap:14px;margin-top:48px}.steps span{padding:14px 20px;
        border-radius:999px;background:#ffffff1b;border:1px solid #ffffff40;font-size:20px}</style>
        </head><body><main><div class="eyebrow">PFA 2026 · Functional demo</div>
        <h1>Document Intelligence Workspace</h1>
        <p>Upload files. Ask questions. Open four structured, readable exports.</p>
        <div class="steps"><span>Upload</span><span>Ask</span><span>Preview</span><span>Open</span>
        <span>PDF</span><span>Word</span><span>CSV</span><span>TXT</span></div></main></body></html>"""
    )
    hold(page, 3300)


def architecture_slide(page: Page) -> None:
    page.set_content(
        """<!doctype html><html><head><meta charset="utf-8"><style>
        *{box-sizing:border-box}body{margin:0;background:#07182b;color:#fff;
        font-family:'Segoe UI',Arial,sans-serif}main{padding:74px 90px;height:100vh;
        background:linear-gradient(135deg,#091d31,#174565)}small{color:#87d8e8;
        text-transform:uppercase;letter-spacing:.18em;font-size:18px;font-weight:700}
        h1{font-size:52px;margin:14px 0 12px}p{font-size:23px;color:#d2e4f1;
        margin-bottom:42px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}
        .box{border:1px solid #b2d7e65c;background:#ffffff17;border-radius:18px;
        padding:24px;min-height:128px}.box strong{display:block;font-size:23px;margin-bottom:9px}
        .box span{color:#d2e4f1;font-size:17px}.note{margin-top:35px;color:#aee7ec;
        font-size:19px}</style></head><body><main><small>Production architecture</small>
        <h1>Services behind the workflow</h1><p>The local demo exercises the same user journey with a standalone API and local storage.</p>
        <div class="grid">
        <div class="box"><strong>React workspace</strong><span>Chat, document queue, library, settings</span></div>
        <div class="box"><strong>Chatbot API</strong><span>Authentication, sessions, grounded answers</span></div>
        <div class="box"><strong>Orchestration</strong><span>Pipeline decisions and service health</span></div>
        <div class="box"><strong>Upload + Storage</strong><span>File intake and provider routing</span></div>
        <div class="box"><strong>Docling OCR</strong><span>Text extraction and parsing</span></div>
        <div class="box"><strong>VLM fallback</strong><span>Vision help for difficult pages</span></div>
        <div class="box"><strong>LightRAG</strong><span>Indexing and retrieval</span></div>
        <div class="box"><strong>PostgreSQL</strong><span>Users, documents, processing records</span></div>
        </div><div class="note">Demo mode runs locally; external providers and models are represented by the production architecture.</div>
        </main></body></html>"""
    )
    hold(page, 5300)


def walkthrough(page: Page, frontend_url: str, email: str, password: str, documents: list[Path], work: Path, timings: dict[str, float]) -> None:
    started = time.monotonic()
    def mark(name: str) -> None:
        timings[name] = time.monotonic() - started

    mark("intro")
    title_slide(page)
    page.goto(frontend_url, wait_until="domcontentloaded", timeout=30000)
    page.get_by_role("heading", name="Configure your workspace").wait_for(timeout=30000)
    if page.get_by_role("button", name="Continue to local demo").count():
        page.get_by_role("button", name="Continue to local demo").click()
    else:
        page.get_by_label("Token counter model name").fill("gpt-4o-mini")
        hold(page, 800)
        page.get_by_role("button", name="Save and continue").click()

    page.get_by_role("heading", name="Sign in to the chatbot").wait_for(timeout=30000)
    page.get_by_role("button", name="New here? Create an account").click()
    page.get_by_role("heading", name="Create your account").wait_for(timeout=10000)
    page.get_by_label("Name").fill("PFA Demo")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Create account", exact=True).click()
    page.get_by_role("heading", name="Ask the assistant").wait_for(timeout=30000)

    mark("upload")
    chapter(page, "1 · Upload four file types", "PDF, Word, CSV, and TXT are processed and indexed together.", 1700)
    page.locator("#storage-provider").select_option("nextcloud")
    page.locator(".compact-picker input[type=file]").set_input_files([str(path) for path in documents])
    page.wait_for_function("() => document.querySelectorAll('.queue-row').length === 4", timeout=10000)
    page.locator(".queue-row").first.evaluate("element => element.scrollIntoView({block: 'center', behavior: 'instant'})")
    hold(page, 1100)
    page.locator(".queue-row").last.evaluate("element => element.scrollIntoView({block: 'center', behavior: 'instant'})")
    hold(page, 1100)
    page.locator(".queue-actions").get_by_role("button", name="Start").click()
    page.wait_for_function(
        "() => document.querySelectorAll('.queue-row.done, .queue-row.error').length === 4",
        timeout=120000,
    )
    if page.locator(".queue-row.error").count():
        raise RuntimeError("Document pipeline failed: " + page.locator(".queue-row.error").inner_text())
    page.locator(".queue-row").first.evaluate("element => element.scrollIntoView({block: 'center', behavior: 'instant'})")
    hold(page, 2200)

    mark("answer")
    chapter(page, "2 · Ask across the uploads", "Answers show source names and exact facts from the files.", 1300)
    page.get_by_placeholder("Ask about uploaded and indexed documents...").fill(QUESTION)
    page.get_by_role("button", name="Send", exact=True).click()
    page.wait_for_function(
        "() => [...document.querySelectorAll('.message.assistant')].some("
        "node => node.textContent?.toLowerCase().includes('casablanca'))",
        timeout=120000,
    )
    page.wait_for_function(
        "() => ![...document.querySelectorAll('.message.assistant')].some("
        "node => node.textContent?.includes('Thinking with the current knowledge base'))",
        timeout=20000,
    )
    answer = page.locator(".message.assistant").last.inner_text().lower()
    expected_facts = ("casablanca", "amal benali", "classify")
    missing_facts = [fact for fact in expected_facts if fact not in answer]
    if missing_facts:
        raise RuntimeError(
            f"Chat answer omitted {', '.join(missing_facts)} from the sample document: {answer[:500]}"
        )
    page.locator(".message.assistant").last.evaluate("element => element.scrollIntoView({block: 'center', behavior: 'instant'})")
    hold(page, 2800)

    mark("refusal")
    chapter(page, "3 · No outside facts", "An unrelated topic receives a clear refusal, not invented content.", 1200)
    page.get_by_placeholder("Ask about uploaded and indexed documents...").fill("Generate a PDF summary about lunar geology")
    page.get_by_role("button", name="Send", exact=True).click()
    page.wait_for_function("() => [...document.querySelectorAll('.message.assistant')].some(node => node.textContent?.includes('did not generate'))", timeout=30000)
    page.locator(".message.assistant").last.evaluate("element => element.scrollIntoView({block: 'center', behavior: 'instant'})")
    hold(page, 2800)

    for index, file_format in enumerate(("PDF", "DOCX", "TXT", "CSV"), start=1):
        mark(file_format.lower())
        if file_format == "PDF":
            chapter(page, "4 · PDF brief on ML", "Preview the evidence, then open the designed PDF.", 1100)
            prompt = "Generate a PDF summary on ML using only indexed documents"
        else:
            chapter(page, f"{index + 3} · {file_format} report", "Preview and open its structured sections.", 1100)
            prompt = f"Generate a {file_format} using only the uploaded files"
        page.get_by_placeholder("Ask about uploaded and indexed documents...").fill(
            prompt
        )
        page.get_by_role("button", name="Send", exact=True).click()
        card = page.locator(".generated-file-card").nth(index - 1)
        card.wait_for(timeout=30000)
        card.get_by_role("button", name="Preview").click()
        preview = page.locator(".generated-file-block").nth(index - 1).locator(".generated-file-preview")
        preview.wait_for(timeout=30000)
        preview.evaluate("element => element.scrollIntoView({block: 'center', behavior: 'instant'})")
        preview_text = preview.inner_text().lower()
        if file_format == "PDF":
            if "quality_criteria.pdf" not in preview_text or "machine learning" not in preview_text:
                raise RuntimeError(f"ML PDF preview was not grounded in the indexed PDF: {preview_text[:500]}")
            if any(name in preview_text for name in ("project_brief.txt", "review_guide.docx", "pilot_metrics.csv")):
                raise RuntimeError(f"ML PDF included an unrelated source: {preview_text[:500]}")
        else:
            expected_sources = ("project_brief.txt", "review_guide.docx", "pilot_metrics.csv", "quality_criteria.pdf")
            missing_sources = [name for name in expected_sources if name not in preview_text]
            if missing_sources:
                raise RuntimeError(f"{file_format} preview omitted {missing_sources}: {preview_text[:500]}")
        hold(page, 900)
        mark(f"{file_format.lower()}_open")
        card.get_by_role("button", name="Open file").click()
        viewer = page.get_by_role("dialog", name=f"Opened {file_format} file")
        viewer.wait_for(timeout=10000)
        viewer.locator("iframe").wait_for(timeout=10000)
        open_url = card.locator("a.generated-file-download").get_attribute("href").replace("/download/", "/open/")
        opened_response = page.request.get(frontend_url.rstrip("/") + open_url)
        if opened_response.status != 200:
            raise RuntimeError(f"Could not open {file_format} file: HTTP {opened_response.status}")
        if file_format == "PDF" and not opened_response.body().startswith(b"%PDF"):
            raise RuntimeError("Opened PDF did not contain PDF bytes")
        if file_format != "PDF":
            opened_body = page.frame_locator(".generated-viewer-dialog iframe").locator("body")
            opened_body.wait_for(timeout=10000)
            if "project_brief.txt" not in opened_body.inner_text().lower():
                raise RuntimeError(f"Opened {file_format} viewer did not show file content")
        hold(page, 1900)
        if file_format != "PDF":
            scroll_target = 900 if file_format == "CSV" else 500
            opened_body.evaluate(
                "(element, top) => element.ownerDocument.defaultView.scrollTo({top, behavior: 'smooth'})",
                scroll_target,
            )
            hold(page, 2400)
        else:
            hold(page, 1900)
        viewer.get_by_role("button", name="Close file viewer").click()
        with page.expect_download(timeout=30000) as download_event:
            card.get_by_role("link", name="Download").click()
        exported = work / f"grounded_export.{file_format.lower()}"
        download_event.value.save_as(str(exported))
        if exported.stat().st_size == 0:
            raise RuntimeError(f"Generated {file_format} was empty")
        hold(page, 700)

    mark("end")
    chapter(page, "Four redesigned files opened", "PDF · Word (.docx) · CSV · TXT — viewed and downloaded.", 3300)


def transcode(raw_video: Path, output: Path, ffmpeg: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_video),
        "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-movflags", "+faststart", str(output),
    ]
    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", default="http://127.0.0.1:5173")
    parser.add_argument("--api-url", default="http://127.0.0.1:8015")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--browser", choices=("chrome", "msedge", "chromium"), default="chrome")
    parser.add_argument("--show-browser", action="store_true", help="Show the browser during recording")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    wait_for_url(args.frontend_url, "Frontend")
    wait_for_url(f"{args.api_url.rstrip('/')}/health", "Demo API")
    email, password = demo_identity()

    with tempfile.TemporaryDirectory(prefix="pfa-demo-") as temporary:
        work = Path(temporary)
        documents = create_unique_documents(work)
        timings: dict[str, float] = {}
        video_directory = work / "video"
        video_directory.mkdir()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel=args.browser if args.browser != "chromium" else None,
                headless=not args.show_browser,
            )
            context = browser.new_context(
                viewport={"width": 1600, "height": 900},
                record_video_dir=str(video_directory),
                record_video_size={"width": 1600, "height": 900},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.set_default_timeout(20000)
            video = page.video
            raw_video = work / "walkthrough.webm"
            try:
                walkthrough(page, args.frontend_url, email, password, documents, work, timings)
            except Exception:
                screenshot = output.with_suffix(".failure.png")
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot), full_page=True)
                raise
            finally:
                context.close()
                if video is not None:
                    video.save_as(str(raw_video))
                browser.close()

            if video is None:
                raise RuntimeError("Playwright did not provide a recorded video")
            transcode(raw_video, output, args.ffmpeg)
            output.with_suffix(".timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")

    print(f"Demo video: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
