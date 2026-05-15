# **TIP-002: Streamlit UI, Analytics & Time-Travel Integration**

**Project:** HITL PR Review Agent (Pro Edition)  
**Priority:** P0 (Core UX)  
**Estimated Effort:** 8-10 hours  
**Depends on:** TIP-001 (Graph Scaffolding)

## ---

**1\. CONTEXT & DIRECTORY**

Nhiệm vụ này chuyển trọng tâm từ Backend sang **Interface Layer**. Thợ thi công sẽ hoàn thiện file app.py và tích hợp các tính năng Bonus để biến Agent thành một sản phẩm thương mại hoàn chỉnh.  
**Working Directory:** ./, ./audit/  
**Core Files:**

* app.py: Entry point của Streamlit.  
* audit/analytics.py: Logic truy vấn dữ liệu từ SQLite.  
* common/database.py: Cần bổ sung logic switch DB config (Scale-ready).

## ---

**2\. TASK DESCRIPTION**

1. **Main Interface (REQ-UI-01):** Thiết kế bố cục 2 cột bằng st.columns(\[2, 1\]). Cột trái hiển thị Markdown Diff, cột phải hiển thị Card phân tích của AI.  
2. **Confidence Bar (REQ-UI-02):** Implement thanh progress bar tùy chỉnh bằng CSS.  
   * \< 58%: Red.  
   * 58% \- 72%: Yellow.  
   * \> 72%: Green.  
3. **Dynamic HITL Rendering:**  
   * **Approval Card:** Hiển thị 3 nút Approve / Reject / Edit.  
   * **Escalation Form (REQ-LOG-02):** Mỗi câu hỏi của AI phải là một st.text\_input riêng biệt trong st.form.  
4. **Advanced Mode & Time-travel (REQ-BNS-02):** Trong Sidebar, thêm toggle "Advanced Mode". Khi bật, hiển thị danh sách checkpoint từ app.aget\_state\_history và cho phép user resume từ bất kỳ điểm nào.  
5. **Analytics Dashboard (REQ-BNS-01):** Tạo một Tab "Analytics" sử dụng st.metric và st.bar\_chart để hiển thị AVG(confidence) và tỷ lệ phê duyệt từ bảng audit\_events.

## ---

**3\. SPECIFICATIONS & RULES**

* **Scale-Ready Architecture:** Tuyệt đối không hardcode SQL query trong app.py. Mọi truy vấn phải thông qua module audit/analytics.py. Đường dẫn DB phải lấy từ os.getenv("DATABASE\_URL").  
* **Vibe Code UI:** Sử dụng st.status để tạo cảm giác Agent đang suy nghĩ. Không dùng st.write thô cho các Object phức tạp.  
* **Security:** Input Token GitHub phải dùng type="password". Không bao giờ log Token ra console hoặc UI.  
* **Cleanup:** Trước khi bàn giao, phải chạy script dọn dẹp các tệp tin .tmp, hitl\_audit.db-journal và các cache của Streamlit.

## ---

**4\. ACCEPTANCE CRITERIA (Gherkin)**

`Scenario: User performs Time-travel`  
    `Given the app is in 'Advanced Mode'`  
    `When I select a checkpoint from 2 steps ago`  
    `Then the UI should refresh to show the state at that time`  
    `And I should be able to provide a new decision from that point`

`Scenario: Analytics are accurate`  
    `Given multiple PR reviews have been completed`  
    `When I open the 'Analytics' tab`  
    `Then I should see a bar chart showing the confidence trend`  
    `And the AVG confidence metric should match the database records`

## ---

**5\. REPORT FORMAT**

Thợ thi công báo cáo theo mẫu **Completion Report**:

* STATUS: DONE / PARTIAL / BLOCKED  
* FILES CHANGED: \[list\]  
* SCALABILITY CHECK: \[X\] Env vars used for DB \[X\] Abstracted analytics logic  
* CLEANUP LOG: \[list of purged files\]  
* SUGGESTIONS FOR CONTRACTOR: \[nếu có\]