from __future__ import annotations


# ==============================================================================
# BƯỚC 1: CẤU HÌNH GOOGLE CHROME ĐỂ TỰ ĐỘNG DOWNLOAD FILE KHI CHẠY CODE JS
# ==============================================================================
import os
import sys

# Tự động cài đặt môi trường nếu chạy trực tiếp trên Colab hệ thống chưa có
if "google.colab" in sys.modules or os.path.exists("/content"):
    if not os.path.exists("/usr/bin/google-chrome-stable"):
        print("[*] Đang khởi động cấu hình môi trường tải file bằng ép mã Javascript chạy ngầm...")
        os.system("wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -")
        os.system('echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list')
        os.system("apt-get update -y && apt-get install -y google-chrome-stable > /dev/null")
        os.system("pip install selenium pypdf requests > /dev/null")


import argparse
import hashlib
import json
import logging
import re
import shutil
import tempfile
import threading
import time
import unicodedata
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from selenium import webdriver
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import json
from pathlib import Path
from config import CONFIG

# ------------------------------- Configuration --------------------------------
ROOT_DIR = Path(CONFIG["paths"]["root_dir"])
DRIVE_TARGET_DIR = Path(CONFIG["paths"]["drive_target_dir"])
CACHE_FILE = ROOT_DIR / "tasks.json"
LOG_FILE = ROOT_DIR / "cafef_downloader_v2.log"
SUCCESS_DOWNLOADS_LOG = ROOT_DIR / "successful_downloads.jsonl"
FAILED_COMPANIES_LOG = ROOT_DIR / "companies_failed.jsonl"

BANK_TICKERS = []

COLLECTOR_NAME = CONFIG["crawler_settings"]["collector_name"]
YEARS = tuple(CONFIG["crawler_settings"]["years"])
REQUEST_WORKERS = CONFIG["crawler_settings"]["request_workers"]
MAX_RETRY_ROUNDS = CONFIG["crawler_settings"]["max_retry_rounds"]
MIN_FILE_BYTES = 10 * 1024
REQUEST_WORKERS = 6
MAX_RETRY_ROUNDS = 3
PAGE_WAIT_SECONDS = 15
DOWNLOAD_WAIT_SECONDS = 20
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


@dataclass(frozen=True)
class ReportTask:
    ticker: str
    exchange: str
    year: str
    period: str
    title: str
    filename: str
    sub_path: str
    href: str = ""
    onclick: str = ""
    outer_html: str = ""
    row_text: str = ""
    source_url: str = ""
    link_index: int = 0
    task_id: str = ""
    company_name: str = ""
    @property
    def local_path(self) -> Path:
        return ROOT_DIR / self.sub_path / self.filename
    @property
    def drive_path(self) -> Path:
        return DRIVE_TARGET_DIR / self.sub_path / self.filename
    @staticmethod
    def from_dict(data: dict) -> "ReportTask":
        allowed = {k: v for k, v in data.items() if k in ReportTask.__dataclass_fields__}
        return ReportTask(**allowed)
@dataclass
class DownloadResult:
    task: ReportTask
    ok: bool
    strategy: str
    reason: str = ""
    elapsed: float = 0.0
    retry_round: int = 0
def configure_logger() -> logging.Logger:
    ROOT_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cafef")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger
