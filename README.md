# 🐙 GitHub User Daily Activity Crawler

Công cụ crawl và tổng hợp toàn bộ hoạt động của một GitHub User bất kỳ trong 1 ngày định trước (`YYYY-MM-DD`).

---

## 📌 Phân Tích & So Sánh Lựa Chọn API của GitHub

Để trả lời câu hỏi: *"Lấy những gì user đó làm trong 1 ngày định sẵn thì nên chọn API nào?"*, dưới đây là phân tích chi tiết dựa trên tài liệu chính thức của GitHub:

### 1. GitHub REST Search API (`/search/issues` & `/search/commits`)
*Tài liệu bạn cung cấp: [GitHub Search API Docs](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests)*

* **Cách hoạt động:** Dùng các bộ lọc qualifiers:
  - Pull Requests tạo trong ngày: `author:{user} type:pr created:YYYY-MM-DD`
  - Issues tạo trong ngày: `author:{user} type:issue created:YYYY-MM-DD`
  - PRs/Issues có comment: `commenter:{user} updated:YYYY-MM-DD`
  - PRs được user review: `reviewed-by:{user} type:pr updated:YYYY-MM-DD`
  - Commits tác giả đã tạo: `GET /search/commits?q=author:{user} author-date:YYYY-MM-DD`
* **Ưu điểm:**
  - **Truy vấn bất kỳ ngày nào trong lịch sử** (1 năm, 5 năm trước đều tìm được).
  - Trả về đầy đủ metadata về Issues, PRs, Commits.
* **Hạn chế:**
  - Rate limit riêng của Search API: tối đa 30 requests/phút (có Token) hoặc 10 requests/phút (không có Token).
  - Không ghi nhận được các hành vi ngoài commit/issue/pr như: tạo branch, tag, fork repo, star repo.

---

### 2. GitHub Activity Events API (`/users/{username}/events`)
*Tài liệu: [GitHub Events API Docs](https://docs.github.com/en/rest/activity/events)*

* **Cách hoạt động:** Lấy dòng thời gian (timeline stream) các sự kiện công khai của user.
* **Loại hoạt động bắt được:**
  - `PushEvent`: Các commit đã đẩy lên nhánh kèm message & SHA.
  - `PullRequestEvent`: Mở, đóng, merge Pull Request.
  - `IssuesEvent`: Mở, đóng Issue.
  - `IssueCommentEvent`: Bình luận thảo luận trong Issue hoặc PR.
  - `PullRequestReviewEvent`: Duyệt code / review PR.
  - `PullRequestReviewCommentEvent`: Bình luận trực tiếp trên từng dòng code diff.
  - `CreateEvent` / `DeleteEvent`: Tạo/xóa nhánh (branch) hoặc tag release.
  - `ForkEvent` / `WatchEvent`: Fork hoặc Star repository.
* **Ưu điểm:**
  - **Bắt trọn 100% mọi hành động thực tế** của lập trình viên trong ngày theo đúng thứ tự thời gian.
  - Rate limit tiêu chuẩn rất cao (5,000 req/giờ với Token).
  - Chỉ cần 1 đến 3 requests là lấy hết toàn bộ sự kiện.
* **Hạn chế:**
  - GitHub chỉ lưu trữ sự kiện trong **30 ngày gần nhất** (tối đa 300 sự kiện). Nếu ngày cần crawl nằm quá 30 ngày trước, Events API sẽ không có dữ liệu.

---

### 3. Bảng So Sánh Tổng Hợp

| Tiêu chí | 🔍 REST Search API | ⚡ Activity Events API |
| :--- | :--- | :--- |
| **Phạm vi ngày** | **Bất kỳ ngày nào trong lịch sử** | **30 ngày gần nhất** (tối đa 300 events) |
| **Hành động bắt được** | Issues, PRs, Comments, Commits | Commits, PRs, Issues, Comments, Reviews, Branch, Star, Fork |
| **Độ phủ hoạt động** | Khá (tập trung vào Code & Issue) | Rất cao (toàn bộ hành vi trên GitHub) |
| **Rate Limit** | 30 req/phút (Token) | 5,000 req/giờ (Token) |
| **Tình huống sử dụng** | Khi cần crawl **quá khứ xa** (> 30 ngày) | Khi crawl **hôm nay, hôm qua hoặc 1-30 ngày gần đây** |

> 💡 **Giải pháp trong tool:** Tool hỗ trợ chế độ **`auto` (mặc định)**:
> - Nếu ngày cần tra cứu nằm trong vòng 30 ngày gần đây ➔ Tự động dùng **Events API** để lấy chi tiết nhất.
> - Nếu ngày cần tra cứu cách đây hơn 30 ngày ➔ Tự động chuyển sang **Search API** để tra cứu dữ liệu lịch sử.
> - Bạn cũng có thể ép buộc chạy chế độ mong muốn bằng cờ `--mode events` hoặc `--mode search`.

---

## 🚀 Hướng Dẫn Sử Dụng

Tool được viết hoàn toàn bằng Python standard library (`urllib.request`), **không cần cài đặt thư viện phụ thuộc (`pip install`)**.

### 1. Cú pháp cơ bản

```bash
python3 github_activity_crawler.py <username> <YYYY-MM-DD> [tùy_chọn]
```

### 2. Các ví dụ thực tế

#### Ví dụ 1: Crawl hoạt động gần đây (chế độ auto / events)
```bash
python3 github_activity_crawler.py torvalds 2026-10-06
```

#### Ví dụ 2: Crawl một ngày bất kỳ trong quá khứ (dùng Search API)
```bash
python3 github_activity_crawler.py torvalds 2024-01-08 --mode search
```

#### Ví dụ 3: Chỉ định múi giờ (Mặc định UTC+7 cho Việt Nam)
```bash
# Múi giờ UTC (+0)
python3 github_activity_crawler.py torvalds 2026-10-05 --tz 0

# Múi giờ Việt Nam (UTC+7)
python3 github_activity_crawler.py octocat 2026-10-05 --tz 7
```

#### Ví dụ 4: Sử dụng GitHub Personal Access Token (Khuyến nghị để tránh bị giới hạn Rate Limit)
```bash
# Cách 1: Truyền trực tiếp qua flag --token
python3 github_activity_crawler.py torvalds 2026-10-06 --token ghp_xxxx

# Cách 2: Export biến môi trường
export GITHUB_TOKEN="ghp_xxxx"
python3 github_activity_crawler.py torvalds 2026-10-06
```

---

## 📂 Dữ Liệu Đầu Ra (Outputs)

Mỗi lần chạy, tool sẽ tự động xuất ra 2 file:

1. **File JSON (`github_activity_{username}_{date}.json`)**: Chứa toàn bộ dữ liệu thô và dữ liệu phân loại có cấu trúc để phục vụ lưu trữ vào Database hoặc xử lý tiếp bằng code.
2. **File Markdown (`github_activity_{username}_{date}.md`)**: Báo cáo tóm tắt trực quan, có bảng biểu thống kê, link commit, link PR/Issue để đọc nhanh hoặc gửi báo cáo công việc hằng ngày (Daily Standup).
