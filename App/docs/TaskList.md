# Shop Ads 圖片產生工具－工作清單

## Phase 1：本次實作

- [x] T01 確認目錄、尺寸、預設版型與分階段邊界
- [x] T02 完成 Requirement
- [x] T03 完成 Design
- [x] T04 建立 Python 專案與預設 TOML
- [x] T05 實作結構化錯誤與 Log
- [x] T06 實作 Markdown 解析與欄位驗證
- [x] T07 實作日期作業與數字群組掃描
- [x] T08 實作自然排序、GIF 規則與圖片檢查
- [x] T09 實作 clean 版型、文字 fitting、外框、陰影與固定旋轉
- [x] T10 實作 Generated 安全覆蓋與舊分頁清理
- [x] T11 實作 run-manifest.json 與 SHA-256
- [x] T12 實作 Final 檢查
- [x] T13 實作 PublishPackage ZIP 與 publish-manifest.json
- [x] T14 建立單元與整合測試
- [x] T15 建立 Windows CMD 與 PyInstaller 打包腳本
- [x] T16 部署至 `D:\CASE\Shop_ADs\App` 並執行驗收
- [x] T17 將 Store_ADs repository 搬移為 SmartCabiNet 的同層 repository 並更新路徑

## Phase 2：後續

- [x] P201 支援 `yyyyMMdd-NN` 單一商品作業與 `Input` 目錄
- [x] P202 將商品資料契約改為 `Product_Description.md`
- [x] P203 定義並驗證供應商中立的 `ai-plan.json`
- [x] P204 建立移除 metadata、限制解析度的 AI 分析副本
- [x] P205 建立 OpenAI 與 Google AI Provider Adapter（Google 真實 UAT 已通過）
- [x] P206 建立 AI 選圖、分組、排序、文案及 GIF 排序規則
- [x] P207 建立本機 HTML 計畫預覽與確認流程
- [x] P208 建立受控版型與連續輸出命名（後續 P227 依 UAT 限縮為一至兩張）
- [ ] P209 加入輸入雜湊快取、token usage 與成本紀錄
- [x] P210 加入 `config.local.toml`、範本與機密防護
- [x] P211 更新 Manifest、Final、封裝與使用說明
- [x] P212 完成新版自動測試、真實圖片 UAT 與 EXE 建置
- [x] P213 所有 PNG 加入「情趣時光」品牌頁尾
- [x] P214 加入廠商文字說明、日文翻譯與最後一張資訊圖契約
- [x] P215 支援多動畫 GIF、單影格 GIF 靜態化與三影格 AI 預覽
- [x] P216 新增 `NewJob.cmd` 與安全的自動流水號作業建立流程
- [x] P217 建立後續 AI／Codex 使用的完整系統導覽文件
- [x] P218 Google responseSchema、錯誤診斷與輸出名稱正規化
- [x] P219 全格式 SHA-256 輸入去重、計畫追蹤與暫時性 API 錯誤重試
- [ ] P220 建立 Codex Skill
- [ ] P221 讓 Skill 檢視 Generated 並依指示重做指定成品
- [ ] P222 加入 AI 背景選配（目前需求明確排除，保留未來評估）
- [x] P225 圖片文字與商品描述去重彙整，依資訊量產生最後摘要頁
- [x] P226 修復 Windows 暫存成品移入 Generated 後未繼承使用者 ACL
- [x] P227 摘要亮點文案、雙圖上限、柔和背景與左側品牌特色列
- [ ] P230 設計 Facebook 授權、預覽、確認、發布與重試
- [ ] P231 設計靜態網站內容映射、Dry Run 與 GitHub 發布驗證