LOG = logging.getLogger("cafef")
def task_key(ticker: str, year: str, period: str, filename: str, href: str, onclick: str) -> str:
    raw = "|".join((ticker, year, period, filename, href, onclick))
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:20]
def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
# ==================================================================
# HÀM MỚI ĐỂ CHUẨN HÓA TÊN THƯ MỤC ROOT TỪ TÊN CÔNG TY
# ==================================================================
PREFIX_MAPPING = {
    "tổng công ty": "TCT", "công ty": "CT", "ngân hàng": "NH", "thương mại": "TM",
    "cổ phần": "CP", "xuất nhập khẩu": "XNK", "đầu tư": "DT", "kinh doanh": "KD",
    "phát triển": "PT", "tập đoàn": "TD", "dịch vụ": "DV", "sản xuất": "SX",
    "xây dựng": "XD", "và": "", "tmcp": "TMCP", "ctcp": "CTCP", "tctcp": "TCTCP",
}
def standardize_company_name(full_name: str, fallback_ticker: str) -> str:
    if not full_name: return fallback_ticker
    name = re.sub(r"\s+", " ", full_name.strip())
    prefix, rest = "", name
    keys = sorted(PREFIX_MAPPING.keys(), key=len, reverse=True)
    while True:
        matched = False
        lower_rest = rest.lower()
        for k in keys:
            if lower_rest.startswith(k + " ") or lower_rest == k:
                prefix += PREFIX_MAPPING[k]
                rest = rest[len(k):].strip()
                matched = True
                break
        if not matched: break
    rest = re.sub(r'(?i)\bviệt nam\b', 'VN', rest)
    rest = re.sub(r'(?i)\bviet nam\b', 'VN', rest)
    rest_no_accents = unicodedata.normalize('NFKD', rest).encode('ASCII', 'ignore').decode('utf-8')
    words = rest_no_accents.split()
    capitalized_words = [w if w.isupper() or w == "VN" else w.capitalize() for w in words]
    suffix = "".join(capitalized_words)
    suffix = re.sub(r"[^a-zA-Z0-9]", "", suffix)
    if prefix and suffix: return f"{prefix}_{suffix}"
    elif prefix: return prefix
    elif suffix: return suffix
    else: return fallback_ticker
def company_name_from_cafef(driver: webdriver.Chrome, ticker: str, fallback: str) -> str:
    prefixes = ("công ty ", "tổng công ty ", "ctcp ", "tct ", "ngân hàng ")
    def clean(value: str) -> str:
        value = normalize_space(value)
        value = re.sub(rf"^{re.escape(ticker)}\s*:\s*", "", value, flags=re.I)
        value = re.sub(r"\s*\((?:HOSE|HNX|UPCOM|HASTC)\)\s*$", "", value, flags=re.I)
        return value
    for selector in ("h1", ".company-name", ".stock-name", "[class*='company-name']"):
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                candidate = clean(element.text)
                if candidate.casefold().startswith(prefixes):
                    return candidate
        except WebDriverException:
            pass
    for candidate in re.findall(r"(?:Công ty|Tổng công ty|Ngân hàng)\s+[^|–—]+", driver.title, flags=re.I):
        candidate = clean(candidate)
        if candidate.casefold().startswith(prefixes):
            return candidate
    LOG.warning("%s: cannot read company name from CafeF; use fallback '%s'", ticker, fallback)
    return fallback
def is_valid_document(path: Path) -> tuple[bool, str]:
    try:
        if not path.is_file() or path.stat().st_size < MIN_FILE_BYTES:
            return False, "smaller than 10 KB"
        head = path.read_bytes()[:2048].lstrip().lower()
        if head.startswith(b"%pdf-"):
            return True, "pdf"
        if (b"<html" in head or b"<!doctype html" in head or b"access denied" in head or
                b"403 forbidden" in head or b"404 not found" in head):
            return False, "HTML/error response"
        return True, "binary document"
    except OSError as exc:
        return False, str(exc)
def usable_existing_file(task: ReportTask) -> bool:
    for path in (task.local_path, task.drive_path):
        valid, _ = is_valid_document(path)
        if valid: return True
        if path.exists():
            try: path.unlink()
            except OSError: pass
    return False
