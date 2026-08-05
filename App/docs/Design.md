# Shop Ads 圖片產生工具－設計

## 1. 架構

系統分成供應商中立的 AI 規劃層與可重現的 Python 合成核心：

```text
CLI
├─ 設定載入
├─ 輸入驗證
├─ Product Description 解析
├─ AI 分析副本
├─ AI Provider（OpenAI / Google）
├─ AI Plan 驗證與預覽
├─ 圖片合成
├─ Manifest / Log
├─ Final 檢查
└─ 跨電腦封裝

未來獨立階段
├─ Codex Skill 視覺檢查與調整
├─ Facebook 發布
└─ 靜態網站 / GitHub 發布
```

AI 只分析使用者提供的圖片並產生結構化文字計畫，不呼叫圖片生成服務。商品外觀不得由 AI 重畫、補圖、換背景或修改。

## 1.1 AI Provider 契約

Provider 接收商品欄位、移除 metadata 且限制解析度的靜態圖分析副本、可用版型與固定文案政策，回傳相同的 JSON Schema。API 差異、驗證、重試與 usage 解析封裝在 Adapter 內；合成器不得依賴供應商。

API key 由未追蹤的 `App\config.local.toml` 讀取。該檔不得寫入 Log、Manifest、EXE 或 ZIP；共用 `config.toml` 只保存 provider、model 與限制。

## 2. 技術

- Python 3.13
- Pillow：圖片讀取、EXIF 修正、縮放、旋轉、陰影、文字與輸出
- `argparse`：命令列介面
- `tomllib`：讀取 TOML，不增加 YAML 相依性
- `zipfile`、`hashlib`：封裝與完整性驗證
- PyInstaller：Windows EXE
- `unittest`：自動測試

## 3. 模組

```text
shopads/
├─ cli.py          命令列與結束碼
├─ config.py       TOML 載入、合併、設定驗證
├─ errors.py       結構化錯誤
├─ markdown.py     固定 Markdown 欄位解析
├─ validation.py   作業、圖片與 GIF 影格分類
├─ ai_plan.py      AI Plan 契約、驗證、快取與預覽
├─ ai_provider.py  Provider Adapter 與安全 API 呼叫
├─ compositor.py   clean 版型與文字排版
├─ manifest.py     SHA-256 與執行紀錄
└─ package_ops.py  Final 檢查與 ZIP 封裝
```

## 4. 設定合併

依序套用：

1. 程式內安全預設值
2. `App\config.toml`
3. 日期目錄的 `job.toml`

`job.toml` 只允許覆寫圖片與版型參數，不允許改變憑證來源或任意輸出路徑。

## 4.1 快速建立作業

`new-job` 讀取 `paths.work_root`，以本機時區日期產生 `yyyyMMdd`，依序檢查 `01`～`10`。程式先在作業根目錄建立唯一暫存目錄，放入 `Product_Description.md`、`Input`、`Result\Generated`、`Result\Final`，確認目標仍不存在後以同磁碟 rename 原子完成。`NewJob.cmd` 預設開啟描述檔與 Input；CLI 的 `--no-open` 供自動化使用。

## 5. 圖片版面

1080×1080 clean 版型分成：

- 上方標題安全區
- 中央商品卡片區
- 下方說明與下標題安全區

來源圖以 `contain` 模式完整放入卡片。AI 只可從 `hero`、`two_cards` 中選擇，每張最多兩個來源；最後商品資訊摘要使用 `vendor_text`。卡片使用白底、圓角、邊框與陰影，背景使用低彩度漸層與半透明裝飾圓形。旋轉角度由作業、成品序號及檔名計算固定 seed，確保重跑一致。

所有 PNG 在其他內容完成後，統一由合成器將 `assets\branding\shop-footer.png` 等比例縮放至設定寬度並貼至左下角。其右側顯示 `assets\branding\store-banner.md` 的 Markdown 清單項目；選擇索引以作業名稱、成品序號與固定字串計算 SHA-256 seed，因此具隨機感但可重現。品牌資產與特色檔由 `config.toml` 指定相對 App 路徑，啟動時驗證，不交給 AI 修改。多影格 GIF 保持 passthrough，不套品牌圖；單影格 GIF 進入靜態合成流程。

`vendor_text` 不引用來源圖片，作為獨立的商品資訊摘要卡。AI 將商品描述、廠商文字與圖片 OCR 可辨識資訊合併、去重、翻譯並濃縮為繁體中文重點。廠商文字存在時必須產生；否則由 `ai.summary_min_facts` 控制最低資訊量，達標才產生。該輸出最多一張，且必須位於所有靜態圖與 GIF 計畫之後。

