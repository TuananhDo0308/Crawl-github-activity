#!/usr/bin/env python3
"""
GitHub User Daily Activity Crawler
===================================
Công cụ crawl toàn bộ hoạt động của 1 GitHub User trong 1 ngày định sẵn.

Hỗ trợ 3 chế độ:
  1. 'events': Dùng Activity Events API (GET /users/{username}/events).
               Thích hợp nhất cho 30 ngày gần đây. Bắt trọn mọi hành động:
               Push commit, Comment, Review, Mở/Đóng Issue & PR, Tạo branch/tag, Star, Fork.
  2. 'search': Dùng GitHub Search API (GET /search/issues & GET /search/commits).
               Thích hợp cho ngày trong quá khứ xa (>30 ngày), tìm issues, PRs, comments, commits.
  3. 'auto':   Tự động phát hiện: nếu ngày trong vòng 30 ngày -> dùng Events API;
               nếu xa hơn -> dùng Search API.
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Any, Optional

API_VERSION = "2022-11-28"  # GitHub REST API Version chuẩn, hoặc 2026-03-10

class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHub-Daily-Activity-Crawler",
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
                print(f"[!] Lỗi Rate Limit từ GitHub API: {msg}", file=sys.stderr)
                print("[!] Gợi ý: Hãy truyền GitHub Token (--token <TOKEN> hoặc set biến môi trường GITHUB_TOKEN) để có hạn mức 5,000 req/giờ.", file=sys.stderr)
            elif e.code == 422:
                print(f"[!] Lỗi tham số truy vấn (Validation Failed): {msg}", file=sys.stderr)
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
        raise ValueError(f"Định dạng ngày không hợp lệ '{date_str}'. Vui lòng dùng định dạng YYYY-MM-DD (VD: 2026-10-05).")


def parse_iso_datetime(dt_str: str) -> datetime:
    """Parse chuỗi ISO 8601 sang datetime (hỗ trợ Z và timezone offset)."""
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)


# -------------------------------------------------------------
# Phương pháp 1: Activity Events API (GET /users/{username}/events)
# -------------------------------------------------------------
def crawl_user_events_by_date(client: GitHubClient, username: str, target_date: date, tz_offset_hours: int = 0) -> Dict[str, Any]:
    """
    Crawl timeline sự kiện của user thông qua Activity API.
    Lấy tối đa 300 sự kiện gần nhất (3 trang x 100).
    Lọc các sự kiện diễn ra đúng vào target_date (theo timezone quy định).
    """
    print(f"[*] [Events API] Đang lấy danh sách sự kiện gần nhất của user '{username}'...")
    all_events = []
    
    # GitHub Events API cho phép tối đa 300 events (3 trang x 100)
    for page in range(1, 4):
        try:
            events = client.request(f"/users/{username}/events", {"per_page": 100, "page": page})
            if not events or not isinstance(events, list):
                break
            all_events.extend(events)
            
            # Kiểm tra ngày của sự kiện cuối cùng trên trang này
            last_event_time = parse_iso_datetime(events[-1]["created_at"])
            # Chuyển về timezone mong muốn
            target_tz = timezone(timedelta(hours=tz_offset_hours))
            last_event_local_date = last_event_time.astimezone(target_tz).date()
            
            # Nếu sự kiện cuối cùng đã cũ hơn target_date, ta có thể dừng phân trang
            if last_event_local_date < target_date:
                break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ValueError(f"Không tìm thấy GitHub user '{username}'.")
            break

    target_tz = timezone(timedelta(hours=tz_offset_hours))
    filtered_events = []
    
    for ev in all_events:
        created_at_dt = parse_iso_datetime(ev["created_at"])
        local_date = created_at_dt.astimezone(target_tz).date()
        if local_date == target_date:
            filtered_events.append(ev)

    # Phân loại hoạt động
    categorized = {
        "commits": [],
        "pull_requests": [],
        "issues": [],
        "issue_comments": [],
        "pr_reviews": [],
        "pr_review_comments": [],
        "branch_and_tag_creations": [],
        "forks": [],
        "stars": [],
        "other": []
    }

    for ev in filtered_events:
        ev_type = ev.get("type")
        repo_name = ev.get("repo", {}).get("name", "unknown")
        created_at = ev.get("created_at")
        payload = ev.get("payload", {})

        if ev_type == "PushEvent":
            commits = payload.get("commits") or []
            branch = payload.get("ref", "").replace("refs/heads/", "")
            head_sha = payload.get("head", "")

            if commits:
                for c in commits:
                    categorized["commits"].append({
                        "repo": repo_name,
                        "branch": branch,
                        "sha": c.get("sha", "")[:7],
                        "message": c.get("message", "").strip(),
                        "url": f"https://github.com/{repo_name}/commit/{c.get('sha')}",
                        "created_at": created_at
                    })
            elif head_sha:
                # Nếu API không trả về mảng commits (để tiết kiệm băng thông), thử lấy thông điệp qua SHA
                commit_msg = ""
                try:
                    commit_detail = client.request(f"/repos/{repo_name}/commits/{head_sha}")
                    commit_msg = commit_detail.get("commit", {}).get("message", "").split("\n")[0]
                except Exception:
                    pass

                categorized["commits"].append({
                    "repo": repo_name,
                    "branch": branch,
                    "sha": head_sha[:7],
                    "message": commit_msg or f"Push to branch {branch}",
                    "url": f"https://github.com/{repo_name}/commit/{head_sha}",
                    "created_at": created_at
                })

        elif ev_type == "PullRequestEvent":
            pr = payload.get("pull_request", {})
            action = payload.get("action", "")
            categorized["pull_requests"].append({
                "action": action,
                "repo": repo_name,
                "number": pr.get("number"),
                "title": pr.get("title"),
                "url": pr.get("html_url"),
                "merged": pr.get("merged", False),
                "created_at": created_at
            })

        elif ev_type == "IssuesEvent":
            issue = payload.get("issue", {})
            action = payload.get("action", "")
            categorized["issues"].append({
                "action": action,
                "repo": repo_name,
                "number": issue.get("number"),
                "title": issue.get("title"),
                "url": issue.get("html_url"),
                "created_at": created_at
            })

        elif ev_type == "IssueCommentEvent":
            issue = payload.get("issue", {})
            comment = payload.get("comment", {})
            is_pr = "pull_request" in issue
            categorized["issue_comments"].append({
                "type": "pull_request" if is_pr else "issue",
                "repo": repo_name,
                "number": issue.get("number"),
                "title": issue.get("title"),
                "comment_body": comment.get("body", "")[:200],
                "url": comment.get("html_url"),
                "created_at": created_at
            })

        elif ev_type == "PullRequestReviewEvent":
            review = payload.get("review", {})
            pr = payload.get("pull_request", {})
            categorized["pr_reviews"].append({
                "repo": repo_name,
                "pr_number": pr.get("number"),
                "pr_title": pr.get("title"),
                "state": review.get("state"),
                "url": review.get("html_url"),
                "created_at": created_at
            })

        elif ev_type == "PullRequestReviewCommentEvent":
            comment = payload.get("comment", {})
            pr = payload.get("pull_request", {})
            categorized["pr_review_comments"].append({
                "repo": repo_name,
                "pr_number": pr.get("number"),
                "pr_title": pr.get("title"),
                "comment_body": comment.get("body", "")[:200],
                "url": comment.get("html_url"),
                "created_at": created_at
            })

        elif ev_type == "CreateEvent":
            ref_type = payload.get("ref_type")  # repository, branch, tag
            ref = payload.get("ref")
            categorized["branch_and_tag_creations"].append({
                "repo": repo_name,
                "type": ref_type,
                "ref": ref,
                "created_at": created_at
            })

        elif ev_type == "ForkEvent":
            forkee = payload.get("forkee", {})
            categorized["forks"].append({
                "from_repo": repo_name,
                "fork_url": forkee.get("html_url"),
                "created_at": created_at
            })

        elif ev_type == "WatchEvent":
            categorized["stars"].append({
                "repo": repo_name,
                "created_at": created_at
            })

        else:
            categorized["other"].append({
                "type": ev_type,
                "repo": repo_name,
                "created_at": created_at
            })

    return {
        "method": "events_api",
        "username": username,
        "date": target_date.isoformat(),
        "timezone_offset_hours": tz_offset_hours,
        "total_events": len(filtered_events),
        "categorized": categorized,
        "raw_events_count": len(all_events)
    }


# -------------------------------------------------------------
# Phương pháp 2: Search API (/search/issues & /search/commits)
# -------------------------------------------------------------
def crawl_user_activity_via_search(client: GitHubClient, username: str, target_date: date) -> Dict[str, Any]:
    """
    Crawl hoạt động của user trong ngày target_date thông qua Search API.
    Hỗ trợ tìm bất kỳ ngày nào trong lịch sử.
    """
    date_str = target_date.isoformat()
    print(f"[*] [Search API] Đang tìm kiếm Issues & PRs tạo bởi '{username}' ngày {date_str}...")

    categorized = {
        "prs_created": [],
        "issues_created": [],
        "prs_reviewed": [],
        "items_commented": [],
        "commits": []
    }

    # 1. Tìm PRs được tạo ngày hôm đó: author:USER type:pr created:YYYY-MM-DD
    try:
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

    # 2. Tìm Issues được tạo ngày hôm đó: author:USER type:issue created:YYYY-MM-DD
    try:
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

    # 3. Tìm PRs được review bởi user vào ngày đó: reviewed-by:USER type:pr updated:YYYY-MM-DD
    try:
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

    # 4. Tìm các Issue/PR có user bình luận vào ngày đó: commenter:USER updated:YYYY-MM-DD
    try:
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

    # 5. Tìm Commits được commit ngày hôm đó: author:USER author-date:YYYY-MM-DD
    try:
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

    total_items = (
        len(categorized["prs_created"]) +
        len(categorized["issues_created"]) +
        len(categorized["prs_reviewed"]) +
        len(categorized["items_commented"]) +
        len(categorized["commits"])
    )

    return {
        "method": "search_api",
        "username": username,
        "date": date_str,
        "total_results": total_items,
        "categorized": categorized
    }


# -------------------------------------------------------------
# Xuất báo cáo Markdown
# -------------------------------------------------------------
def generate_markdown_report(data: Dict[str, Any]) -> str:
    """Tạo báo cáo tóm tắt Markdown đẹp mắt từ dữ liệu đã crawl."""
    username = data["username"]
    date_str = data["date"]
    method = data["method"]
    cat = data.get("categorized", {})

    lines = []
    lines.append(f"# 📊 Báo Cáo Hoạt Động GitHub: @{username}")
    lines.append(f"- **Ngày:** `{date_str}`")
    lines.append(f"- **Phương thức crawl:** `{method}` ({'Activity Events API' if method == 'events_api' else 'REST Search API'})")
    lines.append(f"- **Thời gian xuất báo cáo:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append("")
    lines.append("---")

    if method == "events_api":
        commits = cat.get("commits", [])
        prs = cat.get("pull_requests", [])
        issues = cat.get("issues", [])
        comments = cat.get("issue_comments", [])
        reviews = cat.get("pr_reviews", [])
        review_comments = cat.get("pr_review_comments", [])
        branches = cat.get("branch_and_tag_creations", [])
        stars = cat.get("stars", [])
        forks = cat.get("forks", [])

        lines.append("## 📈 Thống Kê Tổng Quan")
        lines.append(f"| Hoạt động | Số lượng |")
        lines.append(f"| :--- | :--- |")
        lines.append(f"| 🔨 Commits đã push | **{len(commits)}** |")
        lines.append(f"| 🔀 Pull Requests thao tác | **{len(prs)}** |")
        lines.append(f"| 🐛 Issues thao tác | **{len(issues)}** |")
        lines.append(f"| 💬 Bình luận (Issue/PR) | **{len(comments)}** |")
        lines.append(f"| 👀 Reviews PR | **{len(reviews) + len(review_comments)}** |")
        lines.append(f"| 🌿 Nhánh/Tag đã tạo | **{len(branches)}** |")
        lines.append(f"| ⭐ Stars đã bấm | **{len(stars)}** |")
        lines.append(f"| 🍴 Repos đã fork | **{len(forks)}** |")
        lines.append("")

        if commits:
            lines.append("## 🔨 Commits Đã Đẩy Lên (Push)")
            for c in commits:
                lines.append(f"- [`{c['sha']}`]({c['url']}) trong **{c['repo']}** (`{c['branch']}`): {c['message']}")
            lines.append("")

        if prs:
            lines.append("## 🔀 Pull Requests")
            for pr in prs:
                action_text = f"[{pr['action'].upper()}]"
                merged_text = " *(Merged)*" if pr.get("merged") else ""
                lines.append(f"- {action_text} [#{pr['number']} {pr['title']}]({pr['url']}) tại **{pr['repo']}**{merged_text}")
            lines.append("")

        if issues:
            lines.append("## 🐛 Issues")
            for iss in issues:
                lines.append(f"- [{iss['action'].upper()}] [#{iss['number']} {iss['title']}]({iss['url']}) tại **{iss['repo']}**")
            lines.append("")

        if reviews or review_comments:
            lines.append("## 👀 Pull Request Reviews")
            for r in reviews:
                lines.append(f"- Review PR [#{r['pr_number']} {r['pr_title']}]({r['url']}) tại **{r['repo']}** (Trạng thái: `{r['state']}`)")
            for rc in review_comments:
                lines.append(f"- Nhận xét code PR [#{rc['pr_number']}]({rc['url']}) tại **{rc['repo']}**: *\"{rc['comment_body']}...\"*")
            lines.append("")

        if comments:
            lines.append("## 💬 Bình Luận Thảo Luận")
            for cm in comments:
                lines.append(f"- Bình luận tại {cm['type']} [#{cm['number']} {cm['title']}]({cm['url']}) (**{cm['repo']}**): *\"{cm['comment_body']}...\"*")
            lines.append("")

        if branches:
            lines.append("## 🌿 Nhánh & Tag Được Tạo")
            for b in branches:
                lines.append(f"- Tạo {b['type']} `{b['ref']}` trong repo **{b['repo']}**")
            lines.append("")

    else:
        # Search API report
        prs_created = cat.get("prs_created", [])
        issues_created = cat.get("issues_created", [])
        prs_reviewed = cat.get("prs_reviewed", [])
        items_commented = cat.get("items_commented", [])
        commits = cat.get("commits", [])

        lines.append("## 📈 Thống Kê Tổng Quan")
        lines.append(f"| Hoạt động | Số lượng |")
        lines.append(f"| :--- | :--- |")
        lines.append(f"| 🔨 Commits | **{len(commits)}** |")
        lines.append(f"| 🔀 Pull Requests tạo mới | **{len(prs_created)}** |")
        lines.append(f"| 🐛 Issues tạo mới | **{len(issues_created)}** |")
        lines.append(f"| 👀 PRs đã Review | **{len(prs_reviewed)}** |")
        lines.append(f"| 💬 Issues/PRs đã Comment/Cập nhật | **{len(items_commented)}** |")
        lines.append("")

        if commits:
            lines.append("## 🔨 Commits")
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
            lines.append("## 👀 PRs Đã Review")
            for pr in prs_reviewed:
                lines.append(f"- [{pr['title']}]({pr['url']}) (**{pr['repo']}**)")
            lines.append("")

        if items_commented:
            lines.append("## 💬 Issues/PRs Có Hoạt Động Bình Luận")
            for it in items_commented:
                lines.append(f"- ({it['type']}) [{it['title']}]({it['url']}) (**{it['repo']}**)")
            lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------
# Main CLI Entry Point
# -------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Crawl toàn bộ hoạt động của 1 GitHub User trong 1 ngày định sẵn."
    )
    parser.add_argument("username", help="GitHub username cần crawl (VD: torvalds, octocat)")
    parser.add_argument("date", help="Ngày cần crawl định dạng YYYY-MM-DD (VD: 2026-10-05)")
    parser.add_argument(
        "--mode",
        choices=["auto", "events", "search"],
        default="auto",
        help="Chế độ crawl: 'auto' (tự chọn), 'events' (GET /users/{u}/events), 'search' (GET /search/issues & /search/commits)"
    )
    parser.add_argument(
        "--token",
        default=None,
        help="GitHub Personal Access Token (tùy chọn nhưng khuyến nghị để tăng rate limit)"
    )
    parser.add_argument(
        "--tz",
        type=int,
        default=7,
        help="Múi giờ UTC offset (mặc định: +7 cho Việt Nam)"
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

    # Xác định mode
    today = datetime.now().date()
    days_ago = (today - target_date).days

    chosen_mode = args.mode
    if chosen_mode == "auto":
        # Events API chỉ lưu tối đa khoảng 30 ngày (hoặc 300 events)
        if 0 <= days_ago <= 30:
            chosen_mode = "events"
            print(f"[*] Chế độ 'auto': Ngày {args.date} cách đây {days_ago} ngày (<= 30 ngày) -> Sử dụng 'events' API.")
        else:
            chosen_mode = "search"
            print(f"[*] Chế độ 'auto': Ngày {args.date} cách đây {days_ago} ngày (> 30 ngày hoặc tương lai) -> Sử dụng 'search' API.")

    print(f"[*] Bắt đầu crawl hoạt động của user '{args.username}' vào ngày {args.date} (Múi giờ: UTC{'+' if args.tz >= 0 else ''}{args.tz})...")

    result_data = None
    if chosen_mode == "events":
        result_data = crawl_user_events_by_date(client, args.username, target_date, tz_offset_hours=args.tz)
        # Nếu sự kiện rỗng và ngày là gần đây, ta có thể bổ sung hoặc báo
        if result_data["total_events"] == 0 and days_ago > 3:
            print(f"[*] Cảnh báo: Events API không tìm thấy sự kiện nào cho ngày {args.date}. Có thể do user có hơn 300 sự kiện mới hơn hoặc ngày quá cũ.")
    else:
        result_data = crawl_user_activity_via_search(client, args.username, target_date)

    # Tạo thư mục output nếu chưa có
    os.makedirs(args.output_dir, exist_ok=True)
    json_path = os.path.join(args.output_dir, f"github_activity_{args.username}_{args.date}.json")
    md_path = os.path.join(args.output_dir, f"github_activity_{args.username}_{args.date}.md")

    # Lưu file JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    print(f"[✓] Đã xuất dữ liệu thô dạng JSON: {json_path}")

    # Lưu file Markdown
    md_content = generate_markdown_report(result_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"[✓] Đã xuất báo cáo đẹp dạng Markdown: {md_path}")

    print("\n" + "="*50)
    print(f"TỔNG KẾT HOẠT ĐỘNG: @{args.username} ({args.date})")
    print("="*50)
    cat = result_data.get("categorized", {})
    if chosen_mode == "events":
        print(f"• Commits pushed:          {len(cat.get('commits', []))}")
        print(f"• Pull Requests:           {len(cat.get('pull_requests', []))}")
        print(f"• Issues:                  {len(cat.get('issues', []))}")
        print(f"• Comments:                {len(cat.get('issue_comments', []))}")
        print(f"• Reviews:                 {len(cat.get('pr_reviews', [])) + len(cat.get('pr_review_comments', []))}")
        print(f"• Branches/Tags tạo mới:   {len(cat.get('branch_and_tag_creations', []))}")
    else:
        print(f"• Commits:                 {len(cat.get('commits', []))}")
        print(f"• PRs tạo mới:             {len(cat.get('prs_created', []))}")
        print(f"• Issues tạo mới:          {len(cat.get('issues_created', []))}")
        print(f"• PRs đã Review:           {len(cat.get('prs_reviewed', []))}")
        print(f"• Issue/PR thảo luận:      {len(cat.get('items_commented', []))}")
    print(f"Xem chi tiết đầy đủ trong: {md_path}")


if __name__ == "__main__":
    main()