def company_info_for(ticker: str, session: requests.Session) -> tuple[str, str]:
    try:
        response = session.get(f"https://api.vietstock.vn/ta/getticker?ticker={ticker.upper()}", timeout=12)
        payload = response.json()
        record = payload[0] if payload else {}
        raw_exchange = str(record.get("Exchange", "")).lower()
        exchange = "hose" if "hose" in raw_exchange else "hnx" if "hnx" in raw_exchange else "upcom" if "upcom" in raw_exchange else "hose"
        name = next((normalize_space(str(record.get(key, "")))
                     for key in ("CompanyName", "OrganName", "FullName", "Name")
                     if normalize_space(str(record.get(key, "")))), ticker.upper())
        return exchange, name
    except Exception as exc:
        LOG.warning("%s company lookup failed (%s); use ticker and hose", ticker, exc)
        return "hose", ticker.upper()
def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, connect=3, read=3, backoff_factor=0.7,
                  status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(("GET", "HEAD")))
    adapter = HTTPAdapter(max_retries=retry, pool_connections=REQUEST_WORKERS * 2, pool_maxsize=REQUEST_WORKERS * 2)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/pdf,application/octet-stream,*/*;q=0.8"})
    return session
_REQUEST_LOCAL = threading.local()
def worker_session() -> requests.Session:
    if not hasattr(_REQUEST_LOCAL, "session"):
        _REQUEST_LOCAL.session = build_session()
    return _REQUEST_LOCAL.session
def make_driver(download_dir: Path) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1200")
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_experimental_option("prefs", {
        "download.default_directory": str(download_dir.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "safebrowsing.enabled": True,
    })
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(download_dir.resolve())})
    driver.set_page_load_timeout(40)
    return driver
def classify_report(title: str, row_text: str) -> tuple[str, bool, str, str] | None:
    text = normalize_space(f"{title} {row_text}").lower()
    if not ("báo cáo" in text or "bao cao" in text or "bctc" in text): return None
    match = re.search(r"\b(2021|2022|2023|2024|2025)\b", text)
    if not match: return None
    year = match.group(1)
    period, quarterly = "CN", False
    if "kiểm toán" in text or "kiem toan" in text: period = "CN"
    elif re.search(r"quý\s*1|quy\s*1|\bq1\b", text): period, quarterly = "Q1", True
    elif re.search(r"quý\s*2|quy\s*2|\bq2\b|6\s*tháng|6\s*thang|bán niên|ban nien", text): period, quarterly = "Q2", True
    elif re.search(r"quý\s*3|quy\s*3|\bq3\b", text): period, quarterly = "Q3", True
    elif re.search(r"quý\s*4|quy\s*4|\bq4\b", text): period, quarterly = "Q4", True
    suffix_m = "_M" if any(x in text for x in ("mẹ", "me", "riêng", "rieng", "lẻ", "le")) else ""
    suffix_ss = "_SS" if (any(x in text for x in ("soát xét", "soat xet", "đã soát", "da soat")) or re.search(r"\bss\b", text)) else ""
    return year, quarterly, period, suffix_m + suffix_ss
def extract_tasks(driver: webdriver.Chrome, ticker: str, exchange: str, company_name: str) -> list[ReportTask]:
    url = f"https://cafef.vn/du-lieu/{exchange}/{ticker.lower()}-tai-lieu.chn"
    driver.get(url)
    WebDriverWait(driver, PAGE_WAIT_SECONDS).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr")))
    company_name = company_name_from_cafef(driver, ticker, company_name)
    tasks: list[ReportTask] = []
    seen: set[str] = set()
    for row in driver.find_elements(By.CSS_SELECTOR, "tr"):
        row_text = normalize_space(row.text)
        if not any(year in row_text for year in YEARS): continue
        cells = row.find_elements(By.CSS_SELECTOR, "td")
        title = normalize_space(cells[0].text if cells else row_text.split("\n")[0])
        parsed = classify_report(title, row_text)
        if not parsed: continue
        year, quarterly, period, suffix = parsed
        root_folder = standardize_company_name(company_name, ticker)
        sub_path = str(Path(root_folder) / year / period) if quarterly else str(Path(root_folder) / year)
        filename = f"{ticker}_{year}_{period}{suffix}.pdf"
        for index, anchor in enumerate(row.find_elements(By.TAG_NAME, "a")):
            href = anchor.get_attribute("href") or ""
            onclick = anchor.get_attribute("onclick") or ""
            outer = anchor.get_attribute("outerHTML") or ""
            if not (href or onclick or outer): continue
            ident = task_key(ticker, year, period, filename, href, onclick)
            if ident in seen: continue
            seen.add(ident)
            tasks.append(ReportTask(ticker, exchange, year, period, title, filename, sub_path,
                                    href, onclick, outer, row_text, url, index, ident, company_name))
    LOG.info("%s discovery: %d link tasks", ticker, len(tasks))
    return tasks
def save_cache(tasks: Iterable[ReportTask]) -> None:
    payload = {"version": 3, "saved_at": time.time(), "tasks": [asdict(t) for t in tasks]}
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CACHE_FILE)
def load_cache() -> list[ReportTask]:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if int(data.get("version", 0)) < 3: return []
        return [ReportTask.from_dict(item) for item in data.get("tasks", [])]
    except (OSError, ValueError, TypeError):
        return []
def candidate_urls(task: ReportTask) -> list[str]:
    text = " ".join((task.href, task.onclick, task.outer_html))
    urls: list[str] = []
    if task.href and not task.href.lower().startswith("javascript"):
        urls.append(urljoin(task.source_url, task.href))
    extracted_paths = re.findall(r"[\"']([^\"']+\.(?:pdf|docx?|xlsx?)[^\"']*)[\"']", text, re.I)
    for path in extracted_paths:
        path_clean = path.lstrip('/')
        if path_clean.startswith("http"):
            urls.append(path_clean)
        else:
            if "images/uploaded" in path_clean.lower():
                urls.append(f"https://cafefnew.mediacdn.vn/{path_clean}")
                urls.append(f"https://cafef1.mediacdn.vn/{path_clean}")
            else:
                urls.append(f"https://cafefnew.mediacdn.vn/Images/Uploaded/DuLieuDownload/{path_clean}")
                urls.append(f"https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/{path_clean}")
    raw_urls = re.findall(r"https?://[^\s'\"<>\\]+?\.(?:pdf|docx?|xlsx?)(?:\?[^\s'\"<>\\]*)?", text, re.I)
    raw_urls.extend(re.findall(r"https?://(?:cafef1|cafefnew)\.mediacdn\.vn/[^\s'\"<>\\]+", text, re.I))
    for r_url in raw_urls:
        urls.append(r_url)
        if "cafefnew.mediacdn.vn" in r_url:
            urls.append(r_url.replace("cafefnew.mediacdn.vn", "cafef1.mediacdn.vn"))
        elif "cafef1.mediacdn.vn" in r_url:
            urls.append(r_url.replace("cafef1.mediacdn.vn", "cafefnew.mediacdn.vn"))
    for ident in re.findall(r"(?<!\d)(\d{6,})(?!\d)", text):
        urls.append(f"https://cafef.vn/download/{ident}")
    clean_urls = []
    for u in urls:
        u_clean = u.strip().strip("'\"<>").rstrip('.,;)')
        if u_clean.startswith("http"):
            clean_urls.append(u_clean)
    return list(dict.fromkeys(clean_urls))
def write_response(task: ReportTask, response: requests.Response) -> tuple[bool, str]:
    content_type = response.headers.get("Content-Type", "").lower()
    if response.status_code != 200: return False, f"HTTP {response.status_code}"
    if len(response.content) < MIN_FILE_BYTES: return False, "response smaller than 10 KB"
    if "text/html" in content_type or response.content[:2048].lower().find(b"<html") >= 0: return False, "HTML response"
    task.local_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".part-", dir=str(task.local_path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(response.content)
        tmp = Path(tmp_name)
        valid, reason = is_valid_document(tmp)
        if not valid:
            tmp.unlink(missing_ok=True)
            return False, reason
        tmp.replace(task.local_path)
        return True, "saved"
    except Exception as exc:
        Path(tmp_name).unlink(missing_ok=True)
        return False, str(exc)
def request_download(task: ReportTask, cookies: list[dict]) -> DownloadResult:
    started = time.monotonic()
    session = worker_session()
    for cookie in cookies:
        try: session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"), path=cookie.get("path", "/"))
        except Exception: pass
    headers = {"Referer": task.source_url, "Accept": "application/pdf,application/octet-stream,*/*"}
    errors = []
    for url in candidate_urls(task):
        try:
            response = session.get(url, headers=headers, timeout=(12, 60), allow_redirects=True)
            ok, reason = write_response(task, response)
            if ok: return DownloadResult(task, True, "requests-session", f"{url}", time.monotonic() - started)
            errors.append(f"{url}: {reason}")
        except requests.RequestException as exc:
            errors.append(f"{url}: {type(exc).__name__}")
    return DownloadResult(task, False, "requests-session", "; ".join(errors[-3:]), time.monotonic() - started)
