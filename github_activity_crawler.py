#!/usr/bin/env python3
"""
GitHub Daily Activity Crawler (Chỉ dùng GitHub REST Search API)
===============================================================
Công cụ thu thập dữ liệu công việc trong 1 ngày của GitHub User
chỉ sử dụng GitHub REST Search API (Search Issues, Pull Requests & Commits).

Tài liệu:
  - https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests
  - https://docs.github.com/en/rest/search/search#search-commits
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, date
from typing import Dict, List, Any, Optional

API_VERSION = "2022-11-28"  # Chuẩn GitHub REST API Version


class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHub-Daily-Search-Crawler",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        if params:
            encoded_params = urllib.parse.urlencode(params)
            url = f"{url}?{encoded_params}"

        req = urllib.request.Request(url, headers=self._get_headers())
        try:
            with urllib.request.urlopen(req) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            try:
                error_json = json.loads(error_body)
                msg = error_json.get("message", error_body)
            except Exception:
                msg = error_body
            if e.code == 403 and "rate limit" in msg.lower():
                print(f"[!] Rate Limit Search API: {msg}", file=sys.stderr)
                print("[!] Gợi ý: Truyền token (--token <TOKEN> hoặc đăng nhập OAuth) để có 30 requests/phút thay vì 10.", file=sys.stderr)
            elif e.code == 422:
                print(f"[!] Lỗi Validation Search Query: {msg}", file=sys.stderr)
            else:
                print(f"[!] HTTP Error {e.code}: {msg}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"[!] Lỗi kết nối đến GitHub: {e}", file=sys.stderr)
            raise


def parse_target_date(date_str: str) -> date:
    """Chuyển chuỗi YYYY-MM-DD thành date object."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Định dạng ngày không hợp lệ '{date_str}'. Vui lòng dùng định dạng YYYY-MM-DD (VD: 2026-10-06).")


