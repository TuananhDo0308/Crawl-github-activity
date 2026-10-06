# 🐙 GitHub Daily Activity Tracker (GitHub Search API Only)

Ứng dụng web và công cụ dòng lệnh thu thập và báo cáo toàn bộ dữ liệu hoạt động trong 1 ngày của GitHub User (**chỉ sử dụng GitHub REST Search API**).

Tài liệu chính thức:
* [GitHub Search Issues and Pull Requests](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests)
* [GitHub Search Commits](https://docs.github.com/en/rest/search/search#search-commits)

---

## 🔍 Dữ Liệu Được Thu Thập Qua Search API

Hệ thống sử dụng các bộ lọc qualifiers chuẩn xác của GitHub Search API để truy vấn theo ngày (`YYYY-MM-DD`):

1. **🔨 Commits đã viết:** `GET /search/commits?q=author:{username} author-date:{YYYY-MM-DD}`
   * Trả về SHA commit, commit message, tên repo và link xem commit.
2. **🔀 Pull Requests tạo mới:** `GET /search/issues?q=author:{username} type:pr created:{YYYY-MM-DD}`
   * Trả về tiêu đề PR, số PR, trạng thái (`open`/`closed`/`merged`), repo và link PR.
3. **🐛 Issues tạo mới:** `GET /search/issues?q=author:{username} type:issue created:{YYYY-MM-DD}`
   * Trả về tiêu đề Issue, trạng thái, repo và link Issue.
4. **👀 Pull Requests đã Review:** `GET /search/issues?q=reviewed-by:{username} type:pr updated:{YYYY-MM-DD}`
   * Trả về danh sách PR của đồng nghiệp mà bạn đã vào đọc và review duyệt code.
5. **💬 Thảo luận / Bình luận:** `GET /search/issues?q=commenter:{username} updated:{YYYY-MM-DD}`
   * Trả về các Issue hoặc PR mà bạn có để lại bình luận hoặc trao đổi trong ngày.

---

## 🚀 Cách Chạy Ứng Dụng

### Cách 1: Giao Diện Web & Đăng Nhập GitHub OAuth (Khuyên Dùng)

1. Khởi động Web Server:
   ```bash
   python3 server.py
   ```
2. Mở trình duyệt truy cập: `http://localhost:3000`
3. Tại giao diện:
   * **Đăng nhập bằng GitHub OAuth:** Bấm nút **"Đăng Nhập Với GitHub"** (hoặc cấu hình Client ID / Secret theo hướng dẫn trên màn hình).
   * **Hoặc đăng nhập bằng Token (PAT):** Chuyển sang tab **"Dùng Personal Access Token"** để đăng nhập ngay mà không cần tạo OAuth App.
4. Chọn ngày cần tra cứu và bấm **"Tìm Kiếm Hoạt Động"**.
5. Bấm **"Copy Báo Cáo Standup"** để copy báo cáo định dạng Markdown gửi sếp/nhóm hằng ngày!

---

### Cách 2: Chạy Bằng Dòng Lệnh (CLI)

```bash
# Cú pháp
python3 github_activity_crawler.py <username> <YYYY-MM-DD> [--token <TOKEN>]

# Ví dụ crawl ngày 2026-10-06
python3 github_activity_crawler.py torvalds 2026-10-06

# Ví dụ ngày xa trong quá khứ
python3 github_activity_crawler.py torvalds 2024-01-08 --token ghp_xxxx
```

Kết quả sẽ tự động được xuất ra 2 file:
* `github_activity_{username}_{date}.json`: Dữ liệu thô và cấu trúc JSON.
* `github_activity_{username}_{date}.md`: Báo cáo tóm tắt Markdown đẹp mắt.
