# Shop Ads 圖片產生工具－需求規格

## 1. 目標

建立一套可在 Windows 獨立執行的圖片產生工具，從 `D:\CASE\Shop_ADs\yyyyMMdd` 作業目錄讀取商品圖片與 Markdown 說明，產生適合社群平台的 1080×1080 圖片。

第一階段只負責輸入檢查、圖片生成、人工成品檢查與跨電腦封裝；Facebook 與 GitHub 發布屬於後續獨立階段。

## 2. 作業目錄

```text
D:\CASE\Shop_ADs\20260803\
├─ Prod_Description.md
├─ 01\
│  ├─ 001.jpg
│  ├─ 002.png
│  └─ Img_Description.md
├─ 02\
│  └─ product.gif
└─ Result\
   ├─ Generated\
   └─ Final\
```

只處理名稱完全由數字組成的子目錄。`Result`、`Logs`、`PublishPackages` 與其他目錄不得被當成圖片群組。

## 3. 文字資料

### 3.1 Prod_Description.md

必須包含以下 Markdown 標題：

- `商品名稱`
- `使用情境`
- `商品說明`

這些內容提供整批商品資訊、後續 Skill 與發布文案使用。第一階段不強制將商品名稱畫在每張圖片上。

### 3.2 Img_Description.md

靜態圖片群組必須包含此檔案，且包含：

- `上標題`
- `說明`
- `下標題`

三項文字都會顯示在合成圖片。只有單一 GIF 的群組不讀取此檔案。

## 4. 圖片處理

- 支援 `.jpg`、`.jpeg`、`.png`、`.webp`、`.gif`。
- 靜態圖片依自然檔名排序，例如 `2.jpg` 排在 `10.jpg` 前。
- 每張成品最多放三張來源圖。
- 一至三張來源圖輸出 `01.png`。
- 超過三張時每三張分頁，輸出 `01-1.png`、`01-2.png` 等。
- 只有一個 GIF 時直接複製為 `01.gif`，不重新編碼。
- GIF 與其他圖片混用視為輸入錯誤。
- 手機照片須依 EXIF 修正方向。
- 靜態輸出統一轉為 sRGB PNG，尺寸固定為 1080×1080。
- 圖片採完整顯示，不裁掉商品主體。
- 預設使用 `clean` 版型，包含卡片、外框、陰影及小角度旋轉。
- 相同輸入與設定重跑時，輸出排版必須一致。

## 5. 輸出與覆蓋

- 程式生成檔案只寫入 `Result\Generated`。
- 重新生成群組前，只清理該群組在 Generated 中的舊輸出與舊分頁。
- 不得刪除或覆蓋 `Result\Final`。
- 人工確認或加工完成的圖片由使用者放入 `Result\Final`。
- 發布封裝預設只接受 Final，不得無提示地改用 Generated。

## 6. 設定

- 共用設定使用外部 TOML 檔，可調整尺寸、版型、色彩、邊距、旋轉角度、字型及來源根目錄。
- 日期目錄可用 `job.toml` 覆寫允許的視覺設定。
- 第一階段不保存 Facebook 或 GitHub 憑證。
- 後續憑證必須放在 Windows Credential Manager；一般設定檔只保存憑證名稱。

## 7. 防呆與追蹤

- 提供 `validate`、`generate`、`check-final`、`package`、`verify-package` 五個獨立命令。
- 錯誤訊息必須包含錯誤代碼、執行階段、檔案路徑與處理建議。
- 單一群組失敗不得阻止其他合法群組生成，但整體命令須回傳非零結束碼。
- 每次生成產生 `run-manifest.json` 及時間戳記 Log。
- Manifest 記錄輸入與輸出 SHA-256、程式版本、設定、群組結果及錯誤。
- Log 不得記錄 Token、密碼或其他機密。

## 8. 跨電腦封裝

- `package` 只封裝已通過檢查的 Final 圖片。
- 封裝檔包含商品／圖片 Markdown、Final 圖片及 `publish-manifest.json`。
- Manifest 記錄每個封裝檔案的 SHA-256。
- 封裝檔不得包含本機設定、Token、密碼或私鑰。

## 9. 驗收條件

1. 一至九張測試圖片能依三張一頁正確命名。
2. 單一 GIF 位元組內容不變，只更名複製。
3. 更換來源後重跑會覆蓋 Generated，且清除不再需要的舊分頁。
4. 重跑不改動 Final。
5. 缺少 Markdown、欄位、字型或圖片損壞時能指出明確環節。
6. 過長文字不會被靜默截斷；無法排入時該群組失敗。
7. 封裝前缺少 Final 時拒絕執行。
8. 封裝 Manifest 的 SHA-256 能驗證所有檔案。