class SeleniumFallback:
    def __init__(self) -> None:
        self.download_dir = Path(tempfile.mkdtemp(prefix="cafef-chrome-"))
        self.driver: Optional[webdriver.Chrome] = None
    def start(self) -> None:
        if self.driver is None: self.driver = make_driver(self.download_dir)
    def restart(self) -> None:
        self.close_driver()
        self.start()
    def close_driver(self) -> None:
        if self.driver:
            try: self.driver.quit()
            except Exception: pass
            self.driver = None
    def close(self) -> None:
        self.close_driver()
        shutil.rmtree(self.download_dir, ignore_errors=True)
    def clear_downloads(self) -> None:
        for item in self.download_dir.iterdir():
            try: item.unlink()
            except OSError: pass
    def completed_download(self, before: set[Path]) -> Optional[Path]:
        deadline = time.monotonic() + DOWNLOAD_WAIT_SECONDS
        while time.monotonic() < deadline:
            files = [p for p in self.download_dir.iterdir() if p not in before and not p.name.endswith(".crdownload")]
            if files: return max(files, key=lambda p: p.stat().st_mtime)
            time.sleep(0.25)
        return None
    def find_anchor(self, task: ReportTask):
        assert self.driver
        self.driver.get(task.source_url)
        WebDriverWait(self.driver, PAGE_WAIT_SECONDS).until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
        for anchor in self.driver.find_elements(By.TAG_NAME, "a"):
            if ((anchor.get_attribute("href") or "") == task.href and
                    (anchor.get_attribute("onclick") or "") == task.onclick):
                return anchor
        anchors = self.driver.find_elements(By.TAG_NAME, "a")
        return anchors[task.link_index] if task.link_index < len(anchors) else None
    def accept_download(self, task: ReportTask, before: set[Path]) -> tuple[bool, str]:
        downloaded = self.completed_download(before)
        if not downloaded: return False, "no completed browser download"
        valid, reason = is_valid_document(downloaded)
        if not valid:
            downloaded.unlink(missing_ok=True)
            return False, reason
        task.local_path.parent.mkdir(parents=True, exist_ok=True)
        downloaded.replace(task.local_path)
        return True, "saved"
    def download(self, task: ReportTask, retry_round: int) -> DownloadResult:
        started = time.monotonic()
        errors = []
        try:
            self.start()
            assert self.driver
            anchor = self.find_anchor(task)
            if anchor is None: return DownloadResult(task, False, "selenium", "anchor not found", time.monotonic()-started, retry_round)
            strategies = [
                ("normal-click", lambda a: a.click()),
                ("javascript-click", lambda a: self.driver.execute_script("arguments[0].click()", a)),
                ("actionchains-click", lambda a: ActionChains(self.driver).move_to_element(a).click(a).perform()),
                ("enter", lambda a: a.send_keys(Keys.ENTER)),
                ("new-tab", lambda a: self.driver.execute_script("window.open(arguments[0].href || 'about:blank','_blank')", a)),
            ]
            for name, action in strategies:
                self.clear_downloads()
                before = set(self.download_dir.iterdir())
                try:
                    anchor = self.find_anchor(task)
                    if anchor is None: raise WebDriverException("anchor disappeared")
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'})", anchor)
                    action(anchor)
                    ok, reason = self.accept_download(task, before)
                    if ok: return DownloadResult(task, True, name, reason, time.monotonic()-started, retry_round)
                    errors.append(f"{name}: {reason}")
                except Exception as exc: errors.append(f"{name}: {type(exc).__name__}")
            retry = request_download(task, self.driver.get_cookies())
            retry.strategy = "requests-after-selenium-cookie"
            retry.retry_round = retry_round
            if retry.ok: return retry
            errors.append(retry.reason)
        except Exception as exc: errors.append(f"driver: {type(exc).__name__}: {exc}")
        return DownloadResult(task, False, "selenium-fallback", "; ".join(errors[-5:]), time.monotonic()-started, retry_round)
