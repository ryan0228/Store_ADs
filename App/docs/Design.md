# Shop Ads 圖片產生工具－設計

## 1. 架構

系統分成可重現的 Python 核心與未來的 AI Skill／發布層：

```text
CLI
├─ 設定載入
├─ 輸入驗證
├─ Markdown 解析
├─ 圖片合成
├─ Manifest / Log
├─ Final 檢查
└─ 跨電腦封裝

未來獨立階段
├─ Codex Skill 視覺檢查與調整
├─ Facebook 發布
└─ 靜態網站 / GitHub 發布
```

第一階段不呼叫生成式圖片服務，以保護商品外觀與文字。AI 未來只協助檢視、產生背景或調整工作流程。

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
├─ validation.py   作業與群組檢查
├─ compositor.py   clean 版型與文字排版
├─ manifest.py     SHA-256 與執行紀錄
└─ package.py      Final 檢查與 ZIP 封裝
```

## 4. 設定合併

依序套用：

1. 程式內安全預設值
2. `App\config.toml`
3. 日期目錄的 `job.toml`

`job.toml` 只允許覆寫圖片與版型參數，不允許改變憑證來源或任意輸出路徑。

## 5. 圖片版面

1080×1080 clean 版型分成：

- 上方標題安全區
- 中央商品卡片區
- 下方說明與下標題安全區

來源圖以 `contain` 模式完整放入卡片。卡片使用白底、圓角、邊框與陰影；旋轉角度由群組名稱、頁碼及檔名計算固定 seed，確保重跑一致。

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
<job>\Result\Generated\<group>.png
<job>\Result\Generated\<group>-<number>.png
<job>\Result\Generated\<group>.gif
```

刪除前解析絕對路徑，確認父目錄正是目前作業的 `Result\Generated`。程式不提供遞迴刪除。

## 8. 封裝

`check-final` 以最近的成功生成 Manifest 為基準，要求 Final 具有相同檔名。PNG 必須可讀且為 1080×1080；GIF 必須可讀。

`package` 建立暫存清單，計算雜湊，再直接寫入 ZIP。ZIP 內容使用相對路徑，不包含本機絕對路徑及設定檔。

## 9. 發布擴充點

後續發布模組只能讀取已驗證的封裝或 Final，不直接依賴生成流程。Facebook 與 GitHub 各自保存獨立狀態，使單邊重試不會造成另一邊重複發布。

## 10. Repository 與 Workspace 邊界

```text
D:\CASE\
├─ SmartCabiNet\                  ryan0228/SmartCabiNet
│  ├─ SmartCabiNet.sln
│  ├─ SpecDocs\WebSite\          公開網站的唯一本機來源
│  └─ PublishSecretTimeWebsite.*  獨立發布至 GitHub Pages repository
└─ Shop_ADs\                     ryan0228/Store_ADs
   ├─ App\
   └─ yyyyMMdd\
```

- `Shop_ADs` 與 `SmartCabiNet` 必須維持同層的兩個獨立 Git repositories，不可建立巢狀 repository。
- `Shop_ADs` 不加入 `SmartCabiNet.sln`；它是獨立 Python 工具，Visual Studio 方案維持既有 .NET 專案邊界。
- Codex 進行 Shop Ads 核心開發時，以 `D:\CASE\Shop_ADs` 開新 workspace；進行網站修改或驗證時，以 `D:\CASE\SmartCabiNet` workspace 執行。
- Phase 2 透過設定檔指定 `D:\CASE\SmartCabiNet\SpecDocs\WebSite`，只允許寫入核准的網站相對路徑。
- 網站修改後先預覽與 Dry Run；只有使用者明確要求發布時，才呼叫既有 `PublishSecretTimeWebsite.ps1`。
