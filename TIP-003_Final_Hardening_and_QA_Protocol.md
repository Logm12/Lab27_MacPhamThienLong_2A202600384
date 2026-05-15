# **TIP-003: Final Integration, Escalation Synthesis & QA Protocol**

**Project:** HITL PR Review Agent (Pro Edition)  
**Priority:** P0 (Final Release)  
**Estimated Effort:** 6-8 hours  
**Depends on:** TIP-002 (UI & Analytics)

## ---

**1\. CONTEXT & DIRECTORY**

Dự án đã hoàn thành 85%. TIP-003 là chặng đường cuối để biến một bản demo thành một hệ thống **Production-Ready**. Thợ thi công cần tập trung vào việc khép kín luồng Escalation và thực hiện quy trình kiểm định nghiêm ngặt theo **QA Protocol**.  
**Working Directory:** ./engine/, ./audit/, ./tests/  
**Core Files:**

* engine/nodes.py: Cần hoàn thiện logic node\_synthesize.  
* common/database.py: Bổ sung Database Indexing cho hiệu năng lâu dài.  
* tests/qa\_verification.py: File mới để thực hiện QA Protocol.

## ---

**2\. TASK DESCRIPTION**

1. **Escalation Synthesis (REQ-LOG-02):**  
   * Hoàn thiện node\_synthesize: LLM phải đọc các câu trả lời (answers) từ Human, kết hợp với phân tích cũ để viết lại Review Comment cuối cùng.  
   * Đảm bảo Review Comment mới giải quyết được các "Red Flags" đã cảnh báo trước đó.  
2. **Long-term Scaling (REQ-DAT-01):**  
   * Trong common/database.py, thêm lệnh SQL CREATE INDEX cho các cột thread\_id và timestamp trong bảng audit\_events.  
   * Điều này đảm bảo Dashboard Analytics vẫn chạy nhanh khi số lượng PR lên đến hàng nghìn.  
3. **QA Protocol Tier 1 & 2 (REQ-LOG-01):**  
   * Xây dựng script kiểm thử tự động (hoặc bán tự động) để verify 100% REQ-IDs trong RRI Matrix.  
   * **Stress Test:** Giả lập trường hợp mạng chậm/API lỗi để kiểm tra Loading States và Error Messages.  
4. **Environment Hardening:**  
   * Chuyển cơ chế lưu Token từ Session State sang st.secrets hoặc mã hóa nhẹ trước khi lưu vào DB (nếu user chọn Remember me).  
   * Fix triệt để lỗi tiềm tàng 403 GitHub API bằng cách thêm check quyền (scope) trước khi Commit.

## ---

**3\. SPECIFICATIONS & RULES**

* **Vibe Code Rules:** Tuyệt đối không dùng try-except: pass. Mọi lỗi phải được log vào bảng audit\_events với risk\_level='high'.  
* **Data Integrity:** Đảm bảo AsyncSqliteSaver không tạo ra các file \-journal rác sau khi đóng ứng dụng.  
* **Cleanup:** Xóa sạch các folder scratch/, logs/ tạm và reset file hitl\_audit.db về trạng thái sạch (chỉ giữ schema) trước khi bàn giao bản Release.

## ---

**4\. ACCEPTANCE CRITERIA (Gherkin)**

`Scenario: Escalation flow closes correctly`  
    `Given a PR in 'Escalate' state with 2 questions answered`  
    `When node_synthesize is executed`  
    `Then the final review should contain references to those 2 answers`  
    `And the decision state should move to 'COMMIT'`

`Scenario: Database is optimized for scale`  
    `Given 5000 audit entries in the database`  
    `When a thread history query is executed`  
    `Then the execution time should be < 50ms (thanks to indexing)`

## ---

**5\. REPORT FORMAT**

Thợ thi công báo cáo theo mẫu **Completion Report**:

* STATUS: DONE / PARTIAL  
* QA REPORT: \[Đính kèm bảng Summary Tier 1 & 2\]  
* SCALABILITY: \[X\] DB Indexed \[X\] Memory usage optimized  
* CLEANUP LOG: \[X\] Scratch files removed \[X\] DB Reset  
* FINAL VERDICT: READY TO SHIP / NEEDS REFINE