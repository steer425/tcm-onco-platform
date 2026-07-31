"""
全站功能項目設定（單一資料來源，供 seed.py 初始建立、migrate_schema.py 回填既有資料共用）。

欄位說明：
    code            功能代碼（唯一）
    module          所屬目標（目標零/目標一二/目標五...）
    name            功能全名（用於權限矩陣顯示）
    nav_label       導覽選單顯示文字（較短，None 時前端會退回用 name）
    page_url        對應的獨立 HTML 頁面檔名；None 代表非頁面項目（例如 Dashboard 小工具，僅受 enabled 控制）
    show_frontend   是否顯示於前台導覽選單
    show_backend    是否顯示於後台導覽選單
    sort_order      導覽選單排序（小到大）
"""

FEATURE_CONFIG = [
    # ---- Dashboard 本體 + 4 個可獨立開關的小工具 ----
    {"code": "F0-13", "module": "目標零", "name": "Dashboard",
     "nav_label": "Dashboard", "page_url": "dashboard.html",
     "show_frontend": True, "show_backend": True, "sort_order": 10},
    {"code": "F0-13-1", "module": "目標零", "name": "Dashboard-主機資訊小工具",
     "nav_label": "主機資訊", "page_url": None,
     "show_frontend": True, "show_backend": True, "sort_order": 11},
    {"code": "F0-13-2", "module": "目標零", "name": "Dashboard-版本資訊小工具",
     "nav_label": "版本資訊", "page_url": None,
     "show_frontend": True, "show_backend": True, "sort_order": 12},
    {"code": "F0-13-3", "module": "目標零", "name": "Dashboard-專案文件小工具",
     "nav_label": "專案文件", "page_url": None,
     "show_frontend": True, "show_backend": True, "sort_order": 13},
    {"code": "F0-13-4", "module": "目標零", "name": "Dashboard-2026目標小工具",
     "nav_label": "2026年工作目標", "page_url": None,
     "show_frontend": True, "show_backend": True, "sort_order": 14},
    {"code": "F0-13-5", "module": "目標零", "name": "Dashboard-公告小工具",
     "nav_label": "公告", "page_url": None,
     "show_frontend": True, "show_backend": True, "sort_order": 15},

    # ---- 後台管理頁面 ----
    {"code": "F0-2", "module": "目標零", "name": "角色管理",
     "nav_label": "角色管理", "page_url": "roles.html",
     "show_frontend": False, "show_backend": True, "sort_order": 20},
    {"code": "F0-5", "module": "目標零", "name": "帳號管理",
     "nav_label": "帳號管理", "page_url": "users.html",
     "show_frontend": False, "show_backend": True, "sort_order": 30},
    {"code": "F0-4", "module": "目標零", "name": "帳號審核",
     "nav_label": "帳號審核", "page_url": "applications.html",
     "show_frontend": False, "show_backend": True, "sort_order": 40},
    {"code": "F0-11", "module": "目標零", "name": "稽核與登入紀錄查詢",
     "nav_label": "稽核 / 登入紀錄", "page_url": "logs.html",
     "show_frontend": False, "show_backend": True, "sort_order": 90},
    {"code": "F0-16", "module": "目標零", "name": "系統設定（配色主題）",
     "nav_label": "系統設定", "page_url": "system-settings.html",
     "show_frontend": False, "show_backend": True, "sort_order": 100},
    {"code": "F0-17", "module": "目標零", "name": "公告管理",
     "nav_label": "公告管理", "page_url": "announcements.html",
     "show_frontend": False, "show_backend": True, "sort_order": 46},

    # ---- 目標五：中藥行 ----
    {"code": "F5-1", "module": "目標五", "name": "中藥行資料管理（後台）",
     "nav_label": "中藥行管理", "page_url": "pharmacies.html",
     "show_frontend": False, "show_backend": True, "sort_order": 50},
    {"code": "F5-2", "module": "目標五", "name": "中藥行地理推薦（前台）",
     "nav_label": "中藥行地理推薦", "page_url": "finder.html",
     "show_frontend": True, "show_backend": False, "sort_order": 60},
    {"code": "F5-3", "module": "目標五", "name": "評價管理（後台）",
     # 功能已內建在「中藥行管理」（F5-1）頁面裡，這裡只標記對應頁面路徑，
     # 前台/後台皆不顯示，避免導覽選單出現兩個一模一樣的連結。
     "nav_label": "評價管理", "page_url": "pharmacies.html",
     "show_frontend": False, "show_backend": False, "sort_order": 0},

    # ---- 目標一/二：TCMSP ----
    {"code": "F1-1", "module": "目標一/二", "name": "TCMSP 藥材關聯查詢站",
     "nav_label": "TCMSP 藥材關聯查詢站", "page_url": "tcmsp_query.html",
     "show_frontend": True, "show_backend": False, "sort_order": 70},

    # ---- 其餘目標零基礎建設項目：現在都有對應頁面可查看/設定 ----
    {"code": "F0-1", "module": "目標零", "name": "前後台架構規劃",
     "nav_label": "系統架構規劃", "page_url": "architecture.html",
     "show_frontend": False, "show_backend": True, "sort_order": 95},
    {"code": "F0-3", "module": "目標零", "name": "後台登入權限控管",
     # 與 F0-1 共用同一份架構說明頁，這裡不重複顯示於導覽選單（避免出現兩個一樣的連結）
     "nav_label": "後台登入權限控管", "page_url": "architecture.html",
     "show_frontend": False, "show_backend": False, "sort_order": 0},
    {"code": "F0-9", "module": "目標零", "name": "全站CRUD後台管理",
     "nav_label": "全站CRUD後台管理", "page_url": "architecture.html",
     "show_frontend": False, "show_backend": False, "sort_order": 0},
    {"code": "F0-6", "module": "目標零", "name": "第三方登入整合",
     "nav_label": "第三方登入狀態", "page_url": "oauth-status.html",
     "show_frontend": False, "show_backend": True, "sort_order": 96},
    {"code": "F0-7", "module": "目標零", "name": "資安規劃",
     "nav_label": "資安規劃", "page_url": "security.html",
     "show_frontend": False, "show_backend": True, "sort_order": 97},
    {"code": "F0-8", "module": "目標零", "name": "報表設計",
     "nav_label": "報表設計", "page_url": "reports.html",
     "show_frontend": False, "show_backend": True, "sort_order": 98},
    {"code": "F0-10", "module": "目標零", "name": "資料庫備份與還原",
     # 備份紀錄查詢已內建在「稽核/登入紀錄」（F0-11）頁面的分頁籤裡
     "nav_label": "資料庫備份與還原", "page_url": "logs.html",
     "show_frontend": False, "show_backend": False, "sort_order": 0},
    {"code": "F0-12", "module": "目標零", "name": "登入紀錄查詢",
     # 已內建在「稽核/登入紀錄」（F0-11）頁面裡，不重複顯示
     "nav_label": "登入紀錄查詢", "page_url": "logs.html",
     "show_frontend": False, "show_backend": False, "sort_order": 0},
]
