import os
import sqlite3
import secrets
import mimetypes
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_file,
    send_from_directory,
    abort,
    jsonify,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "huubinhtm.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
STATIC_UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(STATIC_UPLOAD_FOLDER, exist_ok=True)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

    def get_db():
        # connect without automatic timestamp parsing to avoid older rows with mixed formats
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db():
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT,
                email TEXT UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_blocked INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                filesize INTEGER NOT NULL,
                uploaded_by INTEGER NOT NULL,
                upload_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expire_time TIMESTAMP NOT NULL,
                password TEXT,
                FOREIGN KEY(uploaded_by) REFERENCES users(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        # ensure email column exists for older DBs (avoid UNIQUE to prevent migration errors)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "email" not in columns:
            cur.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "full_name" not in columns:
            cur.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
        try:
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        except sqlite3.OperationalError:
            # if duplicate existing rows, skip creating unique index
            pass

        # bootstrap admin user
        cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO users (username, full_name, email, password, role, is_blocked) VALUES (?,?,?,?,?,0)",
                ("admin", "Administrator", "admin@example.com", generate_password_hash("admin123"), "admin"),
            )
        # bootstrap guest user for anonymous uploads
        cur.execute("SELECT id FROM users WHERE username = ?", ("guest",))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO users (username, full_name, email, password, role, is_blocked) VALUES (?,?,?,?,?,0)",
                ("guest", "Guest User", "guest@example.com", generate_password_hash("guest"), "user"),
            )
        conn.commit()
        conn.close()

    init_db()

    # ---------- settings helpers ----------
    def get_setting(key: str, default=None):
        conn = get_db()
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else default

    def set_setting(key: str, value: str):
        conn = get_db()
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
        conn.close()

    def get_guest_id():
        conn = get_db()
        row = conn.execute("SELECT id FROM users WHERE username = ?", ("guest",)).fetchone()
        conn.close()
        return row["id"] if row else None

    # shared upload handler
    def store_file(file_storage, user_id, link_password=None, expire_hours=24):
        safe_name = secure_filename(file_storage.filename)
        unique_token = secrets.token_urlsafe(6)
        stored_name = f"{unique_token}_{safe_name}"
        filepath = os.path.join(UPLOAD_FOLDER, stored_name)
        file_storage.save(filepath)
        filesize = os.path.getsize(filepath)
        # expire_hours == 0 means permanent (long-lived)
        expire_time = datetime.utcnow() + (timedelta(days=365 * 100) if expire_hours == 0 else timedelta(hours=expire_hours))
        expire_time_str = expire_time.strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()
        conn.execute(
            """
            INSERT INTO files (file_id, filename, filepath, filesize, uploaded_by, expire_time, password)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                unique_token,
                safe_name,
                filepath,
                filesize,
                user_id,
                expire_time_str,
                link_password,
            ),
        )
        conn.commit()
        conn.close()
        return {
            "file_id": unique_token,
            "filename": safe_name,
            "filesize": filesize,
            "expire_time": expire_time_str,
            "filepath": filepath,
            "password": link_password,
        }

    # ---------- helpers ----------
    def login_required(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            return func(*args, **kwargs)

        return wrapper

    def admin_required(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if session.get("role") != "admin":
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    def format_size(num_bytes: int) -> str:
        if num_bytes < 1024:
            return f"{num_bytes} B"
        if num_bytes < 1024 * 1024:
            return f"{num_bytes/1024:.1f} KB"
        return f"{num_bytes/1024/1024:.1f} MB"

    app.jinja_env.globals.update(format_size=format_size)

    # ---------- blog data ----------
    BLOG_POSTS = [
        {
            "slug": "vps-la-gi-huong-dan-cho-nguoi-moi",
            "title": "VPS là gì? Hướng dẫn cho người mới",
            "desc": "Hiểu VPS, nguyên lý hoạt động, khi nào dùng và cách chọn nhà cung cấp phù hợp.",
            "image": "/public/qc/demo1.png",
            "date": "12 May 2025",
            "sections": [
                {
                    "heading": "Những điểm chính",
                    "body": [],
                    "list": [
                        "Khái niệm: VPS là máy chủ ảo (Virtual Private Server) có tài nguyên và hệ điều hành riêng.",
                        "Thời điểm sử dụng: Nên chuyển từ Shared Hosting sang VPS khi cần hiệu suất và quyền kiểm soát cao hơn.",
                        "Nguyên lý hoạt động: Ảo hóa chia máy chủ vật lý thành nhiều môi trường độc lập, cô lập tài nguyên.",
                        "So sánh dịch vụ: VPS nằm giữa Shared Hosting và Dedicated Server về chi phí và quyền kiểm soát.",
                        "Thông số kỹ thuật: CPU, RAM, SSD, Bandwidth, hệ điều hành quyết định hiệu năng.",
                        "Ưu nhược điểm: Hiệu năng và linh hoạt cao nhưng đòi hỏi kỹ năng quản trị.",
                        "Ứng dụng thực tế: Lưu trữ web, chạy ứng dụng, mail/proxy/VPN, môi trường test.",
                        "Chọn nhà cung cấp: Ưu tiên uy tín, hiệu suất, vị trí DC, hỗ trợ 24/7, giá minh bạch.",
                    ],
                },
                {
                    "heading": "VPS là gì?",
                    "body": [
                        "VPS là máy chủ ảo được tạo ra bằng cách phân chia tài nguyên từ một máy chủ vật lý thành nhiều môi trường độc lập, giúp người dùng toàn quyền quản lý và cài đặt như trên máy chủ riêng.",
                        "Nhờ tính linh hoạt, hiệu năng ổn định và chi phí tối ưu, VPS trở thành giải pháp lưu trữ lý tưởng cho doanh nghiệp và cá nhân phát triển website, ứng dụng hoặc hệ thống trực tuyến.",
                        "Trong bài viết này, chúng ta sẽ hiểu rõ VPS là gì, nguyên lý hoạt động và lý do vì sao VPS được xem là lựa chọn thay thế cân bằng cho máy chủ vật lý truyền thống."
                    ],
                    "list": [],
                },
                {
                    "heading": "Ví dụ dễ hình dung",
                    "level": 3,
                    "body": [
                        "Nếu Shared Hosting giống như thuê một phòng trong ký túc xá (chia sẻ tài nguyên), thì VPS giống như một căn hộ riêng trong chung cư: bạn có chìa khóa (quyền root), không gian riêng (tài nguyên được đảm bảo) và ít bị ảnh hưởng bởi hàng xóm."
                    ],
                    "list": [],
                },
                {
                    "heading": "Khi nào nên sử dụng VPS?",
                    "body": [
                        "Chọn VPS khi website/ứng dụng tăng traffic, cần tài nguyên riêng để đảm bảo hiệu suất và ổn định."
                    ],
                    "list": [
                        "Chạy web/ API có lưu lượng lớn, cần worker, queue, cron.",
                        "Cần cài đặt phần mềm tùy chỉnh: Redis, RabbitMQ, Docker, ffmpeg...",
                        "Vận hành TMĐT, xử lý dữ liệu nhạy cảm, yêu cầu bảo mật cao.",
                        "Muốn mở rộng tài nguyên linh hoạt mà không phải di chuyển dữ liệu sang server mới ngay.",
                    ],
                },
                {
                    "heading": "VPS hoạt động như thế nào?",
                    "body": [
                        "Máy chủ vật lý được cài hypervisor (KVM, VMware, Xen...). Hypervisor chia CPU, RAM, disk thành nhiều máy ảo cô lập; mỗi VPS có hệ điều hành và tài nguyên riêng, không ảnh hưởng lẫn nhau.",
                        "Người dùng truy cập qua SSH/RDP, cài đặt web server, DB, bảo mật tùy ý nhưng vẫn nằm trên cùng phần cứng vật lý.",
                    ],
                    "list": [],
                },
                {
                    "heading": "Kiến trúc VPS minh họa",
                    "image": "/public/qc/vpslagi.png",
                    "caption": "Hypervisor tách tài nguyên vật lý thành nhiều VPS độc lập.",
                    "body": [],
                    "list": [],
                },
                {
                    "heading": "So sánh VPS, Shared Hosting, Dedicated Server",
                    "body": [],
                    "list": [
                        "Chi phí: Shared (thấp) < VPS (trung bình) < Dedicated (cao).",
                        "Tài nguyên: Shared chia sẻ hoàn toàn; VPS có phần riêng được đảm bảo; Dedicated toàn bộ phần cứng.",
                        "Quyền kiểm soát: Shared hạn chế; VPS quyền root/administrator; Dedicated toàn quyền.",
                        "Bảo mật & cô lập: VPS cao hơn Shared, thấp hơn Dedicated.",
                        "Hiệu năng: VPS ổn định hơn Shared, thấp hơn Dedicated nhưng đủ cho đa số ứng dụng SMB.",
                    ],
                },
                {
                    "heading": "Thông số kỹ thuật quan trọng",
                    "body": [
                        "Nắm ý nghĩa từng thông số để chọn cấu hình phù hợp nhu cầu.",
                    ],
                    "list": [
                        "CPU: số lõi/xung, quyết định khả năng xử lý song song.",
                        "RAM: dung lượng bộ nhớ tạm cho ứng dụng và cache.",
                        "SSD/NVMe: tốc độ I/O, ảnh hưởng trực tiếp đến DB và web động.",
                        "Bandwidth: lưu lượng truyền tải/tháng; lưu lượng cao cần băng thông lớn.",
                        "Hệ điều hành: Linux/Windows ảnh hưởng môi trường phần mềm và bảo mật.",
                    ],
                },
                {
                    "heading": "Ưu điểm của VPS",
                    "body": [],
                    "list": [
                        "Tài nguyên riêng, hiệu năng ổn định, ít bị ảnh hưởng chéo.",
                        "Quyền kiểm soát cao: cài bất kỳ stack, tối ưu hệ thống.",
                        "Bảo mật tốt hơn shared: cô lập tiến trình, IP riêng.",
                        "Mở rộng nhanh: nâng CPU/RAM/SSD trong vài phút.",
                        "Chi phí hợp lý so với Dedicated, phù hợp giai đoạn scale-up.",
                    ],
                },
                {
                    "heading": "Nhược điểm cần lưu ý",
                    "body": [],
                    "list": [
                        "Đòi hỏi kiến thức quản trị server (CLI, bảo mật, backup).",
                        "Chi phí cao hơn Shared Hosting.",
                        "Hiệu năng phụ thuộc máy chủ vật lý; không co giãn tức thời như Cloud Server thuần túy.",
                        "Bạn chịu trách nhiệm cập nhật, vá bảo mật và giám sát.",
                    ],
                },
                {
                    "heading": "Ứng dụng thực tế của VPS",
                    "body": [],
                    "list": [
                        "Lưu trữ website, blog, landing page nhiều traffic.",
                        "Chạy API/backend, microservice, webhook.",
                        "Mail server, proxy, VPN riêng, game server nhỏ.",
                        "Môi trường dev/stage/test, CI/CD runner, build server.",
                        "Backup dữ liệu, lưu trữ file đa phương tiện.",
                    ],
                },
                {
                    "heading": "Cách chọn nhà cung cấp VPS",
                    "body": [],
                    "list": [
                        "Ưu tiên nhà cung cấp uy tín, cam kết uptime rõ ràng.",
                        "Hạ tầng và hiệu suất: CPU mới, NVMe, băng thông rộng, có IPv6.",
                        "Vị trí datacenter gần người dùng chính.",
                        "Hỗ trợ kỹ thuật 24/7, đa kênh; SLA minh bạch.",
                        "Giá và phụ phí rõ ràng (băng thông, IP, snapshot, backup).",
                    ],
                },
                {
                    "heading": "FileShare – VPS tốc độ cao, ổn định",
                    "body": [
                        "FileShare cung cấp gói VPS cấu hình linh hoạt, uptime cao, hạ tầng hiện đại và đội ngũ hỗ trợ 24/7. Phù hợp cho cá nhân, SMB và doanh nghiệp cần môi trường ổn định với chi phí hợp lý.",
                        "Nếu bạn cần hiệu năng mạnh, quyền tùy chỉnh cao nhưng tối ưu chi phí, đây là lựa chọn đáng cân nhắc. Liên hệ để được tư vấn nhanh."
                    ],
                    "list": [],
                },
                {
                    "heading": "Thông tin liên hệ FileShare",
                    "level": 3,
                    "body": [],
                    "list": [
                        "Website: https://VpsHuuBinhTM.VN/",
                        "Hotline: 0977.367.398",
                        "Email: sales@FileShare.com.vn",
                        "Địa chỉ: 139 Đông Hội - Đông Anh - Hà Nội",
                    ],
                },
            ],
        },
        {
            "slug": "so-sanh-vps-vs-shared-hosting",
            "title": "So sánh VPS vs Shared Hosting",
            "desc": "Hiểu rõ khác biệt VPS và Hosting, ưu nhược điểm và khi nào nên chọn mỗi dịch vụ.",
            "image": "/public/qc/demo2.png",
            "date": "10 May 2025",
            "sections": [
                {
                    "heading": "Tổng quan",
                    "body": [
                        "Nếu bạn đang phân vân giữa VPS và Hosting, điểm khó nhất là hiểu rõ khái niệm và sự khác biệt thực tế. Bài viết này tóm lược và so sánh chi tiết để bạn chọn đúng dịch vụ."
                    ],
                    "list": [],
                },
                {
                    "heading": "VPS là gì?",
                    "body": [
                        "VPS (Virtual Private Server) là máy chủ ảo được tách ra từ máy chủ vật lý bằng công nghệ ảo hóa. Mỗi VPS có hệ điều hành, CPU, RAM, ổ đĩa, IP riêng và quyền quản trị root/administrator.",
                        "Giá cao hơn shared hosting nhưng bù lại bạn có tài nguyên riêng, hiệu năng ổn định và có thể cài bất kỳ phần mềm nào.",
                    ],
                    "list": [],
                },
                {
                    "heading": "Kiến trúc VPS minh họa",
                    "image": "/public/qc/ad3.jpg",
                    "caption": "Hypervisor tách tài nguyên vật lý thành nhiều VPS độc lập.",
                    "body": [],
                    "list": [],
                },
                {
                    "heading": "Ưu nhược điểm VPS",
                    "body": [],
                    "list": [
                        "Ưu: Tài nguyên riêng, hiệu năng ổn định, dễ nâng cấp, bảo mật cao hơn shared, toàn quyền cấu hình.",
                        "Nhược: Chi phí cao hơn hosting, cần kiến thức quản trị; vẫn phụ thuộc phần cứng vật lý và không co giãn nhanh như cloud thuần.",
                    ],
                },
                {
                    "heading": "Hosting (Shared Hosting) là gì?",
                    "body": [
                        "Hosting là dịch vụ lưu trữ web dùng chung tài nguyên trên một máy chủ. Nhiều website cùng chia sẻ CPU, RAM, băng thông và được nhà cung cấp quản lý.",
                        "Phù hợp website/blog nhỏ, chi phí thấp, không cần cấu hình phức tạp."
                    ],
                    "list": [],
                },
                {
                    "heading": "Ưu nhược điểm Hosting",
                    "body": [],
                    "list": [
                        "Ưu: Chi phí rẻ, có sẵn cPanel/DirectAdmin, email dưới tên miền, hỗ trợ kỹ thuật; triển khai nhanh.",
                        "Nhược: Tài nguyên hạn chế, dễ bị ảnh hưởng bởi website khác, quyền quản trị thấp, khó cài dịch vụ tùy chỉnh, bảo mật phụ thuộc nhà cung cấp.",
                    ],
                },
                {
                    "heading": "Khác biệt lớn nhất",
                    "body": [],
                    "list": [
                        "Tài nguyên: VPS có phần tài nguyên riêng; hosting chia sẻ cho nhiều tài khoản.",
                        "Quyền kiểm soát: VPS có root; hosting giới hạn thao tác hệ thống.",
                        "Hiệu năng & ổn định: VPS ít bị ảnh hưởng chéo; hosting dễ chậm khi có website khác load cao.",
                        "Bảo mật: VPS cô lập tốt hơn; hosting rủi ro lây nhiễm từ site khác.",
                        "Mở rộng: VPS nâng cấp nhanh CPU/RAM; hosting bị giới hạn gói.",
                        "Chi phí: Hosting rẻ nhất; VPS cao hơn nhưng rẻ hơn Dedicated.",
                    ],
                },
                {
                    "heading": "Nên chọn VPS khi",
                    "body": [],
                    "list": [
                        "Website/ứng dụng đang tăng trưởng, cần tài nguyên riêng và uptime ổn định.",
                        "Cần cài đặt dịch vụ tùy chỉnh (Redis, RabbitMQ, Docker, ffmpeg...).",
                        "Muốn toàn quyền cấu hình, bảo mật và tối ưu hiệu năng.",
                        "Có ngân sách trung bình và cần hỗ trợ 24/7.",
                    ],
                },
                {
                    "heading": "Nên chọn Hosting khi",
                    "body": [],
                    "list": [
                        "Website/blog nhỏ, traffic thấp (<~500 lượt/ngày).",
                        "Ưu tiên chi phí rẻ, không cần quản trị máy chủ.",
                        "Muốn triển khai nhanh, dùng sẵn email, cPanel/DirectAdmin.",
                    ],
                },
                {
                    "heading": "Gợi ý gói dịch vụ FileShare",
                    "body": [],
                    "list": [
                        "VPS: Giá Rẻ (cân bằng chi phí/hiệu năng), Phổ Thông (linh hoạt), Cao Cấp (chống DDoS, game), VPS GPU, VPS NVMe.",
                        "Hosting: Giá Rẻ (cá nhân, mới bắt đầu), Cao Cấp (traffic vừa/lớn), Business Hosting (doanh nghiệp), SEO Hosting (nhiều IP), WordPress Hosting.",
                    ],
                },
                {
                    "heading": "Lời kết",
                    "body": [
                        "VPS phù hợp khi bạn cần quyền kiểm soát và tài nguyên riêng; Hosting phù hợp khi cần chi phí thấp và sự đơn giản. Xác định nhu cầu, ngân sách và mức tăng trưởng để chọn dịch vụ tối ưu."
                    ],
                    "list": [],
                },
            ],
        },
        {
            "slug": "huong-dan-cai-wordpress-tren-cpanel",
            "title": "Hướng dẫn chi tiết 2 cách cài WordPress trên cPanel",
            "desc": "Hướng dẫn cài WordPress tự động và thủ công trên cPanel, kèm chuẩn bị và mẹo tối ưu.",
            "image": "/public/qc/demo3.png",
            "date": "8 May 2025",
            "sections": [
                {
                    "heading": "Lợi ích khi cài WordPress trên cPanel",
                    "body": [],
                    "list": [
                        "Cài đặt nhanh: vài cú click là có WordPress kèm database và cấu hình ban đầu.",
                        "Tiết kiệm chi phí: chỉ cần hosting + domain; kho theme/plugin miễn phí phong phú.",
                        "Dễ dùng, không cần code: giao diện trực quan để viết bài, chỉnh sửa, quản lý user.",
                        "Tối ưu SEO: nhiều plugin SEO mạnh, dễ đạt thứ hạng Google.",
                        "Cộng đồng lớn: dễ tìm tài liệu, hỏi đáp khi gặp vấn đề.",
                    ],
                },
                {
                    "heading": "Gợi ý dịch vụ Vietnix",
                    "body": [
                        "Nếu cần tên miền và hosting tốc độ cao, tham khảo gói WordPress Hosting hoặc Business Hosting của Vietnix.",
                        "Xem gói tại: https://vietnix.vn/",
                    ],
                    "list": [],
                },
                {
                    "heading": "Chuẩn bị trước khi cài",
                    "body": [],
                    "list": [
                        "Tên miền: ngắn gọn, dễ nhớ, trỏ về hosting.",
                        "Gói hosting: đủ dung lượng, băng thông; hỗ trợ cPanel.",
                    ],
                },
                {
                    "heading": "Cách 1: Cài WordPress tự động trên cPanel",
                    "body": [],
                    "list": [
                        "B1: Đăng nhập cPanel (link nhà cung cấp, ví dụ https://host250.vietnix.vn:2083).",
                        "B2: Ở giao diện chính, tìm mục WordPress và mở trình cài đặt (Softaculous/WordPress Manager).",
                        "B3: Nhấn Install Now, cấu hình Domain, Protocol https, để trống In Directory, chọn version.",
                        "Site Settings: đặt Site Name, Description; tùy chọn Multisite, Cron.",
                        "Admin account: Username, Password, Email.",
                        "Language + Plugin tùy chọn (Loginizer, Classic Editor, wpCentral...).",
                        "B4: Advanced: đặt tên database, cấu hình backup rotation.",
                        "B5: Nhấn Install, đợi 3–4 phút; nhận link site + link admin.",
                        "B6: Mở domain để kiểm tra website hoạt động.",
                    ],
                },
                {
                    "heading": "Cách 2: Upload source WordPress thủ công",
                    "body": [],
                    "list": [
                        "Tải WordPress mới nhất: https://wordpress.org/download/",
                        "Đăng nhập cPanel → File Manager → vào public_html (hoặc thư mục addon domain).",
                        "Upload wordpress-xxx.zip → Extract → move toàn bộ file ra thư mục gốc site, xóa file .zip và thư mục wordpress/ rỗng.",
                        "Tạo database bằng MySQL Database Wizard: tạo DB, user, gán ALL PRIVILEGES; lưu DB name/user/pass/host.",
                        "Truy cập domain → màn hình setup WordPress → nhập thông tin DB → đặt Site Title, admin user/password/email → Install.",
                        "Đăng nhập quản trị tại /wp-admin bằng tài khoản vừa tạo.",
                    ],
                },
                {
                    "heading": "Cài bằng WordPress Toolkit (nếu được bật)",
                    "level": 3,
                    "body": [],
                    "list": [
                        "Trong cPanel tìm “WordPress” → WordPress Management/Toolkit.",
                        "Nhấn Install, chọn path (root hoặc /blog), tiêu đề site, admin user/pass; DB được tạo tự động → Install.",
                        "Toolkit hỗ trợ bảo mật (chặn PHP uploads, tắt XML-RPC), cập nhật core/theme/plugin, clone/staging, bật WP_DEBUG nhanh.",
                    ],
                },
                {
                    "heading": "Kiểm tra & xử lý lỗi thường gặp",
                    "body": [],
                    "list": [
                        "Không thấy Toolkit: cần nhà cung cấp bật license/feature trong WHM.",
                        "Lỗi Install/Clone: tăng PHP memory_limit, max_execution_time; kiểm tra quyền ghi thư mục.",
                        "Tính năng bị khóa: cần gói Toolkit Deluxe/Agency – liên hệ nhà cung cấp.",
                    ],
                },
                {
                    "heading": "Một số dạng website WordPress phổ biến",
                    "body": [],
                    "list": [
                        "Blog, portfolio, website doanh nghiệp/phi lợi nhuận.",
                        "Cửa hàng trực tuyến với WooCommerce.",
                        "Landing page, trang sự kiện, tài liệu nội bộ.",
                    ],
                },
                {
                    "heading": "Vietnix – Hosting tốc độ cao, bảo mật",
                    "body": [
                        "Hosting tối ưu tốc độ, nhiều lớp bảo mật, SSL miễn phí, backup hằng ngày; hỗ trợ 24/7.",
                    ],
                    "list": [
                        "Website: https://vietnix.vn/",
                        "Hotline: 18001093",
                        "Email: sales@vietnix.com.vn",
                        "Địa chỉ: 265 Hồng Lạc, Phường Bảy Hiền, TP. Hồ Chí Minh",
                    ],
                },
            ],
        },
        {
            "slug": "chmod-777-la-gi",
            "title": "Chmod 777 là gì? Cách sử dụng lệnh Chmod 777 chi tiết",
            "desc": "Giải thích chmod 777, rủi ro bảo mật và cách dùng/lựa chọn quyền an toàn hơn.",
            "image": "/public/qc/ad1.jpg",
            "date": "5 May 2025",
            "sections": [
                {
                    "heading": "Tóm tắt nhanh",
                    "body": [],
                    "list": [
                        "Chmod 777 cấp toàn bộ quyền đọc/ghi/thực thi cho tất cả user.",
                        "Rất nguy hiểm vì ai cũng chỉnh sửa/xóa/chèn mã độc được.",
                        "Cách thực thi qua terminal, FTP, cPanel.",
                        "Quyền thay thế an toàn: 755, 644, 555.",
                        "Gợi ý VPS Linux Vietnix để thử nghiệm an toàn.",
                        "FAQ: có nên dùng để sửa lỗi? quyền an toàn cho WordPress? ảnh hưởng SEO?",
                    ],
                },
                {
                    "heading": "chmod 777 là gì?",
                    "body": [
                        "Lệnh phân quyền trong Linux cấp full quyền (read=4, write=2, execute=1) cho owner/group/others (7-7-7).",
                        "Tiện nhưng tiềm ẩn rủi ro cao, dễ bị sửa/xóa file hoặc chèn mã độc.",
                    ],
                    "list": [],
                },
                {
                    "heading": "Giải thích 777",
                    "body": [],
                    "list": [
                        "Chữ số 1: owner = 7 (4+2+1).",
                        "Chữ số 2: group = 7.",
                        "Chữ số 3: others = 7.",
                    ],
                },
                {
                    "heading": "Tại sao chmod 777 nguy hiểm?",
                    "body": [],
                    "list": [
                        "Ai cũng có thể đọc/ghi/thực thi → dễ bị chèn mã độc, xoá dữ liệu.",
                        "Làm suy yếu sudo/setuid/setgid; sticky bit mất hiệu lực.",
                        "Tăng rủi ro bảo mật, log đầy rác, khó kiểm soát truy cập.",
                    ],
                },
                {
                    "heading": "Cách chạy chmod 777 trên Linux",
                    "body": [],
                    "list": [
                        "Terminal: chmod 777 <path>",
                        "Đệ quy: chmod -R 777 <thư_mục>",
                    ],
                },
                {
                    "heading": "Đặt chmod 777 qua FTP / cPanel",
                    "body": [],
                    "list": [
                        "FTP: đăng nhập → right-click file/folder → File permissions → nhập 777 → OK.",
                        "cPanel: File Manager → chọn file/folder → Change Permissions/Perms → nhập 777 → lưu.",
                    ],
                },
                {
                    "heading": "Quyền thay thế an toàn hơn",
                    "body": [],
                    "list": [
                        "chmod 755: owner full; group/others read+execute (thư mục web công khai).",
                        "chmod 644: owner read+write; group/others read (file nội dung).",
                        "chmod 555: chỉ đọc+execute, ngăn sửa đổi ngoài ý muốn.",
                    ],
                },
                {
                    "heading": "VPS Linux Vietnix: môi trường an toàn để thử lệnh",
                    "body": [
                        "VPS Linux SSD/NVMe, CPU mới, hỗ trợ nhiều distro, kỹ thuật 24/7.",
                    ],
                    "list": [
                        "Website: https://vietnix.vn/",
                        "Hotline: 1800 1093",
                        "Email: sales@vietnix.com.vn",
                        "Địa chỉ: 265 Hồng Lạc, Phường Bảy Hiền, TP. Hồ Chí Minh",
                    ],
                },
                {
                    "heading": "Câu hỏi thường gặp",
                    "body": [],
                    "list": [
                        "Có nên dùng 777 để sửa lỗi truy cập? Không, hãy sửa quyền sở hữu (chown) và đặt 755/644 phù hợp.",
                        "Quyền an toàn cho WordPress: thư mục 755, file 644; wp-config.php có thể 640.",
                        "Có ảnh hưởng SEO? Gián tiếp có, nếu 777 bị khai thác làm chèn mã độc/phishing khiến site bị cảnh báo.",
                    ],
                },
            ],
        },
        {
            "slug": "huong-dan-doi-port-ssh-ubuntu-an-toan",
            "title": "Hướng dẫn cách đổi Port SSH Ubuntu an toàn và chi tiết",
            "desc": "Đổi port SSH để giảm brute-force, kèm chuẩn bị, các bước và xử lý sự cố.",
            "image": "/public/qc/demo4.png",
            "date": "3 May 2025",
            "sections": [
                {
                    "heading": "Tóm tắt nhanh",
                    "body": [],
                    "list": [
                        "Lợi ích: giảm brute-force, tiết kiệm tài nguyên, log sạch hơn.",
                        "Chuẩn bị: quyền root/sudo, kết nối ổn định, chọn port 1024-65535 (tránh 80/443).",
                        "Quy trình 6 bước: đăng nhập, kiểm tra port, sửa sshd_config, mở firewall, restart sshd, kiểm tra kết nối.",
                        "Xử lý sự cố: dùng Console/VNC nếu mất kết nối; xem log nếu sshd không khởi động.",
                        "Lưu ý: tránh trùng port dịch vụ web; SELinux cần mở port mới nếu đang bật.",
                        "Tham khảo VPS Vietnix uptime 99.9%, hỗ trợ 24/7.",
                    ],
                },
                {
                    "heading": "Vì sao nên đổi port SSH Ubuntu?",
                    "body": [
                        "Bot thường quét cổng 22 để brute-force. Đổi sang port khác (ví dụ 2235) giúp giảm tấn công tự động.",
                        "Giảm tải CPU, log bớt rác, là lớp bảo vệ đầu tiên trước khi áp dụng SSH key/F2B."
                    ],
                    "list": [],
                },
                {
                    "heading": "Chuẩn bị trước khi thực hiện",
                    "body": [],
                    "list": [
                        "Quyền root hoặc sudo trên VPS.",
                        "Đang SSH được bình thường bằng port hiện tại.",
                        "Chọn port mới 1024-65535, không trùng dịch vụ khác (tránh 80, 443, 21). Ví dụ: 2222, 2235, 2022.",
                    ],
                },
                {
                    "heading": "Các bước đổi Port SSH Ubuntu",
                    "body": [],
                    "list": [
                        "B1: Đăng nhập VPS: ssh root@IP_VPS",
                        "B2: Kiểm tra port hiện tại: netstat -nltp | grep sshd hoặc ss -nltp | grep sshd",
                        "B3: Sửa /etc/ssh/sshd_config: bỏ #Port 22, đổi thành port mới (ví dụ 2235), giữ duy nhất một dòng Port.",
                        "B4: Mở port mới trên firewall:",
                        "- Firewalld: firewall-cmd --permanent --add-port=2235/tcp && firewall-cmd --reload",
                        "- UFW: ufw allow 2235/tcp && ufw reload",
                        "B5: Khởi động lại SSH: systemctl restart sshd",
                        "B6: Mở terminal mới kiểm tra: ssh -p 2235 root@IP_VPS. Thành công rồi mới đóng phiên cũ.",
                    ],
                },
                {
                    "heading": "Kiểm tra và xử lý lỗi phổ biến",
                    "body": [],
                    "list": [
                        "Không SSH được sau khi đổi: có thể quên mở firewall hoặc sai cấu hình. Đăng nhập Console/VNC của nhà cung cấp để sửa lại.",
                        "sshd không khởi động: kiểm tra log với journalctl -u sshd hoặc tail -f /var/log/secure để tìm lỗi cú pháp hoặc port trùng.",
                    ],
                },
                {
                    "heading": "Lưu ý quan trọng",
                    "body": [],
                    "list": [
                        "Tránh dùng port 80/443/8080 hoặc port đang dùng bởi dịch vụ khác.",
                        "Ghi nhớ port mới; nếu quên phải vào Console để khôi phục.",
                        "Nếu SELinux bật, cần thêm rule cho port mới (semanage port -a -t ssh_port_t -p tcp 2235).",
                    ],
                },
                {
                    "heading": "Dịch vụ VPS tốc độ cao tại Vietnix",
                    "body": [
                        "VPS NVMe, uptime 99.9%, backup tự động, hỗ trợ 24/7; phù hợp khi cần hiệu năng và độ ổn định cao."
                    ],
                    "list": [
                        "Website: https://vietnix.vn/",
                        "Hotline: 1800 1093",
                        "Email: sales@vietnix.com.vn",
                        "Địa chỉ: 265 Hồng Lạc, Phường Bảy Hiền, TP. Hồ Chí Minh",
                    ],
                },
            ],
        },
        {
            "slug": "cai-may-ao-vmware-tren-linux-va-windows",
            "title": "Chi tiết cách cài đặt máy ảo VMware trên Linux/Ubuntu và Windows 10",
            "desc": "Hướng dẫn cài máy ảo VMware trên Windows và Linux, so sánh Workstation, Player, VirtualBox, kèm FAQ.",
            "image": "/public/qc/demo5.png",
            "date": "1 May 2025",
            "sections": [
                {
                    "heading": "Những điểm chính",
                    "body": [],
                    "list": [
                        "Định nghĩa máy ảo, lý do nên dùng, cách hoạt động trên Linux.",
                        "VMware Workstation Pro miễn phí cho cá nhân; doanh nghiệp dùng subscription theo thiết bị.",
                        "Các phần mềm phổ biến: VMware Workstation, Player, VirtualBox.",
                        "Cài trên Windows & Linux: chọn ISO, phân bổ CPU/RAM, disk, cấu hình mạng.",
                        "So sánh Workstation vs Player vs VirtualBox.",
                        "Vietnix: nhà cung cấp VPS tốc độ cao.",
                        "FAQ về cài đặt máy ảo.",
                    ],
                },
                {
                    "heading": "Virtual Machine – hiểu đúng và cách hoạt động",
                    "body": [
                        "Máy ảo mô phỏng máy tính vật lý (CPU, RAM, disk, NIC) chạy trên phần cứng thật; hypervisor cách ly và phân bổ tài nguyên.",
                        "Mỗi VM là một hệ điều hành khách riêng, giao tiếp phần cứng qua hypervisor, cho phép nhiều OS chạy song song mà không xung đột.",
                    ],
                    "list": [],
                },
                {
                    "heading": "Lý do nên cài máy ảo trên server",
                    "body": [],
                    "list": [
                        "Hợp nhất máy chủ, giảm chi phí phần cứng.",
                        "Tách biệt tài nguyên, tăng bảo mật và ổn định.",
                        "Quản lý tài nguyên hiệu quả (CPU/RAM/disk theo VM).",
                        "Phát triển/kiểm thử với môi trường gần production.",
                    ],
                },
                {
                    "heading": "Ưu điểm trên Linux",
                    "body": [],
                    "list": [
                        "Phân tách tài nguyên rõ ràng giữa VM.",
                        "Dễ dựng môi trường dev/test mô phỏng production.",
                        "Cô lập tăng bảo mật; KVM tích hợp sẵn trên hầu hết distro.",
                    ],
                },
                {
                    "heading": "Thay đổi mới của VMware",
                    "body": [
                        "VMware thuộc Broadcom; tài liệu chuyển về trang Broadcom.",
                        "Workstation Pro miễn phí cho cá nhân; doanh nghiệp subscription.",
                        "Không cần license key để kích hoạt Workstation Pro cá nhân.",
                    ],
                    "list": [],
                },
                {
                    "heading": "Cách 1: Cài VMware Workstation 17 Pro trên Windows",
                    "body": [
                        "Tải từ Broadcom: https://knowledge.broadcom.com/external/article?articleNumber=368667 (chọn Workstation Pro, phiên bản Windows).",
                        "Chạy installer, accept EULA, tùy chọn thêm PATH, bật auto-update nếu muốn, tạo shortcut, Install → Finish.",
                        "Workstation Pro hỗ trợ Shared Clipboard giữa VM và host.",
                    ],
                    "list": [],
                },
                {
                    "heading": "Cách 2: Cài VMware Workstation 17 trên Ubuntu/Linux",
                    "body": [],
                    "list": [
                        "Tải bản Linux từ link trên.",
                        "chmod +x installer; cài yêu cầu gcc/build-essential: sudo apt update && sudo apt install gcc-12 libgcc-12-dev build-essential -y",
                        "Chạy installer: sudo ./tên_file_installer",
                        "Làm theo wizard (accept license, cập nhật, tham gia CEIP tùy ý) → mở được giao diện Workstation.",
                    ],
                },
                {
                    "heading": "Cách 3: Cài máy ảo bằng VMware Workstation Player",
                    "body": [
                        "Miễn phí, gọn nhẹ; tải tại: https://knowledge.broadcom.com/external/article?articleNumber=309355",
                        "Cài đặt Next/Next, chấp nhận EULA, tùy chọn shortcut, Install → Finish; giao diện sẵn sàng tạo VM.",
                    ],
                    "list": [],
                },
                {
                    "heading": "Cách 4: Tạo VM trên Linux bằng VirtualBox",
                    "body": [
                        "Tải VirtualBox phù hợp OS, chạy installer, Next qua các bước (chấp nhận cảnh báo network).",
                        "Sau khi finish, mở VirtualBox để tạo VM mới; lưu ý cấu hình mạng/driver để tránh lỗi hiệu suất.",
                    ],
                    "list": [],
                },
                {
                    "heading": "So sánh Workstation vs Player vs VirtualBox",
                    "body": [],
                    "list": [
                        "Workstation: nhiều tính năng (snapshot nâng cao, mạng ảo phức tạp), hợp cá nhân/pro/doanh nghiệp.",
                        "Player: miễn phí, nhẹ, giới hạn quản lý snapshot và tính năng nâng cao.",
                        "VirtualBox: mã nguồn mở, đa nền tảng, dễ dùng nhưng hiệu năng 3D và I/O thường kém Workstation.",
                    ],
                },
                {
                    "heading": "Lỗi thường gặp và gợi ý khắc phục",
                    "body": [],
                    "list": [
                        "VMware Tools không chạy: reinstall Tools, kiểm tra tương thích OS guest.",
                        "VM không boot OS: kiểm tra ISO, thứ tự boot, bật ảo hóa CPU (VT-x/AMD-V).",
                        "VirtualBox chậm/mạng lỗi: bật virtio/bridge phù hợp, cấp đủ RAM/CPU, cài Guest Additions.",
                    ],
                },
                {
                    "heading": "Vietnix – VPS tốc độ cao, ổn định",
                    "body": [
                        "VPS đa gói (Giá Rẻ, AMD, GPU), uptime 99.9%, hoàn tiền minh bạch, quản trị root đầy đủ.",
                        "VPS AMD tối ưu ảo hóa, xử lý tốt tác vụ nặng; hỗ trợ 24/7 qua Ticket/Livechat/Hotline.",
                    ],
                    "list": [
                        "Website: https://vietnix.vn/",
                        "Hotline: 1800 1093",
                        "Email: sales@vietnix.com.vn",
                        "Địa chỉ: 265 Hồng Lạc, Phường Bảy Hiền, TP. Hồ Chí Minh",
                    ],
                },
                {
                    "heading": "Câu hỏi thường gặp",
                    "body": [],
                    "list": [
                        "Khác biệt cài VM trên Windows vs Linux: Windows dùng Workstation; Linux có thêm KVM tích hợp.",
                        "Có chạy ứng dụng nặng trên VM? Có, nếu cấp đủ CPU/RAM và ảo hóa phần cứng bật.",
                        "Cài VMware trên Win 10 thế nào? (đã nêu ở Cách 1).",
                        "Phần mềm máy ảo nhẹ nhất? Player/VirtualBox; Workstation nhiều tính năng hơn.",
                    ],
                },
            ],
        },
    ]

    @app.context_processor
    def inject_brand():
        return {
            "logo_url": get_setting("logo_url", url_for("static", filename="img/logo-default.svg")),
        }

    # ---------- routes ----------
    @app.route("/")
    def home():
        if "user_id" in session:
            return redirect(url_for("dashboard"))
        guest_id = get_guest_id()
        conn = get_db()
        recent = conn.execute(
            "SELECT file_id, filename, filesize, password, expire_time FROM files WHERE uploaded_by = ? ORDER BY upload_time DESC LIMIT 5",
            (guest_id,),
        ).fetchall()
        conn.close()
        return render_template("home.html", recent=recent)

    @app.route("/public/<path:filename>")
    def public_files(filename):
        return send_from_directory(os.path.join(BASE_DIR, "public"), filename)

    @app.route("/blog")
    def blog():
        return render_template("blog.html", posts=BLOG_POSTS)

    @app.route("/blog/<slug>")
    def blog_detail(slug: str):
        post = next((p for p in BLOG_POSTS if p["slug"] == slug), None)
        if not post:
            abort(404)
        return render_template("blog_detail.html", post=post)

    @app.route("/dieu-khoan-su-dung")
    def terms():
        return render_template("terms.html")

    @app.route("/lien-he")
    def contact():
        return render_template("contact.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            conn = get_db()
            user = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            conn.close()
            if user and check_password_hash(user["password"], password):
                if user["is_blocked"]:
                    flash("Account is blocked. Please contact admin.", "error")
                else:
                    session["user_id"] = user["id"]
                    session["username"] = user["username"]
                    session["role"] = user["role"]
                    return redirect(url_for("dashboard"))
            else:
                flash("Invalid username or password", "error")
        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("password_confirm", "")
            if password != confirm:
                flash("Mật khẩu xác nhận không khớp", "error")
                return redirect(url_for("register"))
            if not username or not password or not email or not full_name:
                flash("Họ tên, username, email và mật khẩu cần điền đầy đủ", "error")
                return redirect(url_for("register"))
            if "@" not in email or email.startswith("@") or email.endswith("@"):
                flash("Email không hợp lệ", "error")
                return redirect(url_for("register"))
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO users (username, full_name, email, password, role, is_blocked) VALUES (?,?,?,?, 'user', 0)",
                    (username, full_name, email, generate_password_hash(password)),
                )
                conn.commit()
                flash("Account created. Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Username hoặc email đã tồn tại", "error")
            finally:
                conn.close()
        return render_template("register.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        conn = get_db()
        files = conn.execute(
            """
            SELECT f.*, u.username AS uploader
            FROM files f
            JOIN users u ON f.uploaded_by = u.id
            WHERE uploaded_by = ?
            ORDER BY upload_time DESC
            """,
            (session["user_id"],),
        ).fetchall()
        total_size = conn.execute(
            "SELECT COALESCE(SUM(filesize),0) FROM files WHERE uploaded_by = ?", (session["user_id"],)
        ).fetchone()[0]
        conn.close()
        cap_bytes = 5 * 1024 * 1024 * 1024  # 5GB per account
        used_mb = round(total_size / (1024 * 1024), 1)
        cap_mb = round(cap_bytes / (1024 * 1024), 1)
        percent = round((total_size / cap_bytes * 100), 1) if cap_bytes else 0
        return render_template(
            "dashboard.html",
            files=files,
            used_mb=used_mb,
            cap_mb=cap_mb,
            percent=percent,
        )

    @app.route("/upload", methods=["POST"])
    @login_required
    def upload():
        file = request.files.get("file")
        link_password = request.form.get("link_password") or None
        expire_hours = int(request.form.get("expire_hours", 24) or 24)
        if expire_hours not in (0, 1, 6, 12, 24, 48):
            expire_hours = 24
        # dashboard chỉ cho người đã đăng nhập, nên 0h = vĩnh viễn hợp lệ
        if expire_hours == 0:
            expire_hours = 0
        if not file or file.filename == "":
            flash("Please choose a file to upload", "error")
            return redirect(url_for("dashboard"))

        result = store_file(file, session["user_id"], link_password, expire_hours)

        flash("Upload success! Copy your download link below.", "success")
        session["last_link"] = url_for("download_file", file_id=result["file_id"], _external=True)
        return redirect(url_for("dashboard"))

    @app.route("/upload-ajax", methods=["POST"])
    def upload_ajax():
        file = request.files.get("file")
        link_password = request.form.get("link_password") or None
        expire_hours = int(request.form.get("expire_hours", 24) or 24)
        if not file or file.filename == "":
            return jsonify({"error": "Vui lòng chọn file"}), 400
        user_id = session.get("user_id") or get_guest_id()
        if expire_hours == 0 and not session.get("user_id"):
            return jsonify({"error": "Bạn cần đăng nhập để chọn lưu trữ vĩnh viễn"}), 403
        if expire_hours == 0 and session.get("user_id"):
            expire_hours = 0
        if expire_hours not in (0, 1, 6, 12, 24, 48):
            expire_hours = 24
        result = store_file(file, user_id, link_password, expire_hours)
        link = url_for("download_file", file_id=result["file_id"], _external=True)
        return jsonify(
            {
                "link": link,
                "file_id": result["file_id"],
                "filename": result["filename"],
                "password": bool(link_password),
                "expire_hours": expire_hours,
                "size": result["filesize"],
            }
        )

    def parse_ts(val: str) -> datetime:
        try:
            return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.fromisoformat(val)
            except ValueError:
                return datetime.utcnow()

    def get_file_row(file_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone()
        conn.close()
        return row

    @app.route("/file/<file_id>", methods=["GET", "POST"])
    def download_file(file_id):
        file_row = get_file_row(file_id)
        if not file_row:
            abort(404)

        if datetime.utcnow() > parse_ts(str(file_row["expire_time"])):
            flash("Link expired", "error")
            return redirect(url_for("home"))

        password_ok = False
        if file_row["password"]:
            if session.get(f"pw_ok_{file_id}"):
                password_ok = True
            elif request.method == "POST":
                provided = request.form.get("password", "")
                if provided == file_row["password"]:
                    session[f"pw_ok_{file_id}"] = True
                    password_ok = True
                else:
                    flash("Mật khẩu không đúng", "error")
            else:
                password_ok = False

        ready = password_ok or not file_row["password"]
        previewable = str(file_row["filename"]).lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".txt", ".html", ".htm")
        )
        return render_template(
            "download.html",
            file=file_row,
            ready=ready,
            link=url_for("download_direct", file_id=file_id),
            previewable=previewable,
            preview_url=url_for("preview_file", file_id=file_id),
        )

    @app.route("/file/<file_id>/download")
    def download_direct(file_id):
        file_row = get_file_row(file_id)
        if not file_row:
            abort(404)
        if datetime.utcnow() > parse_ts(str(file_row["expire_time"])):
            flash("Link expired", "error")
            return redirect(url_for("home"))
        if file_row["password"] and not session.get(f"pw_ok_{file_id}"):
            flash("Cần nhập mật khẩu trước khi tải", "error")
            return redirect(url_for("download_file", file_id=file_id))
        if not os.path.exists(file_row["filepath"]):
            abort(404)
        guessed, _ = mimetypes.guess_type(file_row["filename"])
        resp = send_file(
            file_row["filepath"],
            as_attachment=True,
            download_name=file_row["filename"],
            mimetype=guessed,
            conditional=False,
        )
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.route("/file/<file_id>/preview")
    def preview_file(file_id):
        file_row = get_file_row(file_id)
        if not file_row:
            abort(404)
        if datetime.utcnow() > parse_ts(str(file_row["expire_time"])):
            abort(410)
        if file_row["password"] and not session.get(f"pw_ok_{file_id}"):
            return redirect(url_for("download_file", file_id=file_id))
        if not os.path.exists(file_row["filepath"]):
            abort(404)
        lower = file_row["filename"].lower()
        if lower.endswith((".html", ".htm")):
            with open(file_row["filepath"], "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            from markupsafe import escape

            escaped = escape(content)
            html = f"<pre style='margin:0;padding:12px;font-family:monospace;white-space:pre-wrap;'>{escaped}</pre>"
            resp = app.response_class(html, mimetype="text/html")
        else:
            guessed, _ = mimetypes.guess_type(file_row["filename"])
            resp = send_file(file_row["filepath"], as_attachment=False, mimetype=guessed, conditional=False)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.route("/delete/<file_id>", methods=["POST"])
    @login_required
    def delete_file(file_id):
        conn = get_db()
        file_row = conn.execute(
            "SELECT * FROM files WHERE file_id = ?", (file_id,)
        ).fetchone()
        if not file_row:
            conn.close()
            abort(404)

        if file_row["uploaded_by"] != session.get("user_id") and session.get("role") != "admin":
            conn.close()
            abort(403)

        # remove file and db row
        try:
            if os.path.exists(file_row["filepath"]):
                os.remove(file_row["filepath"])
        except OSError:
            pass
        conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        conn.commit()
        conn.close()
        flash("File deleted", "success")
        return redirect(request.referrer or url_for("dashboard"))

    # ---------- admin ----------
    @app.route("/admin/dashboard")
    @login_required
    @admin_required
    def admin_dashboard():
        conn = get_db()
        stats = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM files) AS total_files,
                (SELECT COUNT(*) FROM users) AS total_users,
                (SELECT COALESCE(SUM(filesize),0) FROM files) AS total_size
            """
        ).fetchone()
        active_links = conn.execute(
            "SELECT COUNT(*) AS active_links FROM files WHERE expire_time > ?",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),),
        ).fetchone()["active_links"]
        recent_files = conn.execute(
            """
            SELECT f.file_id, f.filename, f.filesize, f.upload_time, f.password
            FROM files f
            ORDER BY f.upload_time DESC
            LIMIT 5
            """
        ).fetchall()
        recent_users = conn.execute(
            """
            SELECT id, username, is_blocked, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT 5
            """
        ).fetchall()
        conn.close()
        return render_template(
            "admin/admin_dashboard.html",
            stats=stats,
            active_links=active_links,
            recent_files=recent_files,
            recent_users=recent_users,
            page_title="Tổng quan hệ thống",
        )

    @app.route("/admin/files")
    @login_required
    @admin_required
    def admin_files():
        conn = get_db()
        files = conn.execute(
            """
            SELECT f.*, u.username AS uploader
            FROM files f
            JOIN users u ON f.uploaded_by = u.id
            ORDER BY upload_time DESC
            """
        ).fetchall()
        conn.close()
        return render_template("admin/manage_files.html", files=files, page_title="Quản lý Files")

    @app.route("/admin/users")
    @login_required
    @admin_required
    def admin_users():
        conn = get_db()
        users = conn.execute(
            """
            SELECT
                u.id,
                u.username,
                u.full_name,
                u.email,
                u.role,
                u.is_blocked,
                u.created_at,
                COUNT(f.id) AS file_count,
                COALESCE(SUM(f.filesize), 0) AS total_size
            FROM users u
            LEFT JOIN files f ON u.id = f.uploaded_by
            GROUP BY u.id
            ORDER BY u.created_at DESC
            """
        ).fetchall()
        conn.close()
        return render_template("admin/manage_users.html", users=users, page_title="Quản lý Users")

    @app.route("/admin/user/<int:user_id>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def edit_user(user_id):
        conn = get_db()
        user = conn.execute(
            "SELECT id, username, full_name, email, role, is_blocked, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not user:
            conn.close()
            abort(404)

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip()
            role = request.form.get("role", "user")
            new_password = request.form.get("password", "").strip()

            if not username or not email or not full_name:
                flash("Họ tên, tên tài khoản và email không được để trống", "error")
                conn.close()
                return redirect(request.url)

            conn.execute(
                "UPDATE users SET username = ?, full_name = ?, email = ?, role = ? WHERE id = ?",
                (username, full_name, email, role, user_id),
            )
            if new_password:
                conn.execute(
                    "UPDATE users SET password = ? WHERE id = ?",
                    (generate_password_hash(new_password), user_id),
                )
            conn.commit()
            conn.close()
            flash("Cập nhật người dùng thành công", "success")
            return redirect(url_for("admin_users"))

        # placeholders for fields chưa lưu trong DB
        last_login_at = None
        last_login_ip = None
        conn.close()
        return render_template(
            "admin/edit_user.html",
            user=user,
            last_login_at=last_login_at,
            last_login_ip=last_login_ip,
            page_title="Chỉnh sửa User",
        )

    @app.route("/admin/user/<int:user_id>/block", methods=["POST"])
    @login_required
    @admin_required
    def block_user(user_id):
        conn = get_db()
        conn.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        flash("User blocked", "success")
        return redirect(url_for("admin_users"))

    @app.route("/admin/user/<int:user_id>/unblock", methods=["POST"])
    @login_required
    @admin_required
    def unblock_user(user_id):
        conn = get_db()
        conn.execute("UPDATE users SET is_blocked = 0 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        flash("User unblocked", "success")
        return redirect(url_for("admin_users"))

    @app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def delete_user(user_id):
        conn = get_db()
        # remove files owned by user
        file_rows = conn.execute(
            "SELECT filepath, file_id FROM files WHERE uploaded_by = ?", (user_id,)
        ).fetchall()
        for row in file_rows:
            try:
                if os.path.exists(row["filepath"]):
                    os.remove(row["filepath"])
            except OSError:
                pass
        conn.execute("DELETE FROM files WHERE uploaded_by = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        flash("User deleted", "success")
        return redirect(url_for("admin_users"))

    @app.route("/admin/logo", methods=["POST"])
    @login_required
    @admin_required
    def update_logo():
        file = request.files.get("logo")
        if not file or file.filename == "":
            flash("Vui lòng chọn file logo", "error")
            return redirect(request.referrer or url_for("admin_dashboard"))
        filename = secure_filename(file.filename)
        if not filename.lower().endswith((".png", ".jpg", ".jpeg", ".svg")):
            flash("Chỉ hỗ trợ PNG, JPG, SVG", "error")
            return redirect(request.referrer or url_for("admin_dashboard"))
        token = secrets.token_hex(4)
        stored_name = f"logo_{token}_{filename}"
        save_path = os.path.join(STATIC_UPLOAD_FOLDER, stored_name)
        file.save(save_path)
        logo_url = url_for("static", filename=f"uploads/{stored_name}")
        set_setting("logo_url", logo_url)
        flash("Cập nhật logo thành công", "success")
        return redirect(request.referrer or url_for("admin_dashboard"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
