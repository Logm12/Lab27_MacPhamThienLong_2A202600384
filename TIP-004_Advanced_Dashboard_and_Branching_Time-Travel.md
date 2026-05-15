# **TIP-004: Advanced Dashboard Analytics & Branching Time-Travel**

**Project:** HITL PR Review Agent (Pro Edition)  
**Priority:** P1 (Bonus & Scaling)  
**Estimated Effort:** 6-8 hours  
**Depends on:** TIP-001, TIP-002, TIP-003 (All Core Modules Complete)

## ---

**1\. CONTEXT & DIRECTORY**

Dây chuyền sản xuất đã hoàn thiện luồng Happy Path. Nhiệm vụ cuối cùng là nâng cấp **Audit Replay** thành một trung tâm điều khiển thời gian và dashboard phân tích thông minh.  
**Working Directory:** ./audit/, ./engine/, ./app.py  
**Core Files:**

* audit/analytics.py: Bổ sung các truy vấn tương quan dữ liệu.  
* engine/graph.py: Cấu hình cơ chế fork/branching cho checkpoint.  
* app.py: UI điều khiển nâng cao.

## ---

**2\. TASK DESCRIPTION**

1. **Branching Time-Travel (REQ-BNS-02 \- Deep):**  
   * Khi người dùng chọn một checkpoint cũ trong Advanced Mode, hãy cho phép họ nhập một quyết định mới.  
   * Sử dụng app.ainvoke(Command(resume=new\_data), config) nhưng phải đảm bảo tạo ra một thread\_id con (branch) hoặc đánh dấu luồng audit mới để không ghi đè lên dữ liệu cũ.  
   * Mục tiêu: So sánh được kết quả Review giữa 2 hướng quyết định khác nhau trên cùng một PR.  
2. **Advanced Analytics Dashboard (REQ-BNS-01 \- Deep):**  
   * Xây dựng biểu đồ **Calibration Curve**: Hiển thị sự chênh lệch giữa điểm Confidence của AI và tỷ lệ Human Approve thực tế.  
   * Thêm bảng thống kê **Top Risk Files**: Dựa trên Audit Trail, liệt kê các file thường xuyên khiến AI bị low confidence (\< 58%).  
   * Hiển thị **Performance Metrics**: AVG Latency per Persona (User vs. QA vs. Developer).  
3. **Long-term Scalability & Security:**  
   * Tối ưu hóa Database: Đảm bảo các truy vấn Dashboard sử dụng idx\_thread\_time đã tạo ở TIP-003.  
   * Token Persistence: Cung cấp tùy chọn "Remember Token" (mã hóa cơ bản hoặc lưu vào .env.local) để không phải nhập lại mỗi khi mở app.  
4. **System Cleanup (Final Flush):**  
   * Xóa toàn bộ scratch/, \*.tmp, và các tệp tin backup sau khi đã verify xong.  
   * Đảm bảo hitl\_audit.db được dọn dẹp sạch dữ liệu rác, chỉ giữ lại schema và indexing cho buổi demo.

## ---

**3\. SPECIFICATIONS & RULES**

* **Vibe Code Enforcement:** Tiếp tục sử dụng Type-hints và Pydantic cho các Model Dashboard mới. Tuyệt đối không dùng any.  
* **Scope Guard:** Chỉ làm Dashboard và Time-travel logic. KHÔNG thay đổi logic lõi của LangGraph (phần routing) đã ổn định từ TIP-001.  
* **Vibe UI Style:** Sử dụng st.expander để ẩn các biểu đồ phức tạp, giữ cho giao diện chính gọn gàng.

## ---

**4\. ACCEPTANCE CRITERIA (Gherkin)**

Scenario: User forks an audit trail  
    Given an existing session for PR \#1 with decision 'Reject'  
    When I use Time-travel to jump back to 'route' node  
    And I provide a new decision 'Approve'  
    Then the system should create a NEW entry in audit\_events for the same PR  
    And I should be able to see both versions in the Replay Sidebar

Scenario: Analytics show correlation  
    Given multiple reviews with varying confidence  
    When I open the Dashboard  
    Then I should see a chart correlating 'Confidence Score' vs 'Decision Type'

## ---

**5\. REPORT FORMAT**

Thợ thi công báo cáo theo mẫu **Completion Report**:

* STATUS: DONE / PARTIAL  
* BRANCHING LOGIC: \[Mô tả cách xử lý thread\_id khi fork\]  
* DASHBOARD PREVIEW: \[Mô tả các biểu đồ mới đã thêm\]  
* FINAL CLEANUP: \[X\] Done  
* READY FOR SHIP: YES / NO