def report_excel_fields(task: ReportTask) -> tuple[str, str]:
    report_type = "BC Năm" if task.period == "CN" else f"BC {task.period}"
    text = normalize_space(f"{task.title} {task.row_text}").lower()
    is_parent = "_M" in Path(task.filename).stem
    is_reviewed = "_SS" in Path(task.filename).stem
    is_audited = "kiểm toán" in text or "kiem toan" in text
    if is_parent and is_audited: note = "công ty mẹ (đã kiểm toán)"
    elif is_parent and is_reviewed: note = "công ty mẹ (đã soát xét)"
    elif is_parent: note = "công ty mẹ"
    elif is_audited: note = "(đã kiểm toán)"
    elif is_reviewed: note = "(đã soát xét)"
    else: note = ""
    return report_type, note
def write_download_result_logs(
    tasks: Iterable[ReportTask],
    unresolved: Iterable[ReportTask],
    failure_reasons: dict[str, str],
) -> None:
    reports_by_company: dict[str, dict[str, ReportTask]] = defaultdict(dict)
    failed_by_company: dict[str, dict[str, ReportTask]] = defaultdict(dict)
    for task in tasks:
        reports_by_company[task.ticker][str(task.local_path)] = task
    for task in unresolved:
        failed_by_company[task.ticker][str(task.local_path)] = task
    success_rows, failed_rows = [], []
    for ticker, reports in reports_by_company.items():
        company_name = next((task.company_name for task in reports.values() if task.company_name), ticker)
        failed_reports = failed_by_company.get(ticker, {})
        for task in reports.values():
            if str(task.local_path) in failed_reports: continue
            report_type, note = report_excel_fields(task)
            success_rows.append({
                "Mã Chứng Khoán": task.ticker,
                "Tên Công ty": task.company_name or company_name,
                "Năm Báo Cáo": int(task.year),
                "Loại Báo Cáo": report_type,
                "Người Thu Thập": COLLECTOR_NAME,
                "Ghi Chú": note,
            })
        if failed_reports:
            failed_rows.append({
                "ticker": ticker,
                "company_name": company_name,
                "total_reports": len(reports),
                "downloaded_reports": len(reports) - len(failed_reports),
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "failed_reports": [
                    {"year": task.year, "period": task.period, "title": task.title, "filename": task.filename, "reason": failure_reasons.get(task.task_id, "missing or invalid output file")}
                    for task in failed_reports.values()
                ],
            })
    def write_rows(path: Path, rows: list[dict]) -> None:
        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        path.write_text(content, encoding="utf-8")
    write_rows(SUCCESS_DOWNLOADS_LOG, success_rows)
    write_rows(FAILED_COMPANIES_LOG, failed_rows)
    LOG.info("Download logs written: success files=%d (%s), failed companies=%d (%s)",
             len(success_rows), SUCCESS_DOWNLOADS_LOG, len(failed_rows), FAILED_COMPANIES_LOG)
