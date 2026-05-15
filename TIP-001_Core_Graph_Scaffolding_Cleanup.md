# **TIP-001: Core Graph Scaffolding & State Management**

**Project:** HITL PR Review Agent (Pro Edition)  
**Priority:** P0 (BLOCKER)  
**Estimated Effort:** 4-6 hours  
**Dependencies:** None (Initial Scaffold)

## ---

**1\. CONTEXT & DIRECTORY**

Dựa trên Blueprint v1.0, chúng ta sẽ bắt đầu xây dựng "Trái tim" của hệ thống \- **LangGraph Engine**. Thợ thi công cần chuyển đổi các bài tập rời rạc (Exercise 1-4) thành một module engine/ có khả năng mở rộng.  
**Working Directory:** ./engine/, ./common/  
**Core Files:**

* engine/graph.py: Định nghĩa State Machine.  
* engine/nodes.py: Logic của từng bước xử lý.  
* common/schemas.py: Các thresholds và Pydantic Models.  
* common/database.py: Setup SQLite persistence.

## ---

**2\. TASK DESCRIPTION**

1. **Refactor Scaffolding:** Tạo cấu trúc thư mục engine/ và common/. Di chuyển các model từ Exercise cũ vào common/schemas.py.  
2. **Implement Async Persistence:** Thiết lập AsyncSqliteSaver trong common/database.py để lưu trữ checkpoint của Graph vào file hitl\_audit.db.  
3. **Build Core Graph Logic:**  
   * Triển khai node\_analyze: LLM trả về điểm confidence.  
   * Triển khai Conditional Edges:  
     * Confidence \> 0.72 \-\> node\_auto\_approve.  
     * 0.58 \<= Confidence \<= 0.72 \-\> node\_human\_review (có interrupt).  
     * Confidence \< 0.58 \-\> node\_escalate (có interrupt).  
4. **Audit Integration:** Tích hợp helper để mỗi khi node chạy xong, một AuditEntry sẽ được ghi vào SQLite (tập trung vào faithfulness và answer\_relevance).  
5. **System Cleanup:** Thực hiện dọn dẹp triệt để môi trường:  
   * Xóa toàn bộ \_\_pycache\_\_/, .pyc, .pyo.  
   * Xóa các file tạm .tmp, .bak hoặc các folder dumped không cần thiết từ các lần chạy Exercise cũ.  
   * Đảm bảo .gitignore bao gồm các file cache này.

## ---

**3\. SPECIFICATIONS & RULES**

* **Vibe Code Rules:** Code phải 100% Type-hinted. Sử dụng pydantic cho mọi cấu trúc dữ liệu input/output.  
* **Routing Thresholds:** Sử dụng biến constants từ common/schemas.py. Tuyệt đối không hardcode số trong graph.  
* **Scope Guard:** Chỉ tập trung vào Logic Graph. KHÔNG làm UI Streamlit trong TIP này. Nếu phát hiện logic out-of-scope, phải báo cáo Chủ thầu ngay.  
* **Side-effect Rule:** Node commit\_review phải là node cuối cùng và tách biệt hoàn toàn để tránh duplicate comment khi resume.

## ---

**4\. ACCEPTANCE CRITERIA (Gherkin)**

`Scenario: Graph correctly pauses for human review`  
    `Given a PR with 65% confidence`  
    `When the graph is invoked with a thread_id`  
    `Then the graph should reach 'node_human_review'`  
    `And the graph should trigger an interrupt()`  
    `And the state should be saved to hitl_audit.db`

`Scenario: System environment is clean`  
    `Given the build process is complete`  
    `When I check the directory tree`  
    `Then no __pycache__ or temporary files should exist`

## ---

**5\. REPORT FORMAT**

Thợ thi công báo cáo theo mẫu **Completion Report**:

* STATUS: DONE / BLOCKED  
* FILES CHANGED: \[list\]  
* CLEANUP LOG: \[X folders/files deleted\]  
* TEST RESULTS: \[AC pass/fail\]  
* SUGGESTIONS FOR CONTRACTOR: \[nếu có\]