# -------------------------------------------------------------
# THU THẬP DỮ LIỆU HOÀN TOÀN BẰNG GITHUB REST SEARCH API
# -------------------------------------------------------------
def crawl_user_activity_via_search(client: GitHubClient, username: str, target_date: date) -> Dict[str, Any]:
    """
    Thu thập toàn bộ hoạt động của user trong ngày target_date thông qua Search API:
      1. Pull Requests tạo mới: author:{user} type:pr created:YYYY-MM-DD
      2. Issues tạo mới:        author:{user} type:issue created:YYYY-MM-DD
      3. Pull Requests review:  reviewed-by:{user} type:pr updated:YYYY-MM-DD
      4. Thảo luận/Bình luận:   commenter:{user} updated:YYYY-MM-DD
      5. Commits đã tạo:        author:{user} author-date:YYYY-MM-DD qua /search/commits
    """
    date_str = target_date.isoformat()
    print(f"[*] [Search API] Đang tìm kiếm hoạt động của @{username} vào ngày {date_str}...")

    categorized = {
        "commits": [],
        "prs_created": [],
        "issues_created": [],
        "prs_reviewed": [],
        "items_commented": []
    }

    # 1. Tìm Commits được commit ngày hôm đó: /search/commits?q=author:USER author-date:YYYY-MM-DD
    try:
        print(f"  -> Đang tìm commits (author:{username} author-date:{date_str})...")
        q_commits = f"author:{username} author-date:{date_str}"
        res_commits = client.request("/search/commits", {"q": q_commits, "per_page": 100})
        for item in res_commits.get("items", []):
            commit_data = item.get("commit", {})
            repo_info = item.get("repository", {})
            repo_full_name = repo_info.get("full_name") or item.get("url", "").split("/commits/")[0].replace("https://api.github.com/repos/", "")
            categorized["commits"].append({
                "sha": item.get("sha", "")[:7],
                "message": commit_data.get("message", "").split("\n")[0],
                "repo": repo_full_name,
                "url": item.get("html_url"),
                "author_date": commit_data.get("author", {}).get("date")
            })
    except Exception as e:
        print(f"[-] Lỗi khi search Commits: {e}", file=sys.stderr)

    # 2. Tìm PRs được tạo ngày hôm đó: /search/issues?q=author:USER type:pr created:YYYY-MM-DD
    try:
        print(f"  -> Đang tìm Pull Requests tạo mới (author:{username} type:pr created:{date_str})...")
        q_prs = f"author:{username} type:pr created:{date_str}"
        res_prs = client.request("/search/issues", {"q": q_prs, "per_page": 100})
        for item in res_prs.get("items", []):
            categorized["prs_created"].append({
                "title": item.get("title"),
                "url": item.get("html_url"),
                "state": item.get("state"),
                "repo": item.get("repository_url", "").replace("https://api.github.com/repos/", ""),
                "created_at": item.get("created_at")
            })
    except Exception as e:
        print(f"[-] Lỗi khi search PRs: {e}", file=sys.stderr)

    # 3. Tìm Issues được tạo ngày hôm đó: /search/issues?q=author:USER type:issue created:YYYY-MM-DD
    try:
        print(f"  -> Đang tìm Issues tạo mới (author:{username} type:issue created:{date_str})...")
        q_issues = f"author:{username} type:issue created:{date_str}"
        res_issues = client.request("/search/issues", {"q": q_issues, "per_page": 100})
        for item in res_issues.get("items", []):
            categorized["issues_created"].append({
                "title": item.get("title"),
                "url": item.get("html_url"),
                "state": item.get("state"),
                "repo": item.get("repository_url", "").replace("https://api.github.com/repos/", ""),
                "created_at": item.get("created_at")
            })
    except Exception as e:
        print(f"[-] Lỗi khi search Issues: {e}", file=sys.stderr)

    # 4. Tìm PRs được review bởi user vào ngày đó: /search/issues?q=reviewed-by:USER type:pr updated:YYYY-MM-DD
    try:
        print(f"  -> Đang tìm PRs đã review (reviewed-by:{username} type:pr updated:{date_str})...")
        q_review = f"reviewed-by:{username} type:pr updated:{date_str}"
        res_reviews = client.request("/search/issues", {"q": q_review, "per_page": 50})
        for item in res_reviews.get("items", []):
            categorized["prs_reviewed"].append({
                "title": item.get("title"),
                "url": item.get("html_url"),
                "state": item.get("state"),
                "repo": item.get("repository_url", "").replace("https://api.github.com/repos/", ""),
                "updated_at": item.get("updated_at")
            })
    except Exception as e:
        print(f"[-] Lỗi khi search PRs reviewed: {e}", file=sys.stderr)

    # 5. Tìm các Issue/PR có user bình luận vào ngày đó: /search/issues?q=commenter:USER updated:YYYY-MM-DD
    try:
        print(f"  -> Đang tìm thảo luận/bình luận (commenter:{username} updated:{date_str})...")
        q_comment = f"commenter:{username} updated:{date_str}"
        res_comments = client.request("/search/issues", {"q": q_comment, "per_page": 50})
        for item in res_comments.get("items", []):
            is_pr = "pull_request" in item
            categorized["items_commented"].append({
                "type": "pull_request" if is_pr else "issue",
                "title": item.get("title"),
                "url": item.get("html_url"),
                "repo": item.get("repository_url", "").replace("https://api.github.com/repos/", ""),
                "updated_at": item.get("updated_at")
            })
    except Exception as e:
        print(f"[-] Lỗi khi search Comments: {e}", file=sys.stderr)

    total_items = (
        len(categorized["commits"]) +
        len(categorized["prs_created"]) +
        len(categorized["issues_created"]) +
        len(categorized["prs_reviewed"]) +
        len(categorized["items_commented"])
    )

    return {
        "method": "search_api",
        "username": username,
        "date": date_str,
        "total_results": total_items,
        "categorized": categorized
    }


