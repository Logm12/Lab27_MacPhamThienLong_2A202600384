# **HITL PR Review Agent (Pro Edition) \- Blueprint & Vision**

**Phiên bản:** Vibe Code Kit v6.0  
**Tình trạng:** APPROVED

## **1\. Tầm nhìn dự án (Vision)**

Xây dựng một hệ thống duyệt Pull Request (PR) thông minh, kết hợp giữa sức mạnh phân tích của AI và sự kiểm soát của con người (Human-in-the-Loop). Hệ thống không chỉ tự động hóa các tác vụ lặp đi lặp lại mà còn biết cách "hỏi" con người khi gặp các tình huống rủi ro cao, đảm bảo tính minh bạch thông qua Audit Trail và khả năng phục hồi dữ liệu mạnh mẽ.

### **Kiến trúc cốt lõi**

* **LangGraph Engine:** Điều phối luồng công việc dưới dạng State Machine.  
* **Streamlit Controller:** Giao diện tương tác thời gian thực, quản lý trạng thái và hiển thị Analytics.  
* **Persistent Layer:** SQLite lưu trữ cả Checkpoints (trạng thái Graph) và Audit Events (lịch sử quyết định).

### **Luồng trải nghiệm người dùng (User Flows)**

1. **Input:** Người dùng nhập URL PR và Token bảo mật.  
2. **Processing:** Agent phân tích mã nguồn và đưa ra điểm Confidence.  
3. **Decision:**  
   * \> 72%: Tự động duyệt.  
   * 58-72%: Tạm dừng, hiển thị Code Diff và lý do để người dùng phê duyệt/sửa/từ chối.  
   * \< 58%: Agent đặt ra các câu hỏi cụ thể để người dùng làm rõ ý đồ code.  
4. **Execution:** Sau khi có quyết định cuối cùng, kết quả được đẩy lên GitHub.

## **2\. Ma trận yêu cầu (Requirements Matrix \- RRI)**

| ID | Phân loại | Mô tả chi tiết   |
| :---- | :---- | :---- |
| REQ-UI-01 | Giao diện | Bố cục 2 cột: Bên trái hiển thị Code Diff, bên phải hiển thị phân tích và nút tương tác. |
| REQ-UI-02 | Giao diện | Thanh trạng thái Confidence đổi màu: Đỏ (\<58), Vàng (58-72), Xanh (\>72). |
| REQ-LOG-01 | Logic | Tách biệt node Commit Review để tránh gửi trùng lặp comment khi resume graph. |
| REQ-DAT-01 | Dữ liệu | Audit Trail lưu trữ vĩnh viễn các chỉ số: Faithfulness, Answer Relevance, Latency. |
| REQ-BNS-01 | Bonus | Dashboard Analytics hiển thị hiệu suất của AI dựa trên dữ liệu SQLite. |
| REQ-BNS-02 | Bonus | Tính năng Time-travel trong Advanced Mode để quay lại các checkpoint cũ. |

## **3\. Thiết kế chi tiết (Blueprint)**

### **Cấu trúc thư mục đề xuất**

`/project-root`  
`├── app.py                # Điểm chạy chính (Streamlit UI)`  
`├── engine/               # Logic LangGraph`  
`│   ├── graph.py          # Định nghĩa Nodes, Edges và State`  
`│   ├── nodes.py          # Chi tiết thực thi của từng node`  
`│   └── tools.py          # Các công cụ hỗ trợ (GitHub API, Audit helper)`  
`├── common/`                 
`│   ├── schemas.py        # Pydantic models và thresholds`  
`│   └── database.py       # Kết nối SQLite và AsyncSqliteSaver`  
`└── audit/`  
    `└── analytics.py      # Logic tính toán cho Dashboard`

### **Định nghĩa Data Schema (SQLite)**

Bảng audit\_events:

* thread\_id: ID phiên làm việc.  
* node: Tên bước thực hiện.  
* confidence: Điểm tin cậy của AI.  
* faithfulness: Độ trung thực của phản hồi.  
* answer\_relevance: Độ liên quan của câu trả lời.  
* latency\_ms: Thời gian xử lý.

### **Kế hoạch triển khai (TIPs Preview)**

* **TIP-001 (Core Graph):** Xây dựng State Machine cơ bản với LangGraph, tích hợp interrupt cho Human Approval.  
* **TIP-002 (UI Integration):** Phát triển giao diện Streamlit 2 cột, xử lý resume logic qua Command.  
* **TIP-003 (Audit & Persistence):** Triển khai AsyncSqliteSaver và lưu trữ AuditEntry vào DB.  
* **TIP-004 (Advanced Features):** Xây dựng Dashboard và cơ chế Time-travel.

## **4\. Giao kèo (Contract)**

* **Phạm vi:** Hoàn thành bài Lab PR Review Agent kèm tất cả tính năng Bonus đã chốt.  
* **Cam kết:** Code sạch, modular, không có lỗi logic/syntax, tuân thủ nguyên tắc bảo mật token.