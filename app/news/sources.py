"""
來源註冊表 — 中藥與腫瘤 10 個權威官方追蹤網站
=================================================
每個來源定義抓取方式（api / rss / scrape）、證據層級、權重與過濾規則。

2026-08 實測狀態（見 docs/SOURCE_VERIFICATION.md）：
  - ClinicalTrials.gov API v2 ...... 可用（已實測回傳 JSON）
  - WHO news RSS .................. 可用（已實測 RSS 2.0）
  - NCI syndication RSS ........... 可用（官方 syndication 頁列出）
  - PubMed E-utilities ............ 官方 API，需 email + 可選 api_key
  - NCCIH / OCCAM / MSK ........... 無 RSS，走 HTML 爬蟲
  - NHC / SATCM ................... 中國官方站，走 HTML 爬蟲，需伺服器可連線

注意：本平台為科研輔助工具。所有抓取內容僅作研究情報彙整，
不構成醫療診斷或治療建議。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CollectorKind(str, Enum):
    API = "api"
    RSS = "rss"
    SCRAPE = "scrape"


class EvidenceLevel(str, Enum):
    """對應 docx 指南的「證據層級」分類，用於前端標籤與排序權重。"""

    POLICY_GLOBAL = "policy_global"        # 政策與全球標準
    CLINICAL_EVIDENCE = "clinical_evidence"  # 癌症臨床與實證
    RESEARCH_POLICY = "research_policy"    # 研究政策與資助
    NATURAL_PRODUCT = "natural_product"    # 天然物研究與安全
    LITERATURE_INDEX = "literature_index"  # 學術文獻索引
    TRIAL_REGISTRY = "trial_registry"      # 臨床試驗登錄
    CANCER_CENTER = "cancer_center"        # 癌症中心臨床實務
    HERB_SAFETY = "herb_safety"            # 草藥安全與交互作用
    NATIONAL_POLICY = "national_policy"    # 國家衛生政策
    TCM_POLICY = "tcm_policy"              # 中醫藥國家政策


@dataclass(frozen=True)
class SourceDef:
    slug: str
    name_zh: str
    name_en: str
    homepage: str
    kind: CollectorKind
    evidence_level: EvidenceLevel
    # 排序權重：官方臨床/試驗證據 > 政策 > 一般新聞
    weight: float
    # 該來源是否天然就與腫瘤+中藥相關（True 表示可略過關鍵字硬過濾，
    # 例如 PubMed 查詢字串本身已鎖定主題）
    prefiltered: bool = False
    lang: str = "en"
    config: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


# --------------------------------------------------------------------------
# PubMed 檢索式：依 docx「建議追蹤」章節設計
# --------------------------------------------------------------------------
PUBMED_QUERY = (
    "("
    "  cancer[Title/Abstract] OR tumor[Title/Abstract] OR tumour[Title/Abstract]"
    "  OR neoplasm[Title/Abstract] OR carcinoma[Title/Abstract]"
    "  OR oncology[Title/Abstract] OR \"Neoplasms\"[MeSH Terms]"
    ") AND ("
    "  \"traditional chinese medicine\"[Title/Abstract]"
    "  OR \"chinese herbal medicine\"[Title/Abstract]"
    "  OR \"chinese medicine\"[Title/Abstract]"
    "  OR \"herbal medicine\"[Title/Abstract]"
    "  OR \"botanical drug\"[Title/Abstract]"
    "  OR \"integrative oncology\"[Title/Abstract]"
    "  OR \"Medicine, Chinese Traditional\"[MeSH Terms]"
    "  OR \"Drugs, Chinese Herbal\"[MeSH Terms]"
    ")"
)

# ClinicalTrials.gov 介入關鍵字（分次查詢後合併去重）
CTGOV_INTERVENTION_QUERIES = [
    "chinese herbal medicine",
    "traditional chinese medicine",
    "botanical drug",
    "acupuncture",
    "integrative oncology",
]


SOURCES: list[SourceDef] = [
    # ---------------------------------------------------------------- 1. WHO
    SourceDef(
        slug="who_tcim",
        name_zh="世界衛生組織（WHO）－傳統、補充與整合醫學",
        name_en="WHO Traditional, Complementary and Integrative Medicine",
        homepage="https://www.who.int/health-topics/traditional-complementary-and-integrative-medicine",
        kind=CollectorKind.RSS,
        evidence_level=EvidenceLevel.POLICY_GLOBAL,
        weight=0.75,
        config={
            # 實測 2026-08：RSS 2.0，含 title / link / pubDate / description
            "feed_url": "https://www.who.int/rss-feeds/news-english.xml",
            "fallback_scrape": {
                "list_url": "https://www.who.int/news-room/releases",
                "item_selector": "a.sf-list-vertical__item, .list-view--item a",
                "title_selector": ".heading, .full-title",
                "date_selector": ".date, .timestamp",
            },
        },
        notes="全球策略、傳統醫學產品品質/安全/監管、Traditional Medicine Global Library。"
        "WHO 支持不等於認可特定中藥可治癌。",
    ),
    # ---------------------------------------------------------------- 2. NCI
    SourceDef(
        slug="nci",
        name_zh="美國國家癌症研究所（NCI）",
        name_en="National Cancer Institute",
        homepage="https://www.cancer.gov/",
        kind=CollectorKind.RSS,
        evidence_level=EvidenceLevel.CLINICAL_EVIDENCE,
        weight=0.90,
        config={
            # 實測 2026-08：cancer.gov/syndication/rss 官方列出
            "feed_urls": [
                "https://www.cancer.gov/publishedcontent/rss/syndication/rss/ncinewsreleases.rss",
                "https://www.cancer.gov/publishedcontent/rss/news-events/cancer-currents-blog.rss",
            ],
        },
        notes="PDQ 整合／替代療法摘要、癌症治療指引、研究新聞。"
        "注意區分實驗室研究、動物研究與人體臨床證據。",
    ),
    # -------------------------------------------------------------- 3. OCCAM
    SourceDef(
        slug="nci_occam",
        name_zh="NCI 癌症補充與替代醫學辦公室（OCCAM）",
        name_en="NCI Office of Cancer Complementary and Alternative Medicine",
        homepage="https://cam.cancer.gov/",
        kind=CollectorKind.SCRAPE,
        evidence_level=EvidenceLevel.RESEARCH_POLICY,
        weight=0.85,
        prefiltered=True,  # 站台本身即為癌症整合醫學專門單位
        config={
            "list_urls": [
                "https://cam.cancer.gov/news_events/index.htm",
                "https://cam.cancer.gov/health_information/index.htm",
            ],
            "item_selector": "main a[href], .content a[href]",
            "link_must_contain": ["cam.cancer.gov", "/news", "/health_information"],
            "date_regex": r"(\w+\s+\d{1,2},\s+\d{4})|(\d{4}-\d{2}-\d{2})",
        },
        notes="中藥複方標準化、天然產物抗癌研究、支持性照護的研究設計與資助方向。",
    ),
    # ------------------------------------------------------------- 4. NCCIH
    SourceDef(
        slug="nccih",
        name_zh="美國國家補充與整合健康中心（NCCIH）",
        name_en="National Center for Complementary and Integrative Health",
        homepage="https://www.nccih.nih.gov/news",
        kind=CollectorKind.SCRAPE,
        evidence_level=EvidenceLevel.NATURAL_PRODUCT,
        weight=0.85,
        config={
            # 實測 2026-08：/news/rss 回 404，頁面無 rel=alternate feed → 走爬蟲
            "list_urls": [
                "https://www.nccih.nih.gov/news/press-releases",
                "https://www.nccih.nih.gov/news/agency",
                "https://www.nccih.nih.gov/health/safety-information",
            ],
            "item_selector": "article a, .views-row a, h3 a",
            "link_must_contain": ["/news/", "/health/"],
            "date_selector": "time, .date-display-single",
        },
        notes="天然產物臨床試驗規格（原料鑑別、批次一致性、化學指紋、毒理）、"
        "膳食補充品與癌症治療交互作用安全警訊。",
    ),
    # ------------------------------------------------------------- 5. PubMed
    SourceDef(
        slug="pubmed",
        name_zh="NIH PubMed",
        name_en="PubMed",
        homepage="https://pubmed.ncbi.nlm.nih.gov/",
        kind=CollectorKind.API,
        evidence_level=EvidenceLevel.LITERATURE_INDEX,
        weight=0.80,
        prefiltered=True,
        config={
            "esearch": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            "esummary": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            "efetch": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            "db": "pubmed",
            "query": PUBMED_QUERY,
            "reldate_days": 3,      # 每日跑，抓 3 天回溯以吃掉 indexing 延遲
            "datetype": "edat",
            "retmax": 120,
            # 依 NCBI 規範：無 api_key 每秒 3 req，有 key 每秒 10 req
            "rate_limit_per_sec": 3,
            "tool": "grace-tcm-news",
            # 加分：這些出版類型代表較高證據層級
            "high_value_pubtypes": [
                "Randomized Controlled Trial",
                "Systematic Review",
                "Meta-Analysis",
                "Clinical Trial, Phase III",
                "Clinical Trial, Phase II",
                "Practice Guideline",
            ],
        },
        notes="收錄不代表結論正確；須檢查研究設計、期刊、樣本數、偏差風險與重複驗證。",
    ),
    # ----------------------------------------------------- 6. ClinicalTrials
    SourceDef(
        slug="clinicaltrials",
        name_zh="ClinicalTrials.gov",
        name_en="ClinicalTrials.gov",
        homepage="https://clinicaltrials.gov/",
        kind=CollectorKind.API,
        evidence_level=EvidenceLevel.TRIAL_REGISTRY,
        weight=0.88,
        prefiltered=True,
        config={
            # 實測 2026-08：API v2 正常回傳
            "base_url": "https://clinicaltrials.gov/api/v2/studies",
            "condition": "cancer OR tumor OR neoplasm",
            "intervention_queries": CTGOV_INTERVENTION_QUERIES,
            "page_size": 50,
            "fields": [
                "protocolSection.identificationModule.nctId",
                "protocolSection.identificationModule.briefTitle",
                "protocolSection.identificationModule.officialTitle",
                "protocolSection.statusModule.overallStatus",
                "protocolSection.statusModule.lastUpdatePostDateStruct",
                "protocolSection.statusModule.studyFirstPostDateStruct",
                "protocolSection.designModule.phases",
                "protocolSection.designModule.enrollmentInfo",
                "protocolSection.designModule.designInfo",
                "protocolSection.conditionsModule.conditions",
                "protocolSection.armsInterventionsModule.interventions",
                "protocolSection.descriptionModule.briefSummary",
                "protocolSection.sponsorCollaboratorsModule.leadSponsor",
            ],
            "lookback_days": 3,
        },
        notes="登錄不等於有效；應查看狀態、設計、樣本數、主要終點、結果與不良事件。",
    ),
    # ---------------------------------------------------------------- 7. MSK
    SourceDef(
        slug="msk_integrative",
        name_zh="Memorial Sloan Kettering－整合醫學",
        name_en="MSKCC Integrative Medicine",
        homepage="https://www.mskcc.org/cancer-care/diagnosis-treatment/symptom-management/integrative-medicine",
        kind=CollectorKind.SCRAPE,
        evidence_level=EvidenceLevel.CANCER_CENTER,
        weight=0.82,
        config={
            # 實測 2026-08：/news 未暴露 RSS → 爬蟲
            "list_urls": [
                "https://www.mskcc.org/news",
                "https://www.mskcc.org/news-releases",
                "https://www.mskcc.org/cancer-care/diagnosis-treatment/symptom-management/integrative-medicine",
            ],
            "item_selector": "a[href^='/news'], a[href^='/news-releases'], article a",
            "base": "https://www.mskcc.org",
            "date_selector": "time, .date",
        },
        notes="官方新聞通常清楚區分腫瘤治療與症狀管理；重點在癌痛、疲倦、"
        "神經病變、腦霧、睡眠、噁心與生活品質的隨機試驗。",
    ),
    # -------------------------------------------------------- 8. About Herbs
    SourceDef(
        slug="msk_about_herbs",
        name_zh="MSK About Herbs 資料庫",
        name_en="MSK About Herbs Database",
        homepage="https://www.mskcc.org/cancer-care/integrative-medicine/herbs",
        kind=CollectorKind.SCRAPE,
        evidence_level=EvidenceLevel.HERB_SAFETY,
        weight=0.86,
        prefiltered=True,
        config={
            "list_urls": [
                "https://www.mskcc.org/cancer-care/integrative-medicine/herbs",
            ],
            "item_selector": "a[href*='/integrative-medicine/herbs/']",
            "base": "https://www.mskcc.org",
            # About Herbs 是資料庫而非新聞流：偵測條目「最後更新日」變動
            "track_mode": "content_change",
            "content_hash_selector": ".field--name-body, main",
            "date_selector": "time, .updated-date",
        },
        notes="安全警示來源，不是療效推薦引擎。重點：CYP 酵素、P-gp、抗凝血、"
        "化療／標靶／免疫／荷爾蒙治療交互作用。",
    ),
    # ---------------------------------------------------------------- 9. NHC
    SourceDef(
        slug="cn_nhc",
        name_zh="中國國家衛生健康委員會",
        name_en="National Health Commission of China",
        homepage="https://www.nhc.gov.cn/",
        kind=CollectorKind.SCRAPE,
        evidence_level=EvidenceLevel.NATIONAL_POLICY,
        weight=0.70,
        lang="zh-CN",
        config={
            "list_urls": [
                "https://www.nhc.gov.cn/xcs/xwbd/list.shtml",
                "https://www.nhc.gov.cn/yzygj/zcwj2/list.shtml",
                "https://www.nhc.gov.cn/wjw/index.shtml",
            ],
            "item_selector": "ul.zxxx_list li a, .list li a, td a",
            "date_selector": ".date, span",
            "base": "https://www.nhc.gov.cn",
            "encoding": "utf-8",
            # 中國站台常需完整 UA 且對雲端 IP 較敏感；失敗不阻斷整體流程
            "requires_browser_ua": True,
            "allow_failure": True,
        },
        notes="政策支持與個別方劑的臨床療效證明必須分開解讀。",
    ),
    # -------------------------------------------------------------- 10. SATCM
    SourceDef(
        slug="cn_satcm",
        name_zh="中國國家中醫藥管理局",
        name_en="National Administration of Traditional Chinese Medicine",
        homepage="https://www.satcm.gov.cn/",
        kind=CollectorKind.SCRAPE,
        evidence_level=EvidenceLevel.TCM_POLICY,
        weight=0.70,
        lang="zh-CN",
        config={
            "list_urls": [
                "https://www.satcm.gov.cn/xinxifabu/gongzuodongtai/",
                "https://www.satcm.gov.cn/xinxifabu/meitibaodao/",
                "https://www.satcm.gov.cn/hudongjiaoliu/guanfangwenda/",
            ],
            "item_selector": "ul.list li a, .listBox li a, td a",
            "date_selector": "span.date, .time",
            "base": "https://www.satcm.gov.cn",
            "encoding": "utf-8",
            "requires_browser_ua": True,
            "allow_failure": True,
        },
        notes="腫瘤專科建設、診療方案、科研專項、中藥監管與中西醫結合示範項目。"
        "判斷療效仍需回到完整臨床試驗與同行審查證據。",
    ),
]

SOURCE_BY_SLUG: dict[str, SourceDef] = {s.slug: s for s in SOURCES}


# --------------------------------------------------------------------------
# 主題過濾關鍵字（給沒有 prefiltered 的來源用）
# --------------------------------------------------------------------------
CANCER_TERMS = [
    "cancer", "tumor", "tumour", "neoplasm", "carcinoma", "oncology",
    "oncologic", "leukemia", "leukaemia", "lymphoma", "sarcoma", "melanoma",
    "metastasis", "metastatic", "chemotherapy", "radiotherapy", "immunotherapy",
    "腫瘤", "癌", "肿瘤", "化療", "化疗", "放療", "放疗", "免疫治療", "免疫治疗",
]

TCM_TERMS = [
    "traditional chinese medicine", "chinese herbal", "chinese medicine",
    "herbal medicine", "herb", "herbal", "botanical", "natural product",
    "acupuncture", "integrative medicine", "integrative oncology",
    "complementary medicine", "dietary supplement", "phytochemical",
    "中藥", "中医药", "中醫藥", "中药", "草藥", "草药", "針灸", "针灸",
    "中西醫", "中西医", "方劑", "方剂", "本草",
]

# 命中即大幅加分（安全訊號優先，符合 docx「安全監測」定位）
SAFETY_TERMS = [
    "interaction", "adverse", "toxicity", "hepatotoxicity", "nephrotoxicity",
    "contraindication", "warning", "recall", "cyp", "p-gp", "anticoagulant",
    "交互作用", "不良反應", "不良反应", "毒性", "肝損傷", "肝损伤", "禁忌", "警訊",
]
