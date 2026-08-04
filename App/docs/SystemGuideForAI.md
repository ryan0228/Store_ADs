# Shop Ads 系統導覽（AI／Codex 閱讀入口）

> 本文件是後續 AI 接手 `D:\CASE\Shop_ADs` 時的第一閱讀入口。最後更新基準為 ShopAds `0.2.7`。正式需求、設計與工作狀態仍分別以 `Requirement.md`、`Design.md`、`TaskList.md` 為準；若程式、測試與文件不一致，先查明差異並更新契約，不可猜測。

## 1. 接手規則

1. 工作區固定為 `D:\CASE\Shop_ADs`；GitHub repository 是 public 的 `ryan0228/Store_ADs`。
2. 非簡單變更依序執行：Requirement → Design → Task List → implementation → tests → EXE build → UAT。
3. 所有說明、UI、Log 與程式註解使用繁體中文。
4. 不得讀出、顯示、記錄或提交 `App\config.local.toml` 的 API key。
5. 日期商品作業、來源圖片、AI 中間資料、Generated、Final、Log、ZIP 與 EXE 都不得提交 public repository。
6. 不得把本工具加入 `SmartCabiNet.sln`，也不得建立巢狀 Git repository。
7. Facebook、網站與 GitHub 發布尚未實作；未經使用者明確要求不得擴大到發布作業。

## 2. 系統目的與邊界

Shop Ads 是 Windows Python／Pillow 獨立工具。使用者只需提供商品名稱、商品說明與原始圖片；AI 負責理解圖片、分組、排序及產生繁體中文短文案，本機合成器再建立 1080×1080 PNG。

AI 只做「分析與規劃」，不生成、重畫、換背景或改造商品圖片。最終像素輸出必須由可重現的 Pillow 合成器完成。

```text
使用者輸入
  ├─ Product_Description.md
  └─ Input 原始圖片／GIF
          ↓
輸入驗證與圖片分類
          ↓
OpenAI 或 Google Provider
          ↓
Work\ai-plan.json + preview.html
          ↓ 人工確認
Pillow 確定性合成器
          ↓
Result\Generated
          ↓ 人工目視確認／必要加工
Result\Final
          ↓
Final 檢查、ZIP 與 SHA-256 封裝
```

## 3. Repository 結構

```text
D:\CASE\Shop_ADs\
├─ .gitignore
├─ App\
│  ├─ ShopAds.exe                 本機建置成品，Git 忽略
│  ├─ config.toml                 可提交的一般設定
│  ├─ config.local.toml           本機 API key，Git 忽略
│  ├─ config.local.example.toml   無真實 key 的範例
│  ├─ NewJob.cmd
│  ├─ ValidateLatest.cmd
│  ├─ AnalyzeLatest.cmd
│  ├─ GenerateLatest.cmd
│  ├─ PackageLatest.cmd
│  ├─ assets\branding\shop-footer.png
│  ├─ templates\Product_Description.md
│  ├─ docs\
│  ├─ shopads\
│  └─ tests\
└─ yyyyMMdd-NN\                  私有商品作業，Git 忽略
```

`yyyyMMdd-NN` 一天最多 10 個商品，編號固定 `01`～`10`。例如 `20260804-02` 表示 2026-08-04 的第二個商品。

## 4. 商品作業契約

```text
20260804-01\
├─ Product_Description.md
├─ Input\
│  ├─ front.jpg
│  ├─ detail.png
│  ├─ still.gif
│  └─ animation.gif
├─ Work\
│  ├─ ai-plan.json
│  └─ preview.html
├─ Result\
│  ├─ Generated\
│  └─ Final\
├─ Logs\
├─ PublishPackages\
└─ run-manifest.json
```

### Product_Description.md

- `商品名稱`：必填。
- `商品說明`：必填；可貼官方確認資訊。
- `商品用途`：選填；留白時由 AI 根據名稱、說明與圖片推導中性情境。
- `參考資訊`：選填。
- `文案限制`：選填，優先級高於 AI 文案偏好。
- `廠商文字說明`：選填；AI 同時彙整商品描述與圖片文字。廠商文字存在時固定產生最後摘要頁；否則資訊量達 `summary_min_facts` 才產生。

## 5. 日常作業方式

### 雙擊操作

1. `NewJob.cmd`：建立今天下一個商品作業，開啟描述檔與 Input。
2. 填寫商品資料並將所有來源圖放入 Input。
3. `ValidateLatest.cmd`：驗證最新作業。
4. `AnalyzeLatest.cmd`：呼叫 AI，建立 Plan 與 HTML 預覽。
5. 開啟 `Work\preview.html`，人工確認分組、順序、文案、排除原因與最後商品資訊摘要。
6. `GenerateLatest.cmd`：依已驗證 Plan 產生 Generated。
7. 人工目視確認；將核准或加工後成品放入 Final。
8. `PackageLatest.cmd`：只從完整 Final 建立 ZIP。