def sync_to_drive() -> None:
    DRIVE_TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for source in ROOT_DIR.rglob("*"):
        if not source.is_file() or source == CACHE_FILE or source == LOG_FILE: continue
        relative = source.relative_to(ROOT_DIR)
        destination = DRIVE_TARGET_DIR / relative
        if is_valid_document(destination)[0]: continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
def discover_all(target_tickers: list[str]) -> tuple[list[ReportTask], dict[str, list[dict]]]:
    session = build_session()
    work = Path(tempfile.mkdtemp(prefix="cafef-discovery-"))
    driver = None
    try:
        driver = make_driver(work)
        all_tasks, cookies = [], {}
        for ticker in target_tickers:
            exchange, company_name = company_info_for(ticker, session)
            try:
                tasks = extract_tasks(driver, ticker, exchange, company_name)
                all_tasks.extend(tasks)
                cookies[ticker] = driver.get_cookies()
            except Exception as exc:
                LOG.exception("%s discovery failed: %s", ticker, exc)
                cookies[ticker] = []
        unique = list({task.task_id: task for task in all_tasks}.values())
        save_cache(unique)
        return unique, cookies
    finally:
        if driver:
            try: driver.quit()
            except Exception: pass
        shutil.rmtree(work, ignore_errors=True)
