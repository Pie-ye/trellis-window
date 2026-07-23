# Trellis Window

本機 Web 工作台：**選擇資料夾 → 掃描底下所有 Trellis 專案** → **只讀**瀏覽 tasks / PRD / Design / Implement、產物就緒燈與進度條。

## 快速開始

### Linux / macOS / WSL / Git Bash

```bash
cd trellis-window
./start.sh
# 本機：  http://127.0.0.1:8775
# 區網：  http://192.168.68.69:8775   （依主機實際 IP）
```

### Windows（PowerShell）

`start.sh` 是 bash 腳本，**在 PowerShell 裡無效**（常會立刻結束、沒有任何輸出）。請改用：

```powershell
cd trellis-window
.\start.ps1
# 本機：  http://127.0.0.1:8775
```

`start.ps1` 會在 **缺少 uvicorn 時自動 `pip install -r requirements.txt`**（即使 `.venv` 已存在）。

若仍報 `No module named uvicorn`，刪除壞掉的 venv 後重跑：

```powershell
Remove-Item -Recurse -Force .venv
.\start.ps1
```

若出現「無法載入，因為這個系統上已停用指令碼執行」，先執行一次：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

或不用腳本、手動啟動：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 0.0.0.0 --port 8775
```

1. 點 **選擇資料夾…** 在伺服器檔案系統中瀏覽  
2. 選一個工作區根目錄（例如 monorepo）→ **掃描此資料夾**  
3. 左側列出所有含 `.trellis/` 的專案；點專案看 tasks 與進度；點 task 看 PRD 等

預設綁定 `0.0.0.0:8775`，區網其他裝置可連線。可用環境變數覆寫：

```bash
# Linux / macOS
TRELLIS_WINDOW_HOST=0.0.0.0 TRELLIS_WINDOW_PORT=8775 ./start.sh
# 若只要本機： TRELLIS_WINDOW_HOST=127.0.0.1 ./start.sh
```

```powershell
# Windows PowerShell
$env:TRELLIS_WINDOW_HOST="127.0.0.1"; $env:TRELLIS_WINDOW_PORT="8775"; .\start.ps1
```

若系統無 `python3-venv`，可用 [uv](https://github.com/astral-sh/uv)：`uv venv .venv && uv pip install -r requirements.txt --python .venv/bin/python`（`start.sh` 會自動嘗試）。

手動（Unix）：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server.app:app --host 0.0.0.0 --port 8775
```

測試：

```bash
source .venv/bin/activate
pytest -q
```

## 行為邊界

| 可做 | 不可做（MVP） |
|------|----------------|
| 加入 / 移除專案路徑（app 設定） | 修改被檢視專案的 `.trellis` |
| 列出 active tasks、讀 md / spec | 呼叫 `task.py` 改 status |
| 產物就緒燈（檔案是否存在） | 規範增刪建議引擎 |

## 設定檔

已加入專案清單：

- 預設：`~/.config/trellis-window/projects.json`
- 覆寫目錄：環境變數 `TRELLIS_WINDOW_CONFIG_DIR`

## API 摘要

- `GET /api/health`
- `GET /api/browse?path=` — 資料夾瀏覽器
- `POST /api/scan` — 掃描路徑下所有 Trellis 專案並寫入清單
- `GET /api/projects` — 專案 + scanRoots
- `GET|POST /api/projects` / `DELETE /api/projects/{id}`（POST 仍可手動加單一專案）
- `GET /api/projects/{id}/tasks`（含 `progress` + 每 task 的 `review` 摘要）
- `GET /api/projects/{id}/tasks/{dirName}`
- `GET /api/projects/{id}/tasks/{dirName}/review` — 結案 Review（規則引擎）
- `GET /api/projects/{id}/specs/tree`
- `GET /api/projects/{id}/specs/file?path=`

## 結案 Review（v1.1）

依 **prd/implement checkbox、產物檔、status** 計算完成傾向（`rulesVersion: review-1`），並建議下一步與可複製的 `task.py archive` 指令。

- **不**自動 archive、**不**寫入被檢視專案
- 無 checkbox 會標「AC 未維護」，不會當成 0% 失敗
- 最終仍以你對 Goal 的手測為準

## 部署模型（建議）

**每台開發機各自部署一份**，直接讀該機上的程式碼與 `.trellis`。  
各機 repo / 任務進度不同，不適合做成「一台中心站 + 上傳整包資料夾」當主流程。

| 情境 | 做法 |
|------|------|
| 本機寫 code | `./start.sh` → 開 `http://127.0.0.1:8775` |
| 同區網另一台裝置看這台 | `http://<這台IP>:8775`（防火牆放行 8775） |
| 人在外網，要看家裡/公司這台 | 用 Tailscale / VPN / SSH 隧道連回該機 Viewer，**不要**把服務裸掛公網 |
| 給別人看快照 | 可另議 zip 僅 `.trellis`；非預設能力 |

## 網路注意

- 預設監聽所有介面（`0.0.0.0`），方便區網；本機-only 可設 `TRELLIS_WINDOW_HOST=127.0.0.1`。
- 此服務會讀取本機已掃描專案的檔案內容，**請勿直接暴露到公網**。
- 若連不上，檢查主機防火牆是否放行 TCP `8775`。
