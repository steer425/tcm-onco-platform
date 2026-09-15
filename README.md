# 每日重點新聞收集：執行紀錄

這個分支由 `.github/workflows/daily-news.yml` 自動寫入，**不要手動編輯**，
也不要合併回 `main`（它是孤立分支，與 main 沒有共同歷史）。

存在的理由：每天清晨的 Cowork 排程工作跑在雲端沙箱裡，那個沙箱連不到
後端（onrender.com 被擋）也用不了 GitHub Actions API，唯一做得到的是
`git clone` 這個 repo。把每次執行結果寫進這裡之後，它就能讀到事實，
不必再用猜的。

查看方式：

```bash
git clone --depth 1 --branch news-run-log <repo> log && tail -20 log/runs/$(date +%Y-%m).md
```