def run_pipeline(target_tickers: list[str]) -> None:
    ROOT_DIR.mkdir(parents=True, exist_ok=True)
    cached = load_cache() if CACHE_FILE.exists() else []
    if cached:
        tasks, discovery_cookies = cached, defaultdict(list)
        missing_tickers = {task.ticker for task in tasks if not task.company_name}
        if missing_tickers:
            session = build_session()
            info = {ticker: company_info_for(ticker, session) for ticker in missing_tickers}
            tasks = [replace(task, exchange=info[task.ticker][0], company_name=info[task.ticker][1])
                     if task.ticker in info else task for task in tasks]
            save_cache(tasks)
        LOG.info("Resume cache: %d report-link tasks", len(tasks))
    else:
        tasks, discovery_cookies = discover_all(target_tickers)
    pending = [task for task in tasks if not usable_existing_file(task)]
    LOG.info("Tasks=%d | already valid=%d | pending=%d", len(tasks), len(tasks)-len(pending), len(pending))
    stats = defaultdict(Counter)
    for task in tasks: stats[task.ticker]["found"] += 1
    retry_queue: deque[ReportTask] = deque()
    failure_reasons: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=REQUEST_WORKERS, thread_name_prefix="cafef-http") as pool:
        futures = {pool.submit(request_download, task, discovery_cookies.get(task.ticker, [])): task for task in pending}
        for future in as_completed(futures):
            result = future.result()
            if result.ok:
                stats[result.task.ticker]["downloaded"] += 1
                failure_reasons.pop(result.task.task_id, None)
                LOG.info("%s %s %s | %s | %.1fs", result.task.ticker, result.task.year, result.task.period, result.strategy, result.elapsed)
            else:
                retry_queue.append(result.task)
                failure_reasons[result.task.task_id] = result.reason
                LOG.warning("%s %s %s | queue retry | %s", result.task.ticker, result.task.year, result.task.period, result.reason)
    browser = SeleniumFallback()
    try:
        for retry_round in range(1, MAX_RETRY_ROUNDS + 1):
            if not retry_queue: break
            round_tasks, retry_queue = list(retry_queue), deque()
            LOG.info("Retry round %d: %d tasks", retry_round, len(round_tasks))
            if retry_round > 1: browser.restart()
            for task in round_tasks:
                if usable_existing_file(task):
                    stats[task.ticker]["downloaded"] += 1
                    failure_reasons.pop(task.task_id, None)
                    continue
                result = browser.download(task, retry_round)
                if result.ok:
                    stats[task.ticker]["downloaded"] += 1
                    stats[task.ticker]["retry_success"] += 1
                    failure_reasons.pop(task.task_id, None)
                    LOG.info("%s %s %s | %s retry=%d | %.1fs", task.ticker, task.year, task.period, result.strategy, retry_round, result.elapsed)
                else:
                    retry_queue.append(task)
                    failure_reasons[task.task_id] = result.reason
                    LOG.warning("%s %s %s | failed retry=%d | %s", task.ticker, task.year, task.period, retry_round, result.reason)
    finally:
        browser.close()
    unresolved = [task for task in tasks if not usable_existing_file(task)]
    for task in unresolved: stats[task.ticker]["failed"] += 1
    write_download_result_logs(tasks, unresolved, failure_reasons)
    sync_to_drive()
    LOG.info("==================== SUMMARY ====================")
    for ticker in target_tickers:
        s = stats[ticker]
        LOG.info("%s | Found: %d | Downloaded: %d | Retry Success: %d | Failed: %d",
                 ticker, s["found"], s["downloaded"], s["retry_success"], s["failed"])
    if unresolved:
        LOG.error("Unresolved tasks remain in %s for next resume: %d", CACHE_FILE, len(unresolved))