### CLI

```powershell
ShopAds.exe new-job
ShopAds.exe new-job --date 2026-08-04 --no-open
ShopAds.exe validate D:\CASE\Shop_ADs\20260804-01
ShopAds.exe analyze D:\CASE\Shop_ADs\20260804-01
ShopAds.exe generate D:\CASE\Shop_ADs\20260804-01
ShopAds.exe check-final D:\CASE\Shop_ADs\20260804-01
ShopAds.exe package D:\CASE\Shop_ADs\20260804-01
ShopAds.exe verify-package D:\path\PublishPackage-....zip
```

省略 job 路徑時，工具依 `yyyyMMdd-NN` 字典排序選擇最新作業。

## 6. AI 分析流程

設定載入順序：程式安全預設 → `App\config.toml` → `App\config.local.toml` → 作業 `job.toml` 的允許視覺覆寫。

```toml
[ai]
provider = "google"
model = "gemini-3.6-flash"
analysis_max_dimension = 768
max_input_images = 15
gif_frame_analysis = true
summary_min_facts = 3
```

Provider Adapter 位於 `ai_provider.py`。OpenAI 與 Google 必須回傳同一套 AI Plan；API 差異不得滲入合成器。

送往 AI 的不是原始大圖：

- 靜態圖修正 EXIF、轉 RGB、限制最長邊並移除 metadata。
- 單影格 GIF 視為靜態圖。
- 多影格 GIF 在本機擷取首／中／末影格，組成最高 768×256 JPEG 預覽。
- 不上傳完整動畫 GIF。
- API 回傳 usage 可寫入 Plan，但不得包含 API key 或 Authorization header。

AI 文案限制：使用繁體中文；不得杜撰尺寸、材質、價格、產地、功效或保證性宣稱；可排除模糊、重複或低資訊的靜態圖，但必須寫明原因；多影格 GIF 不可排除。

圖片文字與描述檔是同等候選來源，但只接受清楚可辨識且彼此可核對的資訊。摘要前先去重；有廠商文字時固定產生，沒有時至少達 `summary_min_facts` 項才產生。此門檻由 AI 依具體事實項目判斷，本機再驗證摘要最多一張且固定最後。

## 7. AI Plan 契約

Plan 位於 `Work\ai-plan.json`，由 `ai_plan.py` 驗證。Provider 回傳後，本機依展示順序與 type 強制正規化為 `01.png`、`02.gif`、`03.png`，不信任模型自行填寫的 output 檔名。

受控版型：

| type | layout | 圖片數 | 說明 |
|---|---|---:|---|
| `static` | `hero` | 1 | 單張主視覺 |
| `static` | `two_cards` | 2 | 兩張圖片 |
| `static` | `three_cards` | 3 | 三張圖片 |
| `static` | `four_grid` | 4 | 四張網格 |
| `gif` | `original_gif` | 1 | 多影格 GIF 原樣複製 |
| `text` | `vendor_text` | 0 | 商品資訊摘要頁，最多一張且必須最後 |

關鍵驗證：

- type、layout、圖片數量必須一致。
- 引用檔名必須存在於 Input。
- 動畫 GIF 必須恰好出現一次，不能遺漏、重複或放入 static。
- 單影格 GIF 可放入 static，最後輸出 PNG。
- 廠商文字存在時必須恰好產生一張 `vendor_text`；不存在時僅在商品描述與圖片文字去重後資訊量達門檻才產生。
- static／text 必須包含 `top_title`、`description`、`bottom_title`。

## 8. 圖片合成與品牌

`compositor.py` 只接受通過驗證的 Plan：

- PNG 固定 1080×1080、sRGB、完整顯示商品主體，不裁切。
- clean 版型包含白色卡片、圓角、邊框、陰影及固定 seed 小角度旋轉。
- 文字依像素寬度換行並逐級縮小；最小字級仍放不下時報錯，不截斷。
- 所有 PNG 右下角貼 `assets\branding\shop-footer.png`，圖內已包含「情趣時光」，不另外重複畫店名。
- 多影格 GIF 為 passthrough：不重新編碼、不加文字、不加品牌，SHA／位元組必須與原檔一致。
- `vendor_text` 將描述檔、廠商文字與圖片文字去重整理後放在獨立摘要卡，且同樣加入品牌頁尾。

## 9. 輸出、安全覆蓋與封裝

