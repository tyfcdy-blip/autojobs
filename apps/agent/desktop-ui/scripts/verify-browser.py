"""使用已安装的 Playwright 与 Edge 检查静态页面；只模拟 pywebview 边界。"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        """验证记录单独保存，不输出每条静态资源访问。"""


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    assets = root.parent / "src/autojobs_agent/desktop_assets"
    output = root / "verification"
    output.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(assets)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    run = {
        "run_id": "ui-test-001", "task_id": "测试：表格整理", "state": "running",
        "stop_requested": False, "enqueued_at": 1795064400, "deadline": 1795064700,
        "started_at": 1795064401, "finished_at": None, "pid": 100, "exit_code": None,
        "error_code": None, "message": "", "result": None,
    }
    empty = {
        "mode": "local_validation",
        "worker": {"online": True, "last_seen_at": 1795064400, "pid": 50},
        "active_run": None, "runs": [], "pending_event_count": 0,
    }
    reconciling = {**run, "state": "reconciling"}
    scenarios = [
        ("empty", 1120, 780, empty),
        ("running", 1120, 780, {**empty, "active_run": run, "runs": [run], "pending_event_count": 3}),
        ("reconciling", 720, 560, {**empty, "active_run": reconciling, "runs": [reconciling]}),
        ("narrow", 390, 844, empty),
    ]
    evidence = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for name, width, height, snapshot in scenarios:
                page = browser.new_page(viewport={"width": width, "height": height})
                problems = []
                requests = []
                page.on("pageerror", lambda error: problems.append(str(error)))
                page.on("console", lambda message: problems.append(message.text)
                        if message.type in ["error", "warning"] else None)
                page.on("request", lambda request: requests.append(request.url))
                page.add_init_script("window.pywebview={api:{get_status:async()=>("
                                     + json.dumps(snapshot, ensure_ascii=False) + ")}}")
                origin = f"http://127.0.0.1:{server.server_port}/"
                page.goto(origin + "index.html", wait_until="networkidle")
                page.get_by_role("heading", name="执行状态", exact=True).wait_for()
                page.screenshot(path=str(output / (name + ".png")), full_page=True)
                no_overflow = page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                external = [url for url in requests if not url.startswith(origin)]
                evidence.append({
                    "scenario": name, "viewport": [width, height], "console_problems": problems,
                    "horizontal_overflow": not no_overflow, "external_requests": external,
                    "screenshot": name + ".png",
                })
                page.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        (output / "browser-results.json").write_text(json.dumps({
            "scope": "静态前端浏览器验证；pywebview桥使用测试快照，不代表真实worker集成",
            "engine": "Microsoft Edge / Playwright", "results": evidence,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for result in evidence:
        if result["console_problems"] or result["horizontal_overflow"] or result["external_requests"]:
            raise AssertionError(result)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