文字依像素寬度換行並逐級縮小字體。到達最小字級仍超出指定區域時丟出排版錯誤，不截斷文字。

## 6. 狀態與錯誤

錯誤格式：

```text
[E203][PROCESS_IMAGES] 01/001.jpg 無法讀取：檔案可能損壞。
```

階段：

- `VALIDATE_INPUT`
- `READ_DESCRIPTION`
- `PROCESS_IMAGES`
- `WRITE_OUTPUT`
- `VERIFY_OUTPUT`
- `PACKAGE`

群組錯誤收集後繼續下一群組。命令結束時若存在任何錯誤，回傳結束碼 1；環境或設定錯誤回傳 2。

## 7. 安全覆蓋

只允許刪除：

```text
<job>\Result\Generated\<兩位數>.png
<job>\Result\Generated\<兩位數>.gif
```

刪除前解析絕對路徑，確認父目錄正是目前作業的 `Result\Generated`。程式不提供遞迴刪除。

成品先在同磁碟暫存目錄完成並驗證，再以 `os.replace` 移入 Generated。Windows 搬移可能保留暫存檔的受保護 ACL，因此清理既有成品前及每個新目的檔完成後，皆以 `icacls /inheritance:e` 恢復父目錄權限繼承；失敗時回報 `E304`，不得留下表面成功但使用者無法開啟的成品。

## 8. 封裝

`check-final` 以最近的成功生成 Manifest 為基準，要求 Final 具有相同檔名。PNG 必須可讀且為 1080×1080；GIF 必須可讀。

`package` 建立暫存清單，計算雜湊，再直接寫入 ZIP。ZIP 內容使用相對路徑，不包含本機絕對路徑及設定檔。

## 9. AI 作業流程

`analyze` 驗證 `yyyyMMdd-NN\Input`，先依自然檔名排序並計算 SHA-256；完全相同的內容只保留第一份參與後續流程，其餘不刪除原檔並記入 rejected。接著以 Pillow 的影格數將 GIF 分為單影格與動畫。單影格 GIF 產生一般分析副本；動畫 GIF 擷取首、中、末影格並組成一張預覽，不上傳完整動畫。Provider 同時彙整描述檔、廠商文字與圖片中清楚可辨識的文字；有廠商文字時固定建立摘要，否則去重後至少達 `summary_min_facts` 才建立。Provider 回傳後由本機依順序與 type 正規化輸出名稱為 `NN.png`／`NN.gif`，再驗證所有有效動畫 GIF 恰好出現一次、摘要頁最多一張且固定最後，原子寫入 `Work\ai-plan.json` 與 `preview.html`。`generate` 只接受通過 Schema 驗證的計畫；動畫 GIF 不重新編碼。Provider 對 429 與常見 5xx 暫時錯誤採最多三次指數退避重試。

## 10. 發布擴充點

後續發布模組只能讀取已驗證的封裝或 Final，不直接依賴生成流程。Facebook 與 GitHub 各自保存獨立狀態，使單邊重試不會造成另一邊重複發布。

## 11. Repository 與 Workspace 邊界

```text
D:\CASE\
├─ SmartCabiNet\                  ryan0228/SmartCabiNet
│  ├─ SmartCabiNet.sln
│  ├─ SpecDocs\WebSite\          公開網站的唯一本機來源
│  └─ PublishSecretTimeWebsite.*  獨立發布至 GitHub Pages repository
└─ Shop_ADs\                     ryan0228/Store_ADs
   ├─ App\
   └─ yyyyMMdd-NN\
```

- `Shop_ADs` 與 `SmartCabiNet` 必須維持同層的兩個獨立 Git repositories，不可建立巢狀 repository。
- `Shop_ADs` 不加入 `SmartCabiNet.sln`；它是獨立 Python 工具，Visual Studio 方案維持既有 .NET 專案邊界。
- Codex 進行 Shop Ads 核心開發時，以 `D:\CASE\Shop_ADs` 開新 workspace；進行網站修改或驗證時，以 `D:\CASE\SmartCabiNet` workspace 執行。
- Phase 2 透過設定檔指定 `D:\CASE\SmartCabiNet\SpecDocs\WebSite`，只允許寫入核准的網站相對路徑。
- 網站修改後先預覽與 Dry Run；只有使用者明確要求發布時，才呼叫既有 `PublishSecretTimeWebsite.ps1`。