- generate 只寫 `Result\Generated`。
- 重跑只清理 Generated 中符合兩位數連續命名的 PNG／GIF；不得遞迴刪除任意路徑。
- `Result\Final` 永不由 generate 刪除或覆蓋。
- `check-final` 以最近成功的 `run-manifest.json` 為基準，Final 必須具有全部同名成品。
- PNG 必須可讀且為 1080×1080；GIF 必須可讀。
- package 只封裝 Final、根目錄 Markdown 與 `publish-manifest.json`，每個檔案記錄 SHA-256。
- ZIP 不得包含 config、API key、Token、Log、Work、Generated 或本機絕對路徑。

## 10. 模組責任

| 模組 | 責任 |
|---|---|
| `cli.py` | CLI、Log、命令路由、結束碼 |
| `config.py` | TOML 合併、字型／品牌／設定驗證 |
| `job_ops.py` | 安全建立 `yyyyMMdd-NN` 作業與開啟檔案 |
| `markdown.py` | UTF-8 Markdown 區段解析 |
| `validation.py` | 作業名稱、Input、圖片與 GIF 影格分類 |
| `ai_provider.py` | 分析副本、提示詞、OpenAI／Google HTTP Adapter |
| `ai_plan.py` | Plan 驗證、原子儲存與 HTML 預覽 |
| `compositor.py` | clean／vendor_text 合成、品牌與輸出驗證 |
| `manifest.py` | SHA-256、時間戳、JSON 原子寫入 |
| `package_ops.py` | Final 檢查、ZIP 建立與驗證 |
| `errors.py` | 結構化錯誤碼 |

## 11. 錯誤、Log 與結束碼

錯誤格式：`[代碼][階段] 訊息／路徑／建議`。主要階段包括 `LOAD_CONFIG`、`CREATE_JOB`、`VALIDATE_INPUT`、`READ_DESCRIPTION`、`AI_ANALYZE`、`AI_PLAN`、`PROCESS_IMAGES`、`WRITE_OUTPUT`、`VERIFY_OUTPUT`、`PACKAGE`。

- 成功：0。
- 作業或部分處理錯誤：1。
- 設定、環境或頂層 ShopAdsError：2。
- 使用者中止：130。

Log 不得輸出 API key、Authorization header、密碼或完整 Provider 機密回應。

## 12. 測試與建置

開發環境：Python 3.13、Pillow、unittest、PyInstaller。

```powershell
cd D:\CASE\Shop_ADs\App
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\Build.ps1
.\ShopAds.exe --version
```

截至 0.2.7 有 15 項測試通過，涵蓋全格式精確去重、靜態與動畫重複輸入分類、文案來源約束，以及沒有廠商文字時依圖片文字產生最後摘要頁。

`ShopAds.exe`、`.venv`、build、dist 與 spec 均為本機產物，Git 忽略。

## 13. 目前狀態與已知缺口

- 目前版本：0.2.7。
- 真實 UAT 作業：`20260804-01` 驗證全格式精確去重；`20260804-02` 驗證圖片文字彙整與最後摘要頁。
- 目前 Provider 為 Google `gemini-3.6-flash`；兩次真實 analyze 與 generate 均成功，PNG 品牌與版面通過目視 QA，GIF 輸出 SHA-256 均與來源一致。
- 全格式精確去重已完成：自然排序後保留相同 SHA-256 的第一份，其餘不送 AI、不刪除 Input，並寫入 Log 與 rejected。真實 UAT 將兩份相同動畫 GIF 縮減為一份有效來源，Generated 由四個成品降為三個。
- Google 暫時性 429／5xx 最多退避重試三次；真實 UAT 曾遇 503 high demand，後續重跑成功。
- 20260804-02 UAT 已驗證圖片文字摘要：7 張靜態圖與 4 個動畫 GIF 產生 3 張圖片頁、4 個原樣 GIF，以及最後一張商品資訊總覽；摘要涵蓋功能、材質防水、充電、尺寸與配件，排版未截斷。
- 尚未完成輸入 SHA 快取、精確成本報表與 Final／package 真實商品 UAT。
- Facebook、GitHub、網站發布與 Credential Manager 不在目前已實作範圍。

## 14. 後續 AI 工作檢查表

開始前：

- 確認 cwd 是 `D:\CASE\Shop_ADs`。
- 讀本文件、Requirement、Design、TaskList 與使用說明。
- 執行 `git status --short`，保留使用者既有變更。
- 不顯示 `config.local.toml`。

修改後：

- 更新 Requirement、Design、Task List 與本文件中受影響內容。
- 執行 `git diff --check`。
- 跑完整 unittest。
- 依風險建立 EXE，確認 `ShopAds.exe --version`。
- 以代表性圖片目視 QA；動畫 GIF 比較輸入／輸出 SHA-256。
- 未取得使用者明確授權前，不 commit、push、發布 Facebook 或修改 SmartCabiNet 網站。
