"""Minimal reusable client for the Stitch (Google) MCP endpoint.

Stitch speaks MCP JSON-RPC 2.0 over a single HTTPS POST endpoint. Responses may
come back as plain JSON or as SSE-framed ``data: {...}`` lines, so both are handled.

Usage::

    from stitch_client import Stitch
    s = Stitch()
    proj = s.create_project("Interview Portal — Direction A")
    ds = s.create_design_system(proj_id, "Kinetic Glass", theme)
    scr = s.generate_screen(proj_id, prompt, device_type="DESKTOP", design_system=ds_name)
    s.save_screen(scr, out_dir, "landing-a")
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import random
import re
import time
from typing import Any

import requests

ENDPOINT = "https://stitch.googleapis.com/mcp"
DEFAULT_TIMEOUT = 300


def load_api_key(env_path: str | os.PathLike[str] | None = None) -> str:
    """Read STITCH_API_KEY from the environment, falling back to a .env file."""
    key = os.environ.get("STITCH_API_KEY")
    if key:
        return key.strip()
    if env_path is None:
        env_path = pathlib.Path(__file__).resolve().parent.parent / ".env"
    for line in pathlib.Path(env_path).read_text().splitlines():
        line = line.strip()
        if line.startswith("STITCH_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("STITCH_API_KEY not found in environment or .env")


class StitchError(RuntimeError):
    pass


class Stitch:
    def __init__(self, api_key: str | None = None, timeout: int = DEFAULT_TIMEOUT):
        self.api_key = api_key or load_api_key()
        self.timeout = timeout
        self._id = 0
        self.session = requests.Session()

    # ---- transport ------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-Goog-Api-Key": self.api_key,
        }

    @staticmethod
    def _parse(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("{"):
            return json.loads(text)
        # SSE framing: keep the last data: payload that parses as JSON
        last: dict[str, Any] | None = None
        for line in text.splitlines():
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    last = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
        if last is None:
            raise StitchError(f"unparseable response: {text[:500]}")
        return last

    def rpc(self, method: str, params: dict[str, Any] | None = None,
            retries: int = 4) -> dict[str, Any]:
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method,
                "params": params or {}}
        delay = 5.0
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                r = self.session.post(ENDPOINT, headers=self._headers(),
                                      data=json.dumps(body), timeout=self.timeout)
                if r.status_code in (429, 500, 502, 503, 504):
                    last_err = StitchError(f"HTTP {r.status_code}: {r.text[:300]}")
                else:
                    payload = self._parse(r.text)
                    if "error" in payload:
                        msg = json.dumps(payload["error"])[:600]
                        if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                            last_err = StitchError(msg)
                        else:
                            raise StitchError(msg)
                    else:
                        return payload.get("result", payload)
            except requests.RequestException as exc:  # network/timeout
                last_err = exc
            if attempt < retries - 1:
                time.sleep(delay + random.uniform(0, 3))
                delay = min(delay * 2, 90)
        raise StitchError(f"rpc {method} failed after {retries} tries: {last_err}")

    def call(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call an MCP tool and return its structured result."""
        res = self.rpc("tools/call", {"name": tool, "arguments": args or {}})
        if res.get("isError"):
            raise StitchError(json.dumps(res)[:800])
        if "structuredContent" in res:
            return res["structuredContent"]
        for block in res.get("content", []):
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except json.JSONDecodeError:
                    return {"text": block["text"]}
        return res

    def list_tools(self) -> list[dict[str, Any]]:
        return self.rpc("tools/list")["tools"]

    # ---- convenience ----------------------------------------------------
    def create_project(self, title: str) -> dict[str, Any]:
        return self.call("create_project", {"title": title})

    def create_design_system(self, project_id: str, display_name: str,
                             theme: dict[str, Any]) -> dict[str, Any]:
        return self.call("create_design_system", {
            "projectId": project_id,
            "designSystem": {"displayName": display_name, "theme": theme},
        })

    def upload_design_md(self, project_id: str, markdown: str) -> dict[str, Any]:
        b64 = base64.b64encode(markdown.encode()).decode()
        return self.call("upload_design_md",
                         {"projectId": project_id, "designMdBase64": b64})

    def generate_screen(self, project_id: str, prompt: str,
                        device_type: str = "DESKTOP",
                        design_system: str | None = None,
                        model_id: str | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"projectId": project_id, "prompt": prompt,
                                "deviceType": device_type}
        if design_system:
            args["designSystem"] = design_system
        if model_id:
            args["modelId"] = model_id
        return self.call("generate_screen_from_text", args)

    def generate_variants(self, project_id: str, screen_ids: list[str], prompt: str,
                          variant_count: int = 3, creative_range: str = "EXPLORE",
                          aspects: list[str] | None = None,
                          device_type: str = "DESKTOP") -> dict[str, Any]:
        opts: dict[str, Any] = {"variantCount": variant_count,
                                "creativeRange": creative_range}
        if aspects:
            opts["aspects"] = aspects
        return self.call("generate_variants", {
            "projectId": project_id, "selectedScreenIds": screen_ids,
            "prompt": prompt, "variantOptions": opts, "deviceType": device_type,
        })

    def edit_screens(self, project_id: str, screen_ids: list[str], prompt: str,
                     device_type: str = "DESKTOP") -> dict[str, Any]:
        return self.call("edit_screens", {
            "projectId": project_id, "selectedScreenIds": screen_ids,
            "prompt": prompt, "deviceType": device_type})

    @staticmethod
    def extract_screens(result: Any) -> list[dict[str, Any]]:
        """Pull the Screen objects out of a generate/edit/variants result.

        The payload nests them as ``content[<i>].design.screens[]``; older shapes
        put ``design`` at the top level, so both are handled.
        """
        out: list[dict[str, Any]] = []
        stack = [result]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if isinstance(cur.get("screens"), list):
                    out.extend(s for s in cur["screens"] if isinstance(s, dict) and "id" in s)
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
        seen, uniq = set(), []
        for s in out:
            if s["id"] not in seen:
                seen.add(s["id"])
                uniq.append(s)
        return uniq

    def save_screen_files(self, screen: dict[str, Any],
                          out_dir: str | os.PathLike[str], slug: str) -> dict[str, str]:
        """Write a Screen's HTML and screenshot to <out_dir>/<slug>.{html,png}."""
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = {}
        url = (screen.get("htmlCode") or {}).get("downloadUrl")
        if url:
            (out / f"{slug}.html").write_text(self.session.get(url, timeout=180).text)
            paths["html"] = str(out / f"{slug}.html")
        url = (screen.get("screenshot") or {}).get("downloadUrl")
        if url:
            self.download(url, out / f"{slug}.png")
            paths["png"] = str(out / f"{slug}.png")
        return paths

    def list_screens(self, project_id: str) -> dict[str, Any]:
        return self.call("list_screens", {"projectId": project_id})

    def get_screen(self, project_id: str, screen_id: str) -> dict[str, Any]:
        return self.call("get_screen", {
            "name": f"projects/{project_id}/screens/{screen_id}",
            "projectId": project_id, "screenId": screen_id})

    def list_design_systems(self, project_id: str) -> dict[str, Any]:
        return self.call("list_design_systems", {"projectId": project_id})

    # ---- artefact saving -------------------------------------------------
    def download(self, url: str, dest: pathlib.Path) -> pathlib.Path:
        r = self.session.get(url, timeout=120)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest

    @staticmethod
    def _walk(obj: Any, pred) -> list[Any]:
        found = []
        stack = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                for k, v in cur.items():
                    if pred(k, v):
                        found.append(v)
                    stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)
        return found

    def save_screen(self, screen_result: Any, out_dir: str | os.PathLike[str],
                    slug: str) -> dict[str, Any]:
        """Persist the HTML and screenshot of a generate/edit result as <slug>.html/.png."""
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        saved: dict[str, Any] = {"slug": slug, "html": None, "png": None, "urls": []}

        htmls = self._walk(screen_result, lambda k, v: k in
                           ("html", "htmlContent", "code", "content")
                           and isinstance(v, str) and "<" in v)
        urls = self._walk(screen_result, lambda k, v: isinstance(v, str)
                          and v.startswith("http"))
        saved["urls"] = urls

        html = max(htmls, key=len) if htmls else None
        html_urls = [u for u in urls if re.search(r"\.html|html", u)]
        if not html and html_urls:
            try:
                html = self.session.get(html_urls[0], timeout=120).text
            except requests.RequestException:
                html = None
        if html:
            p = out / f"{slug}.html"
            p.write_text(html)
            saved["html"] = str(p)

        png_urls = [u for u in urls if re.search(r"\.png|image|screenshot", u, re.I)]
        for u in png_urls:
            try:
                p = self.download(u, out / f"{slug}.png")
                saved["png"] = str(p)
                break
            except requests.RequestException:
                continue
        return saved


if __name__ == "__main__":
    s = Stitch()
    for t in s.list_tools():
        print(t["name"])