def main() -> None:
    parser = argparse.ArgumentParser(description="CafeF Financial Statement Downloader Dynamic Interface")
    
    # 1. LẤY ĐƯỜNG DẪN MẶC ĐỊNH TỪ CONFIG
    default_input_file = CONFIG.get("paths", {}).get("tickers_can_chay_txt", "./ma.txt")
    default_drive_dir = CONFIG.get("paths", {}).get("drive_target_dir", "")
    
    # 2. GÁN VÀO ARGPARSE
    parser.add_argument("--input_file", type=str, default=default_input_file, help="Đường dẫn file .txt")
    parser.add_argument("--drive_dir", type=str, default=default_drive_dir, help="Tùy chỉnh thư mục đồng bộ")
    parser.add_argument("--tickers", type=str, default="", help="Bơm trực tiếp chuỗi mã (ví dụ: VCB,ACB,BID)")
    
    args = parser.parse_args()
    configure_logger()
    
    global DRIVE_TARGET_DIR
    if args.drive_dir:
        DRIVE_TARGET_DIR = Path(args.drive_dir)
        LOG.info(f"Đã cập nhật thư mục đầu ra Drive: {DRIVE_TARGET_DIR}")

    final_tickers = []

    # Ưu tiên 1: Đọc từ tham số truyền trực tiếp chuỗi mã chứng khoán
    if args.tickers:
        final_tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        LOG.info(f"Nhận diện danh sách mã truyền trực tiếp: {final_tickers}")
        
    # Ưu tiên 2: Đọc từ file .txt (Đã lấy mặc định từ config)
    elif args.input_file:
        path_txt = Path(args.input_file)
        if path_txt.exists():
            content = path_txt.read_text(encoding="utf-8")
            # SỬA LỖI ĐỌC FILE DÍNH CHÙM (Hỗ trợ cả dấu phẩy và dấu xuống dòng)
            import re
            final_tickers = [t.upper() for t in re.split(r'[,\n\s]+', content) if t.strip()]
            LOG.info(f"Đọc thành công {len(final_tickers)} mã từ file {args.input_file}")
        else:
            LOG.error(f"File danh sách mã '{args.input_file}' không tồn tại!")

    # Ưu tiên 3: Dự phòng
    if not final_tickers:
        try:
            final_tickers = BANK_TICKERS
            LOG.info("Chuyển sang chế độ Auto-Pilot sử dụng BANK_TICKERS...")
        except NameError:
            pass

    if not final_tickers:
        LOG.error("Hủy tiến trình: Không tìm thấy bất kỳ mã chứng khoán nào để chạy!")
        return

    start = time.monotonic()
    run_pipeline(final_tickers)
    LOG.info("Completed in %.1f seconds", time.monotonic() - start)

if __name__ == "__main__":
    main()