# -------------------------------------------------------------
# XUẤT BÁO CÁO MARKDOWN
# -------------------------------------------------------------
def generate_markdown_report(data: Dict[str, Any]) -> str:
    """Tạo báo cáo tóm tắt Markdown đẹp mắt từ dữ liệu Search API."""
    username = data["username"]
    date_str = data["date"]
    cat = data.get("categorized", {})

    commits = cat.get("commits", [])
    prs_created = cat.get("prs_created", [])
    issues_created = cat.get("issues_created", [])
    prs_reviewed = cat.get("prs_reviewed", [])
    items_commented = cat.get("items_commented", [])

    lines = []
    lines.append(f"# 📊 Báo Cáo Hoạt Động GitHub: @{username}")
    lines.append(f"- **Ngày:** `{date_str}`")
    lines.append(f"- **Công cụ:** `GitHub REST Search API` (/search/issues & /search/commits)")
    lines.append(f"- **Thời gian tạo:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append("")
    lines.append("---")

    lines.append("## 📈 Thống Kê Tổng Quan")
    lines.append(f"| Hạng mục công việc | Số lượng |")
    lines.append(f"| :--- | :--- |")
    lines.append(f"| 🔨 Commits đã tạo | **{len(commits)}** |")
    lines.append(f"| 🔀 Pull Requests tạo mới | **{len(prs_created)}** |")
    lines.append(f"| 🐛 Issues tạo mới | **{len(issues_created)}** |")
    lines.append(f"| 👀 PRs đã Review | **{len(prs_reviewed)}** |")
    lines.append(f"| 💬 Issues/PRs có bình luận | **{len(items_commented)}** |")
    lines.append("")

    if commits:
        lines.append("## 🔨 Commits Đã Viết")
        for c in commits:
            lines.append(f"- [`{c['sha']}`]({c['url']}) trong **{c['repo']}**: {c['message']}")
        lines.append("")

    if prs_created:
        lines.append("## 🔀 Pull Requests Tạo Mới")
        for pr in prs_created:
            lines.append(f"- [{pr['title']}]({pr['url']}) (**{pr['repo']}**) - Trạng thái: `{pr['state']}`")
        lines.append("")

    if issues_created:
        lines.append("## 🐛 Issues Tạo Mới")
        for iss in issues_created:
            lines.append(f"- [{iss['title']}]({iss['url']}) (**{iss['repo']}**) - Trạng thái: `{iss['state']}`")
        lines.append("")

    if prs_reviewed:
        lines.append("## 👀 Pull Requests Đã Tham Gia Review")
        for pr in prs_reviewed:
            lines.append(f"- [{pr['title']}]({pr['url']}) (**{pr['repo']}**)")
        lines.append("")

    if items_commented:
        lines.append("## 💬 Issues/PRs Đã Tham Gia Thảo Luận")
        for it in items_commented:
            lines.append(f"- ({it['type']}) [{it['title']}]({it['url']}) (**{it['repo']}**)")
        lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------
# CLI ENTRY POINT
# -------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Thu thập hoạt động của 1 GitHub User trong 1 ngày định sẵn qua REST Search API."
    )
    parser.add_argument("username", help="GitHub username cần crawl (VD: torvalds, octocat)")
    parser.add_argument("date", help="Ngày cần crawl định dạng YYYY-MM-DD (VD: 2026-10-06)")
    parser.add_argument(
        "--token",
        default=None,
        help="GitHub Personal Access Token (khuyến nghị để tăng rate limit lên 30 req/phút)"
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Thư mục lưu kết quả JSON và Markdown (mặc định: thư mục hiện tại)"
    )

    args = parser.parse_args()

    try:
        target_date = parse_target_date(args.date)
    except ValueError as e:
        print(f"[!] {e}", file=sys.stderr)
        sys.exit(1)

    client = GitHubClient(token=args.token)

    result_data = crawl_user_activity_via_search(client, args.username, target_date)

    # Lưu kết quả
    os.makedirs(args.output_dir, exist_ok=True)
    json_path = os.path.join(args.output_dir, f"github_activity_{args.username}_{args.date}.json")
    md_path = os.path.join(args.output_dir, f"github_activity_{args.username}_{args.date}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    print(f"[✓] Đã xuất file JSON: {json_path}")

    md_content = generate_markdown_report(result_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[✓] Đã xuất file Markdown: {md_path}")

    print("\n" + "="*50)
    print(f"TỔNG KẾT (SEARCH API): @{args.username} ({args.date})")
    print("="*50)
    cat = result_data.get("categorized", {})
    print(f"• Commits:            {len(cat.get('commits', []))}")
    print(f"• PRs tạo mới:        {len(cat.get('prs_created', []))}")
    print(f"• Issues tạo mới:     {len(cat.get('issues_created', []))}")
    print(f"• PRs đã Review:      {len(cat.get('prs_reviewed', []))}")
    print(f"• Thảo luận/Comment:  {len(cat.get('items_commented', []))}")
    print(f"Xem chi tiết đầy đủ trong: {md_path}")


if __name__ == "__main__":
    main()
