// 登入頁 3D：七本秘笈、花園、巫師的介紹內容（v1.46.6）
//
// 為什麼不放進 i18n-dict.js：每本秘笈的說明超過一千字、分成六段，逐句放進精確比對字典既難維護也容易漏翻。
// 這裡每一項直接存繁中（tw）、英文（en）、韓文（ko）三份；簡中（cn）由繁中經 window.loginT（OpenCC）轉換。
// 數字以平台實際資料為準（見專案文件「六庫串接欄位對照」「六庫各自提供什麼」），資料更新後要一併檢查。
window.LOGIN3D_INFO = (function () {
  const db = [
    {
      key: "TCMSP", url: "https://tcmsp-e.com/",
      tw: {
        name: "TCMSP", manual: "本草藥理真經", star: "天樞",
        sub: "中藥系統藥理學資料庫與分析平台・西北農林科技大學",
        sections: [
          ["重點摘要", "TCMSP 是整條分析鏈路的起點與骨幹：它把一味中藥拆成成分，附上吸收與類藥性參數，再連到靶點與疾病。本平台的 502 種藥材、活性成分篩選（OB ≥ 30%、DL ≥ 0.18）與藥材、疾病兩個查詢站，都建立在這個資料庫之上，其他六個資料庫則負責替它補上結構、基因、通路與細胞層級的證據。"],
          ["維運單位", "TCMSP（Traditional Chinese Medicine Systems Pharmacology Database and Analysis Platform，中藥系統藥理學資料庫與分析平台）由西北農林科技大學生命科學學院系統藥理學實驗室（王永華教授團隊）建置與維護，2014 年發表於《Journal of Cheminformatics》，是網路藥理學研究最常被引用的中藥資料庫之一。官方網站可線上瀏覽與查詢，不需付費。"],
          ["資料庫簡介", "官方公布的收錄規模為 499 種《中華人民共和國藥典》登錄的中藥材、29,384 個化學成分、3,311 個作用靶點與 837 種相關疾病。每個成分都附有 12 項與藥物動力學和類藥性相關的計算值，包括口服生物利用度（OB）、類藥性（DL）、分子量、脂水分配係數、氫鍵供體與受體數、半衰期、Caco-2 細胞通透性、血腦屏障通透性、拓撲極性表面積與可旋轉鍵數等。靶點與疾病的對應整理自 TTD、PharmGKB 等公開資料庫。"],
          ["關鍵數字", "官方收錄：中藥材 499 種、成分 29,384 個、靶點 3,311 個、疾病 837 種，每個成分附 12 項 ADME 參數。本平台上架：藥材 502 種、疾病 564 種，其中依 ICD 代碼判定為腫瘤的有 116 種。活性成分的篩選門檻是口服生物利用度 OB ≥ 30% 且類藥性 DL ≥ 0.18。以人參為例，190 個成分中有 22 個通過篩選，連到 118 個靶點。"],
          ["重要性", "一味中藥含有數十到數百個成分，傳統上很難說清楚「到底是哪個分子在作用」。TCMSP 把藥材拆解成可計算的分子層級，並提供吸收與類藥性的初步篩選依據，讓研究者能從藥材出發，一路追到成分、靶點與疾病。它是本平台整條分析鏈路的骨幹：其他六個資料庫都接在 TCMSP 的成分或靶點之後，替它補上結構、基因、通路與細胞層級的證據。"],
          ["可提供的中藥整合資訊", "藥材的中文名、拼音、英文名與基原植物；每味藥材的全部成分與 12 項 ADME 參數；成分與靶點的關聯（附是否經實驗驗證的註記，以及支持向量機、隨機森林的預測分數）；靶點與疾病的關聯，以及疾病的 ICD-9、ICD-10 代碼。這些資訊可以回答：這味藥有哪些成分？哪些成分可能被口服吸收？它們可能作用在哪些蛋白？又牽涉哪些疾病？"],
          ["本平台介接方式", "平台以匯入腳本將整理好的 TCMSP 資料寫入四張主表（藥材、成分、靶點、疾病）與三張關聯表，目前上架 502 種藥材、564 種疾病。TCMSP 自有編號（MOL、TAR、DIS）作為內部外鍵；活性成分以 OB ≥ 30% 且 DL ≥ 0.18 篩選；疾病另依 ICD 代碼標註腫瘤分類。使用者可在「TCMSP 藥材關聯查詢站」與「疾病關聯查詢站」雙向查詢，外部連結一律指向 TCMSP 的瀏覽頁面。"],
          ["研究應用", "典型的網路藥理學流程從 TCMSP 開始：先選定藥材或複方，取出全部成分並用 ADME 門檻篩出活性成分，再收集這些成分的靶點，與疾病相關基因取交集，最後建立「藥材–成分–靶點–疾病」網路，找出連結最多的核心成分與核心靶點。在本平台，這整段流程不用寫程式：在查詢站點選藥材，就能看到成分表、靶點表與關聯圖，並可勾選特定靶點簡化網路，或從疾病端反向查回含有相關成分的藥材。"],
          ["使用限制與注意", "TCMSP 不提供化學結構與標準基因符號，這兩項分別由 PubChem 與 UniProt 補上；它的 DrugBank 欄位實際上是流水號，不能直接串接。成分與靶點的關聯沒有區分實驗證據與電腦預測，解讀時必須保守。此外，OB 門檻會刷掉多數大分子的皂苷類成分（例如人參皂苷），而它們在體內可能經腸道菌轉化後才被吸收，這是網路藥理學方法的共同限制。"],
        ],
      },
      en: {
        name: "TCMSP", manual: "Canon of Herbal Pharmacology", star: "Dubhe",
        sub: "Traditional Chinese Medicine Systems Pharmacology Database · Northwest A&F University",
        sections: [
          ["In brief", "TCMSP is the starting point and backbone of the whole analysis chain: it breaks an herb into components, attaches absorption and drug-likeness parameters, and links them to targets and diseases. The platform's 502 herbs, its active-component screen (OB ≥ 30%, DL ≥ 0.18) and its herb and disease query stations are all built on it; the other six databases add structural, genetic, pathway and cell-level evidence."],
          ["Maintained by", "TCMSP (Traditional Chinese Medicine Systems Pharmacology Database and Analysis Platform) was built and is maintained by the Lab of Systems Pharmacology, College of Life Sciences, Northwest A&F University (Prof. Yonghua Wang's team). It was published in the Journal of Cheminformatics in 2014 and is one of the most cited herbal databases in network pharmacology. The website is free to browse and search."],
          ["About the database", "Its published scope is 499 herbs listed in the Chinese Pharmacopoeia, 29,384 chemical components, 3,311 targets and 837 related diseases. Every component carries 12 computed pharmacokinetic and drug-likeness properties, including oral bioavailability (OB), drug-likeness (DL), molecular weight, AlogP, H-bond donors and acceptors, half-life, Caco-2 permeability, blood–brain barrier permeability, topological polar surface area and rotatable bonds. Target–disease links are compiled from public sources such as TTD and PharmGKB."],
          ["Key figures", "Official scope: 499 herbs, 29,384 components, 3,311 targets and 837 diseases, with 12 ADME parameters per component. On this platform: 502 herbs and 564 diseases, 116 of which are classified as tumors from their ICD codes. Active components must have oral bioavailability OB ≥ 30% and drug-likeness DL ≥ 0.18. For ginseng, 22 of 190 components pass the screen and link to 118 targets."],
          ["Why it matters", "A single herb contains tens to hundreds of components, so it has always been hard to say which molecule is actually doing the work. TCMSP breaks herbs down to a computable molecular level and provides first-pass absorption and drug-likeness filters, so researchers can trace herb → component → target → disease. It is the backbone of this platform's analysis chain: the other six databases all attach to TCMSP components or targets and add structural, genetic, pathway and cell-level evidence."],
          ["What it adds to herb integration", "Herb names in Chinese, pinyin and English, with the source plant; every component of every herb with 12 ADME parameters; component–target links (with a flag for experimental validation and SVM / random-forest prediction scores); target–disease links with ICD-9 and ICD-10 codes. Together these answer: what is in this herb, which components may be absorbed orally, which proteins might they act on, and which diseases are involved?"],
          ["How this platform connects", "An import script loads curated TCMSP data into four main tables (herbs, components, targets, diseases) and three link tables; 502 herbs and 564 diseases are currently available. TCMSP's own IDs (MOL, TAR, DIS) serve as internal foreign keys. Active components are screened with OB ≥ 30% and DL ≥ 0.18, and diseases are additionally classified as tumor or non-tumor from their ICD codes. Users can search both directions in the TCMSP herb query station and the disease query station; outbound links point to TCMSP's browse pages."],
          ["Research use", "A typical network-pharmacology workflow starts with TCMSP: choose an herb or formula, take all its components and filter the active ones by ADME thresholds, collect their targets, intersect them with disease-related genes, and build an herb–component–target–disease network to find the most connected core components and targets. On this platform the whole workflow needs no code: select an herb in the query station to see its component table, target table and network graph, tick specific targets to simplify the network, or work backwards from a disease to the herbs containing related components."],
          ["Limitations", "TCMSP has no chemical structures or standard gene symbols — PubChem and UniProt fill those gaps — and its DrugBank column is actually a serial number, so it cannot be joined directly. Component–target links do not separate experimental evidence from computational prediction, so they must be read conservatively. The OB threshold also removes most large saponins (such as ginsenosides), which may be absorbed only after conversion by gut bacteria — a limitation shared by network pharmacology in general."],
        ],
      },
      ko: {
        name: "TCMSP", manual: "본초약리진경", star: "천추",
        sub: "중약 시스템 약리학 데이터베이스 · 서북농림과기대학",
        sections: [
          ["한눈에 보기", "TCMSP는 전체 분석 체인의 출발점이자 중심축입니다. 중약 한 가지를 성분으로 나누고 흡수성·약물유사성 파라미터를 붙인 뒤 표적과 질병으로 연결합니다. 플랫폼의 약재 502종, 활성 성분 선별(OB ≥ 30%, DL ≥ 0.18), 약재·질병 조회 화면이 모두 이 데이터베이스 위에 세워졌고, 나머지 여섯 데이터베이스가 구조·유전자·경로·세포 수준의 근거를 보완합니다."],
          ["운영 기관", "TCMSP(Traditional Chinese Medicine Systems Pharmacology Database and Analysis Platform)는 중국 서북농림과기대학 생명과학대학 시스템약리학 연구실(왕융화 교수 연구팀)이 구축·운영합니다. 2014년 Journal of Cheminformatics에 발표되었으며, 네트워크 약리학 연구에서 가장 많이 인용되는 중약 데이터베이스 중 하나입니다. 웹사이트에서 무료로 열람·검색할 수 있습니다."],
          ["데이터베이스 소개", "공식 수록 규모는 중국 약전에 등재된 중약재 499종, 화학 성분 29,384개, 작용 표적 3,311개, 관련 질병 837종입니다. 모든 성분에는 경구 생체이용률(OB), 약물유사성(DL), 분자량, 지용성 계수, 수소결합 공여·수용체 수, 반감기, Caco-2 투과성, 혈뇌장벽 투과성, 위상 극성 표면적, 회전 가능 결합 수 등 약동학·약물유사성 관련 계산값 12항목이 붙어 있습니다. 표적–질병 연결은 TTD, PharmGKB 등 공개 데이터베이스에서 정리했습니다."],
          ["핵심 수치", "공식 수록: 중약재 499종, 성분 29,384개, 표적 3,311개, 질병 837종이며, 성분마다 ADME 파라미터 12항목이 있습니다. 본 플랫폼 등록: 약재 502종, 질병 564종이며 그중 ICD 코드로 종양으로 판정된 것은 116종입니다. 활성 성분 선별 기준은 경구 생체이용률 OB ≥ 30%, 약물유사성 DL ≥ 0.18입니다. 인삼의 경우 성분 190개 중 22개가 선별을 통과해 표적 118개와 연결됩니다."],
          ["중요성", "중약 한 가지에는 수십에서 수백 개의 성분이 들어 있어, 어떤 분자가 실제로 작용하는지 설명하기 어려웠습니다. TCMSP는 약재를 계산 가능한 분자 수준으로 분해하고 흡수성과 약물유사성의 1차 선별 기준을 제공하여, 연구자가 약재 → 성분 → 표적 → 질병으로 추적할 수 있게 합니다. 본 플랫폼 분석 체인의 중심축으로, 나머지 여섯 데이터베이스는 모두 TCMSP의 성분이나 표적 뒤에 연결되어 구조·유전자·경로·세포 수준의 근거를 더합니다."],
          ["중약 통합에 제공하는 정보", "약재의 중국어명, 병음, 영문명과 기원 식물; 약재별 전체 성분과 ADME 파라미터 12항목; 성분–표적 연결(실험 검증 여부 표시, SVM·랜덤 포레스트 예측 점수 포함); 표적–질병 연결과 질병의 ICD-9, ICD-10 코드. 이를 통해 이 약재에 어떤 성분이 있는지, 어떤 성분이 경구 흡수될 수 있는지, 어떤 단백질에 작용할 수 있는지, 어떤 질병과 관련되는지 답할 수 있습니다."],
          ["본 플랫폼 연동 방식", "가져오기 스크립트로 정리된 TCMSP 데이터를 주 테이블 4개(약재, 성분, 표적, 질병)와 연결 테이블 3개에 기록하며, 현재 약재 502종과 질병 564종이 등록되어 있습니다. TCMSP 자체 번호(MOL, TAR, DIS)를 내부 외래키로 사용하고, 활성 성분은 OB ≥ 30%, DL ≥ 0.18로 선별합니다. 질병은 ICD 코드로 종양 분류를 추가 표시합니다. 'TCMSP 약재 연관 조회'와 '질병 연관 조회'에서 양방향으로 검색할 수 있고, 외부 링크는 TCMSP 열람 페이지로 연결됩니다."],
          ["연구 활용", "전형적인 네트워크 약리학 흐름은 TCMSP에서 시작합니다. 약재나 처방을 정하고, 전체 성분을 꺼내 ADME 기준으로 활성 성분을 선별한 뒤, 그 성분들의 표적을 모아 질병 관련 유전자와 교집합을 구하고, '약재–성분–표적–질병' 네트워크를 만들어 연결이 가장 많은 핵심 성분과 핵심 표적을 찾습니다. 본 플랫폼에서는 이 과정 전체를 코드 없이 할 수 있습니다. 조회 화면에서 약재를 선택하면 성분표, 표적표, 관계도를 보고, 특정 표적을 골라 네트워크를 단순화하거나 질병에서 관련 성분을 가진 약재를 역으로 찾을 수 있습니다."],
          ["사용상 한계", "TCMSP에는 화학 구조와 표준 유전자 기호가 없어 각각 PubChem과 UniProt으로 보완합니다. DrugBank 열은 실제로는 일련번호라 직접 연결할 수 없습니다. 성분–표적 연결은 실험 근거와 컴퓨터 예측을 구분하지 않으므로 보수적으로 해석해야 합니다. 또한 OB 기준은 인삼 사포닌 같은 대분자 사포닌 대부분을 걸러내는데, 이들은 장내 세균에 의해 변환된 뒤 흡수될 수 있어 네트워크 약리학 방법의 공통 한계입니다."],
        ],
      },
    },
    {
      key: "PubChem", url: "https://pubchem.ncbi.nlm.nih.gov/",
      tw: {
        name: "PubChem", manual: "萬化分子譜", star: "天璇",
        sub: "美國國家生物技術資訊中心（NCBI／NLM／NIH）",
        sections: [
          ["重點摘要", "PubChem 負責把中藥成分的「名稱」變成真正的「分子」：取得 CID、SMILES、InChIKey 與分子量，並用分子量和 TCMSP 互相驗算。這是整條鏈路唯一的獨立驗算關卡，結構確定之後，成分才能和其他藥物資料、結構比對與計算化學研究接起來。"],
          ["維運單位", "PubChem 由美國國家衛生研究院（NIH）國家醫學圖書館（NLM）轄下的國家生物技術資訊中心（NCBI）建置與維護，2004 年上線。所有資料免費公開，並提供 PUG REST 等程式介面，方便研究者大量查詢與下載。"],
          ["資料庫簡介", "PubChem 是全球規模最大的公開化學資料庫，收錄超過一億筆不重複的化合物，彙整來自數百個資料提供者的化學物質紀錄與生物活性試驗結果。每個化合物有唯一的 CID（Compound ID），並附分子式、分子量、SMILES、InChI 與 InChIKey、IUPAC 命名、同義名稱與 CAS 登記號等資訊。"],
          ["關鍵數字", "化合物超過一億筆，每筆一個 CID。本平台：活性成分 2,632 個中有 1,303 個已完成結構對應（49.5%，2026 年 9 月查核）；分子量對帳容許誤差 0.5 Da；人參 22 個活性成分中有 17 個取得 SMILES、CAS 與 InChIKey 三者齊備的完整結構；苷元誤配防護已識別並攔下 81 筆可疑對應。"],
          ["重要性", "中藥成分在文獻與資料庫裡常有多種寫法，名稱並不可靠；只有化學結構才能唯一確定「這是哪一個分子」。PubChem 把成分名稱轉換成標準結構與識別碼，其中 InChIKey 是跨資料庫比對化合物最通用的鍵。少了這一步，中藥成分就無法和其他藥物資料、生物活性資料或結構相似性研究接起來。"],
          ["可提供的中藥整合資訊", "成分的 CID、標準與立體 SMILES、InChIKey、分子式、分子量、IUPAC 名稱、CAS 號與同義名稱，以及可直接顯示的 2D 結構圖。這些資訊可以回答：這個成分究竟是哪個分子？立體構型為何？能否用 InChIKey 到其他資料庫找到同一個化合物？能否進一步做結構相似性比較，找出結構相近的已知藥物？"],
          ["本平台介接方式", "平台以 PUG REST 依成分名稱查詢，採兩級策略：先用原名，查不到再用清理後的名稱。查回的分子量會和 TCMSP 自存的分子量對帳，容許誤差 0.5 Da，這是整條鏈路中唯一的獨立驗算依據；不符者降低信心並轉入待確認，不會自動採用。結果存入成分–PubChem 映射表，並針對苷元（名稱以 _qt 結尾）被誤配成帶糖基母體的情況設有防護。人參 22 個活性成分中，有 17 個取得完整結構。"],
          ["研究應用", "取得 SMILES 之後，研究者可以把中藥成分放進分子對接、定量構效關係（QSAR）、結構相似性搜尋等計算流程，也可以用 InChIKey 到藥物資料庫比對是否已有相同或相似結構的上市藥物。在本平台，成分頁會顯示 CID、SMILES、CAS 與結構資訊，標準化狀態分為自動採用、人工確認與待確認三種，研究者可以清楚分辨哪些結構可以直接引用、哪些仍需核對。"],
          ["使用限制與注意", "名稱解析不是真正的鍵，「名稱對上」不等於「分子對上」，所以平台保留每筆映射的來源與信心值，只有自動採用或人工確認的結果才會進入分析。PubChem 也收錄大量生物活性試驗（BioAssay），目前平台尚未串接。程式查詢須遵守 NCBI 的使用規範，每秒不超過 5 次請求，因此大量成分的標準化是分批在背景執行。"],
        ],
      },
      en: {
        name: "PubChem", manual: "Atlas of Ten Thousand Molecules", star: "Merak",
        sub: "US National Center for Biotechnology Information (NCBI / NLM / NIH)",
        sections: [
          ["In brief", "PubChem turns herbal component names into real molecules: it supplies the CID, SMILES, InChIKey and molecular weight, and the weight is cross-checked against TCMSP. This is the only independent checkpoint in the chain; once a structure is confirmed, the component can be linked to other drug data, structural comparisons and computational chemistry."],
          ["Maintained by", "PubChem is built and maintained by the National Center for Biotechnology Information (NCBI), part of the US National Library of Medicine (NLM) at the National Institutes of Health (NIH). It went online in 2004. All data are free and public, and programmatic interfaces such as PUG REST support large-scale queries and downloads."],
          ["About the database", "PubChem is the world's largest open chemistry database, with more than 100 million unique compounds, aggregating substance records and bioassay results from hundreds of data contributors. Each compound has a unique CID (Compound ID) along with its molecular formula, molecular weight, SMILES, InChI and InChIKey, IUPAC name, synonyms and CAS registry number."],
          ["Key figures", "More than 100 million compounds, one CID each. On this platform: 1,303 of 2,632 active components have structures mapped (49.5%, checked September 2026); molecular weight must agree within 0.5 Da; 17 of ginseng's 22 active components have complete structures with SMILES, CAS and InChIKey; the aglycone guard has identified and blocked 81 suspicious matches."],
          ["Why it matters", "Herbal components are written many different ways in papers and databases, so names are unreliable — only the chemical structure pins down which molecule it really is. PubChem turns component names into standard structures and identifiers; the InChIKey is the most widely used key for matching compounds across databases. Without this step, herbal components cannot be linked to other drug data, bioactivity data or structural-similarity studies."],
          ["What it adds to herb integration", "For each component: CID, canonical and isomeric SMILES, InChIKey, molecular formula, molecular weight, IUPAC name, CAS number and synonyms, plus a ready-to-display 2D structure image. These answer: which molecule is this component, what is its stereochemistry, can the InChIKey find the same compound in other databases, and can we compare structures to find similar known drugs?"],
          ["How this platform connects", "The platform queries PUG REST by component name in two tiers: the original name first, then a cleaned-up name. The returned molecular weight is reconciled against the weight stored in TCMSP within 0.5 Da — the only independent cross-check in the whole chain. Mismatches get lower confidence and go to manual review instead of being accepted automatically. Results are stored in a component–PubChem mapping table, with a guard against aglycones (names ending in _qt) being mismatched to their glycosylated parents. Of ginseng's 22 active components, 17 have complete structures."],
          ["Research use", "With SMILES in hand, researchers can feed herbal components into molecular docking, QSAR and structural-similarity searches, or use the InChIKey to check drug databases for marketed drugs with the same or similar structures. On this platform the component page shows CID, SMILES, CAS and structure information, and standardization status is one of automatically accepted, manually confirmed or pending, so researchers can tell which structures can be cited directly and which still need checking."],
          ["Limitations", "Name resolution is not a true key — a matching name does not guarantee a matching molecule — so the platform keeps the source and confidence of every mapping, and only automatically accepted or manually confirmed results enter analysis. PubChem also holds a large body of bioassays (BioAssay) that the platform does not yet use. Programmatic access must follow NCBI's usage policy of no more than 5 requests per second, so large batches of components are standardized in the background."],
        ],
      },
      ko: {
        name: "PubChem", manual: "만화분자보", star: "천선",
        sub: "미국 국립생물공학정보센터 (NCBI / NLM / NIH)",
        sections: [
          ["한눈에 보기", "PubChem은 중약 성분의 '이름'을 실제 '분자'로 바꿉니다. CID, SMILES, InChIKey, 분자량을 얻고 분자량으로 TCMSP와 서로 검증합니다. 이는 체인에서 유일한 독립 검증 관문이며, 구조가 확정되어야 성분을 다른 약물 데이터, 구조 비교, 계산화학 연구와 연결할 수 있습니다."],
          ["운영 기관", "PubChem은 미국 국립보건원(NIH) 국립의학도서관(NLM) 산하 국립생물공학정보센터(NCBI)가 구축·운영하며 2004년에 공개되었습니다. 모든 데이터는 무료로 공개되며, PUG REST 등 프로그램 인터페이스로 대량 조회와 다운로드가 가능합니다."],
          ["데이터베이스 소개", "PubChem은 세계 최대의 공개 화학 데이터베이스로, 1억 개가 넘는 고유 화합물을 수록하고 수백 개 데이터 제공처의 물질 기록과 생물 활성 시험 결과를 모읍니다. 각 화합물에는 고유한 CID(Compound ID)와 분자식, 분자량, SMILES, InChI 및 InChIKey, IUPAC 명명, 동의어, CAS 등록번호가 있습니다."],
          ["핵심 수치", "화합물 1억 개 이상, 각각 하나의 CID. 본 플랫폼: 활성 성분 2,632개 중 1,303개의 구조 대응 완료(49.5%, 2026년 9월 점검); 분자량 대조 허용 오차 0.5 Da; 인삼 활성 성분 22개 중 17개가 SMILES, CAS, InChIKey를 모두 갖춘 완전한 구조를 얻음; 아글리콘 오매칭 방지 장치가 의심 대응 81건을 식별·차단."],
          ["중요성", "중약 성분은 문헌과 데이터베이스마다 표기가 달라 이름만으로는 신뢰할 수 없고, 화학 구조만이 어떤 분자인지 유일하게 확정합니다. PubChem은 성분 이름을 표준 구조와 식별자로 바꿔 주며, 그중 InChIKey는 데이터베이스 간 화합물 비교에 가장 널리 쓰이는 키입니다. 이 단계가 없으면 중약 성분을 다른 약물 데이터, 생물 활성 데이터, 구조 유사성 연구와 연결할 수 없습니다."],
          ["중약 통합에 제공하는 정보", "성분의 CID, 표준·입체 SMILES, InChIKey, 분자식, 분자량, IUPAC 이름, CAS 번호와 동의어, 바로 표시할 수 있는 2D 구조 이미지. 이를 통해 이 성분이 정확히 어떤 분자인지, 입체 구조는 어떤지, InChIKey로 다른 데이터베이스에서 같은 화합물을 찾을 수 있는지, 구조가 비슷한 기존 약물을 찾을 수 있는지 답할 수 있습니다."],
          ["본 플랫폼 연동 방식", "플랫폼은 PUG REST로 성분 이름을 조회하며 두 단계로 진행합니다. 먼저 원래 이름으로, 실패하면 정리한 이름으로 조회합니다. 조회된 분자량은 TCMSP에 저장된 분자량과 0.5 Da 이내로 대조하는데, 이것이 전체 체인에서 유일한 독립 검증 근거입니다. 불일치하면 신뢰도를 낮추고 확인 대기로 보내며 자동 채택하지 않습니다. 결과는 성분–PubChem 매핑 테이블에 저장되며, 아글리콘(이름이 _qt로 끝남)이 당이 붙은 모체로 잘못 매칭되는 경우를 막는 장치가 있습니다. 인삼 활성 성분 22개 중 17개가 완전한 구조를 얻었습니다."],
          ["연구 활용", "SMILES를 얻으면 연구자는 중약 성분을 분자 도킹, 정량적 구조–활성 관계(QSAR), 구조 유사성 검색 같은 계산 흐름에 넣거나, InChIKey로 약물 데이터베이스에서 같거나 비슷한 구조의 시판 약물이 있는지 비교할 수 있습니다. 본 플랫폼의 성분 페이지에는 CID, SMILES, CAS와 구조 정보가 표시되고, 표준화 상태는 자동 채택, 수동 확인, 확인 대기 세 가지로 나뉘어 어떤 구조를 바로 인용할 수 있고 어떤 구조를 더 확인해야 하는지 구분할 수 있습니다."],
          ["사용상 한계", "이름 해석은 진짜 키가 아니어서 이름이 맞아도 분자가 맞는다는 보장은 없습니다. 그래서 플랫폼은 매핑마다 출처와 신뢰도를 보관하고, 자동 채택되었거나 사람이 확인한 결과만 분석에 사용합니다. PubChem의 방대한 생물 활성 시험(BioAssay)은 아직 연동하지 않았습니다. 프로그램 조회는 초당 5회 이하라는 NCBI 이용 규정을 지켜야 하므로, 대량 성분 표준화는 백그라운드에서 나누어 실행합니다."],
        ],
      },
    },
    {
      key: "UniProt", url: "https://www.uniprot.org/",
      tw: {
        name: "UniProt", manual: "蛋白靶點錄", star: "天璣",
        sub: "UniProt 聯盟（EMBL-EBI、SIB、PIR）",
        sections: [
          ["重點摘要", "UniProt 是全站的翻譯樞紐：把 TCMSP 的蛋白全名轉成國際通用的標準基因符號。完成這一步，中藥靶點才能和癌症基因清單、KEGG 與 Reactome 通路、DepMap 細胞株資料對話；平台的癌症基因比對率因此從 2.6% 提升到 18.0%。"],
          ["維運單位", "UniProt（Universal Protein Resource，通用蛋白質資源）由 UniProt 聯盟共同維護，成員包括歐洲生物資訊研究所（EMBL-EBI）、瑞士生物資訊研究所（SIB）與蛋白質資訊資源（PIR）。聯盟於 2002 年整合 Swiss-Prot、TrEMBL 與 PIR-PSD 三個資料庫而成，資料以 CC BY 4.0 授權公開。"],
          ["資料庫簡介", "UniProtKB 分為人工審閱的 Swiss-Prot 與自動註解的 TrEMBL 兩部分。Swiss-Prot 約有 57 萬筆經專家逐筆審閱的蛋白紀錄，其中人類蛋白約兩萬筆。每筆紀錄都有唯一的登錄號（accession）、標準基因符號、蛋白名稱、功能描述與細胞定位，以及連往 KEGG、Reactome、PDB 等上百個資料庫的交叉引用。"],
          ["關鍵數字", "Swiss-Prot 人工審閱紀錄約 57 萬筆，其中人類約 2 萬筆。本平台：靶點 1,751 個中有 1,265 個完成標準化（72.2%，2026 年 8 月查核）；癌症基因比對率從 2.6% 提升到 18.0%（1,245 個癌症基因中由 32 個增為 224 個）；人參 118 個靶點對應到 211 個基因符號（含同義詞）。自動採用門檻為信心值 ≥ 0.8。"],
          ["重要性", "TCMSP 的靶點多半以蛋白全名記錄，例如「Prostaglandin G/H synthase 2」，而大多數癌症與基因資料庫使用的是基因符號（PTGS2）。UniProt 是兩種語言之間的翻譯者：完成這一步後，中藥靶點才能和癌症基因清單、通路資料庫與細胞株依賴資料對話。在本平台，基因符號是全站通用的比對鍵，暗黑基因、疾病關聯與新聞實體連結都走它。"],
          ["可提供的中藥整合資訊", "靶點的 UniProt 登錄號、標準基因符號、基因同義名稱、正式蛋白名稱與物種，以及順帶取得的 KEGG 基因識別碼與 Reactome 通路識別碼。這些資訊可以回答：中藥成分打到的這個蛋白是哪一個基因？它還有哪些別名？它參與哪些通路？是否為人類蛋白？"],
          ["本平台介接方式", "平台以 UniProtKB REST 依靶點名稱查詢，採三級策略：精確名稱、拆詞組合查詢、全文查詢，並一律限定人類（organism_id 9606）與已審閱紀錄。三級的信心值依序為 1.0、0.8、0.5，達 0.8 才自動採用，全文查詢的結果一律進入待確認。目前 1,751 個靶點中有 1,265 個完成標準化（72.2%）；癌症基因的比對率因此從 2.6% 提升到 18.0%。"],
          ["研究應用", "標準化之後，研究者可以把靶點清單直接用於通路分析、蛋白交互作用網路或基因表現資料庫，也能和臨床基因檢測報告上的基因名稱對照。在本平台，靶點頁會顯示 UniProt 登錄號並連到 UniProt 條目；所有跨庫查詢（暗黑基因、GenCC 疾病關聯、新聞實體連結、DepMap 細胞株）都經過同一套判定邏輯，只採用自動採用或人工確認的映射，避免把未審閱的對應當成事實。"],
          ["使用限制與注意", "靶點側沒有像分子量那樣的獨立驗算依據，只能靠人工審閱，所以待確認的映射不得當成結論。同一個靶點名稱可能合法對應到多個基因，例如雌激素受體會對到 ESR1 與 ESR2。UniProt 告訴我們「這是哪個蛋白」，但不告訴我們「它在腫瘤裡重不重要」，那需要 OncoKB 與 DepMap 來回答。"],
        ],
      },
      en: {
        name: "UniProt", manual: "Record of Protein Targets", star: "Phecda",
        sub: "UniProt Consortium (EMBL-EBI, SIB, PIR)",
        sections: [
          ["In brief", "UniProt is the platform's translation hub: it converts TCMSP's full protein names into internationally standard gene symbols. Only then can herbal targets talk to cancer gene lists, KEGG and Reactome pathways and DepMap cell-line data — which raised the platform's cancer-gene match rate from 2.6% to 18.0%."],
          ["Maintained by", "UniProt (Universal Protein Resource) is maintained by the UniProt Consortium: the European Bioinformatics Institute (EMBL-EBI), the SIB Swiss Institute of Bioinformatics and the Protein Information Resource (PIR). The consortium was formed in 2002 by merging Swiss-Prot, TrEMBL and PIR-PSD, and its data are released under CC BY 4.0."],
          ["About the database", "UniProtKB has two parts: the manually reviewed Swiss-Prot and the automatically annotated TrEMBL. Swiss-Prot holds about 570,000 expert-reviewed protein entries, roughly 20,000 of them human. Each entry has a unique accession, a standard gene symbol, protein name, function and subcellular location, and cross-references to more than a hundred databases such as KEGG, Reactome and PDB."],
          ["Key figures", "Swiss-Prot holds about 570,000 manually reviewed entries, about 20,000 of them human. On this platform: 1,265 of 1,751 targets standardized (72.2%, checked August 2026); cancer-gene match rate raised from 2.6% to 18.0% (from 32 to 224 of 1,245 cancer genes); ginseng's 118 targets map to 211 gene symbols including synonyms. Automatic acceptance requires confidence ≥ 0.8."],
          ["Why it matters", "TCMSP records most targets by full protein name, e.g. \"Prostaglandin G/H synthase 2\", while most cancer and gene databases use gene symbols (PTGS2). UniProt translates between the two: only after this step can herbal targets talk to cancer gene lists, pathway databases and cell-line dependency data. On this platform the gene symbol is the shared key for everything — dark genes, disease associations and news entity links all go through it."],
          ["What it adds to herb integration", "For each target: UniProt accession, standard gene symbol, gene synonyms, recommended protein name and organism, plus the KEGG gene ID and Reactome pathway IDs that come with the entry. These answer: which gene is the protein hit by this herbal component, what other names does it have, which pathways is it in, and is it a human protein?"],
          ["How this platform connects", "The platform queries UniProtKB REST by target name in three tiers — exact name, split-term AND query, full text — always restricted to human (organism_id 9606) and reviewed entries. Confidence is 1.0, 0.8 and 0.5 for the three tiers; only ≥ 0.8 is accepted automatically, and full-text matches always go to manual review. 1,265 of 1,751 targets (72.2%) are now standardized, which raised the cancer-gene match rate from 2.6% to 18.0%."],
          ["Research use", "Once standardized, a target list can be used directly in pathway analysis, protein–protein interaction networks or gene-expression databases, and compared with gene names on clinical genetic test reports. On this platform the target page shows the UniProt accession with a link to the UniProt entry; every cross-database query (dark genes, GenCC disease associations, news entity links, DepMap cell lines) goes through the same decision logic and uses only automatically accepted or manually confirmed mappings, so unreviewed matches are never presented as fact."],
          ["Limitations", "Unlike molecular weight on the component side, there is no independent check on the target side — only human review — so pending mappings must not be treated as conclusions. One target name can legitimately map to several genes; the estrogen receptor maps to both ESR1 and ESR2. UniProt tells us which protein it is, not whether it matters in tumors; that is what OncoKB and DepMap answer."],
        ],
      },
      ko: {
        name: "UniProt", manual: "단백표적록", star: "천기",
        sub: "UniProt 컨소시엄 (EMBL-EBI, SIB, PIR)",
        sections: [
          ["한눈에 보기", "UniProt은 플랫폼 전체의 번역 허브로, TCMSP의 단백질 전체 이름을 국제 표준 유전자 기호로 바꿉니다. 이 단계를 거쳐야 중약 표적이 암 유전자 목록, KEGG·Reactome 경로, DepMap 세포주 데이터와 연결되며, 이로써 플랫폼의 암 유전자 매칭률이 2.6%에서 18.0%로 높아졌습니다."],
          ["운영 기관", "UniProt(Universal Protein Resource)는 유럽생물정보학연구소(EMBL-EBI), 스위스생물정보학연구소(SIB), 단백질정보자원(PIR)으로 구성된 UniProt 컨소시엄이 공동 운영합니다. 2002년 Swiss-Prot, TrEMBL, PIR-PSD 세 데이터베이스를 통합해 만들어졌으며, 데이터는 CC BY 4.0 라이선스로 공개됩니다."],
          ["데이터베이스 소개", "UniProtKB는 사람이 검토한 Swiss-Prot과 자동 주석의 TrEMBL로 나뉩니다. Swiss-Prot에는 전문가가 한 건씩 검토한 단백질 기록이 약 57만 건 있으며, 그중 인간 단백질은 약 2만 건입니다. 각 기록에는 고유 등록번호(accession), 표준 유전자 기호, 단백질 이름, 기능과 세포 내 위치, 그리고 KEGG, Reactome, PDB 등 백여 개 데이터베이스로의 교차 참조가 있습니다."],
          ["핵심 수치", "Swiss-Prot의 수동 검토 기록은 약 57만 건이며 그중 인간은 약 2만 건입니다. 본 플랫폼: 표적 1,751개 중 1,265개 표준화 완료(72.2%, 2026년 8월 점검); 암 유전자 매칭률 2.6% → 18.0%(암 유전자 1,245개 중 32개 → 224개); 인삼 표적 118개가 동의어 포함 유전자 기호 211개에 대응. 자동 채택 기준은 신뢰도 0.8 이상."],
          ["중요성", "TCMSP의 표적은 대부분 'Prostaglandin G/H synthase 2'처럼 단백질 전체 이름으로 기록되지만, 암·유전자 데이터베이스 대부분은 유전자 기호(PTGS2)를 씁니다. UniProt은 두 언어 사이의 번역자로, 이 단계를 거쳐야 중약 표적이 암 유전자 목록, 경로 데이터베이스, 세포주 의존성 데이터와 연결됩니다. 본 플랫폼에서 유전자 기호는 다크 유전자, 질병 연관, 뉴스 개체 연결 등 모든 비교의 공통 키입니다."],
          ["중약 통합에 제공하는 정보", "표적의 UniProt 등록번호, 표준 유전자 기호, 유전자 동의어, 공식 단백질 이름과 생물종, 그리고 함께 얻는 KEGG 유전자 식별자와 Reactome 경로 식별자. 이를 통해 중약 성분이 작용하는 단백질이 어떤 유전자인지, 다른 이름은 무엇인지, 어떤 경로에 관여하는지, 인간 단백질인지 답할 수 있습니다."],
          ["본 플랫폼 연동 방식", "플랫폼은 UniProtKB REST로 표적 이름을 세 단계(정확한 이름, 단어 분할 AND 조회, 전문 검색)로 조회하며, 항상 인간(organism_id 9606)과 검토된 기록으로 제한합니다. 단계별 신뢰도는 1.0, 0.8, 0.5이며 0.8 이상만 자동 채택하고, 전문 검색 결과는 모두 확인 대기로 보냅니다. 현재 표적 1,751개 중 1,265개(72.2%)가 표준화되었고, 이로써 암 유전자 매칭률이 2.6%에서 18.0%로 높아졌습니다."],
          ["연구 활용", "표준화 후에는 표적 목록을 경로 분석, 단백질 상호작용 네트워크, 유전자 발현 데이터베이스에 바로 쓰거나 임상 유전자 검사 보고서의 유전자 이름과 대조할 수 있습니다. 본 플랫폼의 표적 페이지에는 UniProt 등록번호와 UniProt 항목 링크가 표시되며, 모든 데이터베이스 간 조회(다크 유전자, GenCC 질병 연관, 뉴스 개체 연결, DepMap 세포주)는 같은 판정 로직을 거쳐 자동 채택이나 수동 확인된 매핑만 사용하므로 검토되지 않은 대응이 사실처럼 제시되지 않습니다."],
          ["사용상 한계", "성분 쪽의 분자량 같은 독립 검증 근거가 표적 쪽에는 없어 사람의 검토에만 의존하므로, 확인 대기 매핑을 결론으로 삼으면 안 됩니다. 하나의 표적 이름이 여러 유전자에 정당하게 대응될 수 있습니다(예: 에스트로겐 수용체 → ESR1, ESR2). UniProt은 '어떤 단백질인가'는 알려 주지만 '종양에서 중요한가'는 알려 주지 않으며, 그 답은 OncoKB와 DepMap이 제공합니다."],
        ],
      },
    },
    {
      key: "KEGG", url: "https://www.kegg.jp/",
      tw: {
        name: "KEGG", manual: "經脈通路圖", star: "天權",
        sub: "京都基因與基因體百科全書・京都大學金久實驗室",
        sections: [
          ["重點摘要", "KEGG 把一串靶點放回細胞裡的通路圖上，回答「這味藥的靶點集中在哪些生物過程、其中有哪些是癌症通路」。平台以超幾何檢定與多重比較校正做富集分析，背景母體取自 KEGG 本身；它是國際上最常用的通路體系，但沒有方向性，商業用途須另取得授權。"],
          ["維運單位", "KEGG（Kyoto Encyclopedia of Genes and Genomes，京都基因與基因體百科全書）由日本京都大學化學研究所生物資訊中心金久實（Minoru Kanehisa）教授的團隊於 1995 年建立，現由金久實驗室持續維護。網站供學術研究免費瀏覽；程式介面限學術使用，商業用途與整批下載需另行取得授權。"],
          ["資料庫簡介", "KEGG 以人工繪製的通路圖，描述細胞內的代謝、訊號傳導、遺傳資訊處理與疾病機制。每條通路有固定編號，例如 hsa04151 是 PI3K-Akt 訊號通路，hsa05200 是 Pathways in cancer；05200 至 05235 是 KEGG 自己歸類的癌症通路。KEGG 另有基因、化合物、藥物與疾病等子資料庫，彼此互相連結。"],
          ["關鍵數字", "1995 年建立。本平台：人類通路 372 條、背景基因 9,423 個；已標準化靶點 1,265 個中有 1,098 個連得上（87%）；癌症通路以 KEGG 編號 05200 至 05235 判定，另列平台自訂核心訊號通路 25 條；多重比較以 Benjamini-Hochberg 法校正，結果依 q 值排序。"],
          ["重要性", "單一的靶點清單只是一串基因名稱；放到通路上，才看得出這些靶點是否集中在某個生物過程。KEGG 是網路藥理學最常用的通路富集分析來源，也是國際期刊最常要求比對的通路體系，讓中藥研究的結果能用國際通行的語言表達，並和其他藥物研究直接比較。"],
          ["可提供的中藥整合資訊", "通路編號、名稱、BRITE 分類、每條通路的背景基因數，以及哪些中藥靶點落在哪些通路上。本平台匯入的人類通路共 372 條、背景基因 9,423 個，並標註是否為癌症相關通路。這些資訊可以回答：某味藥的靶點顯著集中在哪些訊號通路？其中有哪些是癌症通路？命中的是哪幾個基因？"],
          ["本平台介接方式", "UniProt 提供的是 KEGG 的基因識別碼（如 hsa:367），平台再向 KEGG REST 整包取得「基因–通路」對應表，換成通路識別碼。富集分析使用超幾何檢定，並以 Benjamini-Hochberg 法校正多重比較；背景母體取自 KEGG 本身，避免拿自家靶點當母體的循環論證。目前 1,265 個已標準化靶點中有 1,098 個（87%）可連上 KEGG 通路。另有 25 條平台自訂的核心訊號通路（如 MAPK、PI3K-Akt、NF-κB）獨立成清單，那是平台的判斷，不是 KEGG 的分類。"],
          ["研究應用", "通路富集分析回答的是：某味藥的靶點落在某條通路上的數量，是否多於隨機抽樣的預期？研究者通常把顯著的通路畫成氣泡圖或標在通路圖上，作為機轉假說的起點，再設計細胞或動物實驗驗證。在本平台，富集結果會列出命中基因、背景基因數、p 值與 q 值，並註明使用的背景母體；同一組人參靶點換不同母體，顯著比例可能從 59% 變成 15.5%，所以母體一定要和結果一起報告。"],
          ["使用限制與注意", "KEGG 通路沒有方向性，無法告訴我們靶點是被活化還是被抑制。不同通路之間大量重疊，例如人參的凋亡通路與 p53 通路命中的基因大多相同，不能視為兩項獨立發現。另外，歸在癌症大類下的通路不一定代表抗腫瘤機轉，可能只是藥物代謝酶被命中。商業用途須先確認 KEGG 授權。"],
        ],
      },
      en: {
        name: "KEGG", manual: "Chart of Pathway Meridians", star: "Megrez",
        sub: "Kyoto Encyclopedia of Genes and Genomes · Kanehisa Laboratories, Kyoto University",
        sections: [
          ["In brief", "KEGG places a list of targets back onto the cell's pathway maps, answering which biological processes an herb's targets cluster in and which of those are cancer pathways. The platform runs enrichment with the hypergeometric test and multiple-comparison correction against a KEGG background. It is the most widely used pathway system, but it has no direction, and commercial use needs a separate license."],
          ["Maintained by", "KEGG (Kyoto Encyclopedia of Genes and Genomes) was founded in 1995 by Prof. Minoru Kanehisa's team at the Bioinformatics Center, Institute for Chemical Research, Kyoto University, and is maintained by Kanehisa Laboratories. The website is free for academic use; the API is limited to academic use, and commercial use or bulk download requires a separate license."],
          ["About the database", "KEGG uses hand-drawn pathway maps to describe metabolism, signal transduction, genetic information processing and disease mechanisms. Each pathway has a fixed ID — hsa04151 is the PI3K-Akt signaling pathway, hsa05200 is Pathways in cancer, and 05200–05235 are KEGG's own cancer category. KEGG also has linked sub-databases for genes, compounds, drugs and diseases."],
          ["Key figures", "Founded in 1995. On this platform: 372 human pathways with 9,423 background genes; 1,098 of 1,265 standardized targets map to them (87%); cancer pathways are identified by KEGG IDs 05200 to 05235, with a separate list of 25 platform-defined core signaling pathways; multiple comparisons are corrected with Benjamini-Hochberg and results are sorted by q-value."],
          ["Why it matters", "A list of targets is just a string of gene names; mapped onto pathways, it shows whether the targets cluster in a particular biological process. KEGG is the most common source for pathway enrichment in network pharmacology and the pathway system journals most often ask for, so herbal research can be expressed in an internationally shared language and compared directly with other drug studies."],
          ["What it adds to herb integration", "Pathway IDs, names, BRITE categories, background gene counts per pathway, and which herbal targets fall in which pathways. The platform holds 372 human pathways with 9,423 background genes, each flagged as cancer-related or not. These answer: which signaling pathways are an herb's targets significantly enriched in, which of them are cancer pathways, and which genes are hit?"],
          ["How this platform connects", "UniProt supplies KEGG gene IDs (such as hsa:367); the platform downloads KEGG's full gene–pathway table via KEGG REST to convert them to pathway IDs. Enrichment uses the hypergeometric test with Benjamini-Hochberg correction for multiple comparisons, and the background comes from KEGG itself rather than the platform's own targets, which would be circular. 1,098 of the 1,265 standardized targets (87%) map to KEGG pathways. A separate list of 25 platform-defined core signaling pathways (MAPK, PI3K-Akt, NF-κB and others) is the platform's judgment, not a KEGG category."],
          ["Research use", "Pathway enrichment asks whether more of an herb's targets fall in a pathway than random sampling would predict. Researchers usually plot significant pathways as bubble charts or mark them on pathway maps as the starting point for a mechanistic hypothesis, then design cell or animal experiments to test it. On this platform enrichment results list the hit genes, background gene count, p-value and q-value, and state the background population used — for the same set of ginseng targets, changing the background can move the share of significant pathways from 59% to 15.5%, so the background must always be reported with the result."],
          ["Limitations", "KEGG pathways have no direction — they cannot say whether a target is activated or inhibited. Pathways overlap heavily: ginseng's apoptosis and p53 pathway hits are mostly the same genes and are not two independent findings. A pathway filed under cancer does not necessarily mean an anti-tumor mechanism; it may simply be drug-metabolizing enzymes being hit. Commercial use requires confirming the KEGG license first."],
        ],
      },
      ko: {
        name: "KEGG", manual: "경맥통로도", star: "천권",
        sub: "교토 유전자 및 유전체 백과사전 · 교토대학 가네히사 연구실",
        sections: [
          ["한눈에 보기", "KEGG는 표적 목록을 세포의 경로도 위에 다시 올려, 이 약재의 표적이 어떤 생물학적 과정에 모이는지, 그중 암 경로는 무엇인지 답합니다. 플랫폼은 KEGG 자체를 배경으로 초기하 검정과 다중 비교 보정으로 농축 분석을 합니다. 가장 널리 쓰이는 경로 체계이지만 방향성이 없고, 상업적 이용에는 별도 라이선스가 필요합니다."],
          ["운영 기관", "KEGG(Kyoto Encyclopedia of Genes and Genomes)는 1995년 일본 교토대학 화학연구소 생물정보학센터의 가네히사 미노루 교수 연구팀이 만들었으며, 현재 가네히사 연구실이 운영합니다. 웹사이트는 학술 연구에 무료이고, API는 학술 용도로 제한되며, 상업적 이용과 일괄 다운로드는 별도 라이선스가 필요합니다."],
          ["데이터베이스 소개", "KEGG는 사람이 그린 경로도로 세포 내 대사, 신호 전달, 유전 정보 처리, 질병 기전을 나타냅니다. 각 경로에는 고정 번호가 있으며, 예를 들어 hsa04151은 PI3K-Akt 신호 경로, hsa05200은 Pathways in cancer이고 05200~05235는 KEGG 자체의 암 경로 분류입니다. 유전자, 화합물, 약물, 질병 하위 데이터베이스도 서로 연결되어 있습니다."],
          ["핵심 수치", "1995년 설립. 본 플랫폼: 인간 경로 372개, 배경 유전자 9,423개; 표준화된 표적 1,265개 중 1,098개 연결(87%); 암 경로는 KEGG 번호 05200~05235로 판정하고 플랫폼 자체 핵심 신호 경로 25개를 별도 목록으로 둠; 다중 비교는 Benjamini-Hochberg로 보정하고 결과는 q값 순으로 정렬."],
          ["중요성", "표적 목록은 유전자 이름의 나열일 뿐이고, 경로에 올려야 특정 생물학적 과정에 모여 있는지 보입니다. KEGG는 네트워크 약리학에서 가장 많이 쓰이는 경로 농축 분석 출처이자 국제 학술지가 가장 자주 요구하는 경로 체계로, 중약 연구 결과를 국제적으로 통용되는 언어로 표현하고 다른 약물 연구와 직접 비교할 수 있게 합니다."],
          ["중약 통합에 제공하는 정보", "경로 번호, 이름, BRITE 분류, 경로별 배경 유전자 수, 그리고 어떤 중약 표적이 어떤 경로에 속하는지. 플랫폼에는 인간 경로 372개, 배경 유전자 9,423개가 있으며 암 관련 여부를 표시합니다. 이를 통해 약재의 표적이 어떤 신호 경로에 유의하게 모이는지, 그중 암 경로는 무엇인지, 어떤 유전자가 해당되는지 답할 수 있습니다."],
          ["본 플랫폼 연동 방식", "UniProt은 KEGG 유전자 식별자(예: hsa:367)를 제공하고, 플랫폼은 KEGG REST로 '유전자–경로' 대응표 전체를 받아 경로 식별자로 바꿉니다. 농축 분석은 초기하 검정과 Benjamini-Hochberg 다중 비교 보정을 사용하며, 배경 모집단은 KEGG 자체에서 가져와 자체 표적을 모집단으로 쓰는 순환 논증을 피합니다. 표준화된 표적 1,265개 중 1,098개(87%)가 KEGG 경로에 연결됩니다. MAPK, PI3K-Akt, NF-κB 등 플랫폼이 정한 핵심 신호 경로 25개는 별도 목록이며 KEGG의 분류가 아닌 플랫폼의 판단입니다."],
          ["연구 활용", "경로 농축 분석은 '약재의 표적이 어떤 경로에 속하는 수가 무작위로 뽑았을 때의 기대보다 많은가'에 답합니다. 연구자는 보통 유의한 경로를 버블 차트로 그리거나 경로도에 표시해 기전 가설의 출발점으로 삼고, 세포나 동물 실험으로 검증합니다. 본 플랫폼의 농축 결과에는 해당 유전자, 배경 유전자 수, p값과 q값, 사용한 배경 모집단이 표시됩니다. 같은 인삼 표적이라도 모집단을 바꾸면 유의한 비율이 59%에서 15.5%로 달라질 수 있으므로, 모집단은 반드시 결과와 함께 보고해야 합니다."],
          ["사용상 한계", "KEGG 경로에는 방향성이 없어 표적이 활성화되는지 억제되는지 알 수 없습니다. 경로끼리 많이 겹쳐서, 인삼의 세포자멸사 경로와 p53 경로는 해당 유전자가 대부분 같아 두 개의 독립된 발견으로 볼 수 없습니다. 암 분류에 속한 경로라도 항종양 기전을 뜻하지 않을 수 있으며 단지 약물 대사 효소가 해당된 것일 수 있습니다. 상업적 이용은 먼저 KEGG 라이선스를 확인해야 합니다."],
        ],
      },
    },
    {
      key: "Reactome", url: "https://reactome.org/",
      tw: {
        name: "Reactome", manual: "生化反應訣", star: "玉衡",
        sub: "開放的同儕審閱生物路徑知識庫（OICR、NYU Langone、EMBL-EBI、OHSU）",
        sections: [
          ["重點摘要", "Reactome 是完全開放授權的層級式通路資料庫，分類比 KEGG 細約七到八倍，能看到更深一層的反應步驟。平台把它與 KEGG 並行做富集分析、互相印證；靶點覆蓋率 93%，是七個資料庫中通路覆蓋最廣的一個。"],
          ["維運單位", "Reactome 是開放、免費且經同儕審閱的生物路徑知識庫，由加拿大安大略癌症研究所（OICR）、美國紐約大學朗格尼醫學中心（NYU Langone Health）、歐洲生物資訊研究所（EMBL-EBI）與俄勒岡健康與科學大學（OHSU）共同維護。資料以 CC BY 4.0 授權公開，網站、檔案下載與程式介面都可以自由使用。"],
          ["資料庫簡介", "Reactome 把生物過程拆成一個個「反應」，再組成層級式的通路：最上層是訊號傳導、細胞週期、DNA 修復、免疫系統等大類，往下逐層細分到具體的分子反應。每條通路有形如 R-HSA-xxxxxx 的穩定識別碼，每一步都附有原始文獻出處與專家審閱紀錄，可以一路追溯到證據。"],
          ["關鍵數字", "本平台：人類通路 2,867 條（約為 KEGG 的 7.7 倍）、背景蛋白 12,155 個；已標準化靶點 1,265 個中有 1,180 個連得上（93%，覆蓋率高於 KEGG）；識別碼格式為 R-HSA-xxxxxx，可直接由 UniProt 交叉引用取得；授權為 CC BY 4.0，沒有商業使用限制。"],
          ["重要性", "Reactome 的分類比 KEGG 細，人類通路數量約為 KEGG 的七到八倍，能看到更深一層的機轉；它也是完全開放授權的通路資料庫，適合需要商業應用或重新散布的情境。與 KEGG 並行分析可以互相印證：兩邊都顯著的通路，結論比較可靠；只在一邊顯著的，則需要更謹慎解讀。"],
          ["可提供的中藥整合資訊", "通路識別碼、名稱、在層級中的位置與每條通路的背景蛋白數，以及中藥靶點落在哪些反應與通路上。本平台匯入人類通路 2,867 條、背景蛋白 12,155 個。這些資訊可以回答：某味藥的靶點集中在哪些細部的生化反應？它們位在哪一個大類之下？和 KEGG 的結果是否一致？"],
          ["本平台介接方式", "UniProt 紀錄裡的 Reactome 交叉引用本身就是通路識別碼，不需要像 KEGG 那樣再轉換；平台再以官方檔案 UniProt2Reactome_All_Levels 依登錄號取回通路名稱與背景蛋白數。Reactome 與 KEGG 共用同一張通路資料表，以來源欄位區分，富集分析同樣使用超幾何檢定與 Benjamini-Hochberg 校正。目前 1,265 個已標準化靶點中有 1,180 個（93%）連得上 Reactome 通路。"],
          ["研究應用", "Reactome 網站提供線上的通路瀏覽器與分析工具，上傳基因清單後就能看到命中的位置在通路圖上的分布。研究者常用它補足 KEGG 沒有涵蓋的細節，例如某個訊號通路中到底是哪一步反應被命中、上下游分子是誰，進而推敲成分可能的作用環節。在本平台，Reactome 與 KEGG 的富集結果並列呈現，兩邊都顯著的通路值得優先追查。"],
          ["使用限制與注意", "與 KEGG 一樣沒有方向性。通路數量多，多重檢定的負擔也更重；而且因為是層級結構，同一個基因會同時出現在上層與下層通路，閱讀結果時要留意同一批基因被重複計數，避免把同一件事當成多項發現。建議優先看層級較低、較具體的通路，再回頭對照上層的大類。"],
        ],
      },
      en: {
        name: "Reactome", manual: "Secrets of Biochemical Reactions", star: "Alioth",
        sub: "Open, peer-reviewed pathway knowledgebase (OICR, NYU Langone, EMBL-EBI, OHSU)",
        sections: [
          ["In brief", "Reactome is a fully open-licensed, hierarchical pathway database about seven to eight times finer-grained than KEGG, revealing reaction steps one level deeper. The platform runs it alongside KEGG so the two corroborate each other; with 93% target coverage it is the broadest pathway source of the seven databases."],
          ["Maintained by", "Reactome is an open, free, peer-reviewed pathway knowledgebase maintained jointly by the Ontario Institute for Cancer Research (OICR), NYU Langone Health, the European Bioinformatics Institute (EMBL-EBI) and Oregon Health & Science University (OHSU). Its data are released under CC BY 4.0, and the website, downloads and APIs are all free to use."],
          ["About the database", "Reactome breaks biological processes into individual reactions and assembles them into hierarchical pathways: top-level categories such as signal transduction, cell cycle, DNA repair and the immune system are subdivided step by step down to specific molecular reactions. Every pathway has a stable ID of the form R-HSA-xxxxxx, and every step cites its source literature and expert review, so evidence can be traced all the way down."],
          ["Key figures", "On this platform: 2,867 human pathways (about 7.7 times KEGG) with 12,155 background proteins; 1,180 of 1,265 standardized targets map to them (93%, higher coverage than KEGG); IDs take the form R-HSA-xxxxxx and come directly from UniProt cross-references; licensed CC BY 4.0 with no restriction on commercial use."],
          ["Why it matters", "Reactome is finer-grained than KEGG, with roughly seven to eight times as many human pathways, so it reveals mechanisms one level deeper. It is also fully open-licensed, which suits commercial use or redistribution. Running it alongside KEGG lets the two corroborate each other: pathways significant in both are more reliable, while those significant in only one need more careful reading."],
          ["What it adds to herb integration", "Pathway IDs, names, hierarchy positions and background protein counts, and which reactions and pathways herbal targets fall in. The platform holds 2,867 human pathways with 12,155 background proteins. These answer: which detailed biochemical reactions are an herb's targets concentrated in, which top-level category do they belong to, and does this agree with KEGG?"],
          ["How this platform connects", "The Reactome cross-references in UniProt entries are already pathway IDs, so no conversion is needed as with KEGG; the platform uses the official UniProt2Reactome_All_Levels file to fetch pathway names and background counts by accession. Reactome and KEGG share one pathway table distinguished by a source column, and enrichment likewise uses the hypergeometric test with Benjamini-Hochberg correction. 1,180 of the 1,265 standardized targets (93%) map to Reactome pathways."],
          ["Research use", "The Reactome website offers an online pathway browser and analysis tools: upload a gene list and see where the hits fall on the pathway diagrams. Researchers often use it to fill in details KEGG does not cover — exactly which reaction step in a signaling pathway is hit and which molecules sit upstream and downstream — to work out where a component might act. On this platform Reactome and KEGG enrichment results are shown side by side, and pathways significant in both deserve to be followed up first."],
          ["Limitations", "Like KEGG, Reactome has no direction. With many more pathways the multiple-testing burden is heavier, and because it is hierarchical the same gene appears in both parent and child pathways — watch for the same set of genes being counted repeatedly, so one finding is not mistaken for several. It is best to look first at lower-level, more specific pathways and then check their parent categories."],
        ],
      },
      ko: {
        name: "Reactome", manual: "생화반응결", star: "옥형",
        sub: "개방형 동료 검토 생물학 경로 지식베이스 (OICR, NYU Langone, EMBL-EBI, OHSU)",
        sections: [
          ["한눈에 보기", "Reactome은 완전 개방 라이선스의 계층형 경로 데이터베이스로, KEGG보다 분류가 7~8배 세밀하여 한 단계 더 깊은 반응 단계를 볼 수 있습니다. 플랫폼은 KEGG와 병행해 농축 분석을 하여 서로 검증하며, 표적 연결률 93%로 일곱 데이터베이스 중 경로 범위가 가장 넓습니다."],
          ["운영 기관", "Reactome은 개방형·무료·동료 검토 생물학 경로 지식베이스로, 캐나다 온타리오암연구소(OICR), 미국 뉴욕대 랭곤 헬스(NYU Langone Health), 유럽생물정보학연구소(EMBL-EBI), 오리건보건과학대학교(OHSU)가 공동 운영합니다. 데이터는 CC BY 4.0 라이선스로 공개되며 웹사이트, 파일 다운로드, API를 모두 자유롭게 사용할 수 있습니다."],
          ["데이터베이스 소개", "Reactome은 생물학적 과정을 개별 '반응'으로 나눈 뒤 계층형 경로로 구성합니다. 최상위는 신호 전달, 세포 주기, DNA 복구, 면역계 등 대분류이고, 아래로 내려가며 구체적인 분자 반응까지 세분됩니다. 각 경로에는 R-HSA-xxxxxx 형식의 안정적인 식별자가 있고, 모든 단계에 원문헌 출처와 전문가 검토 기록이 있어 근거까지 추적할 수 있습니다."],
          ["핵심 수치", "본 플랫폼: 인간 경로 2,867개(KEGG의 약 7.7배), 배경 단백질 12,155개; 표준화된 표적 1,265개 중 1,180개 연결(93%, KEGG보다 높은 연결률); 식별자 형식은 R-HSA-xxxxxx이며 UniProt 교차 참조에서 바로 얻음; CC BY 4.0 라이선스로 상업적 이용 제한 없음."],
          ["중요성", "Reactome은 KEGG보다 분류가 세밀하여 인간 경로 수가 KEGG의 약 7~8배이며, 한 단계 더 깊은 기전을 볼 수 있습니다. 또한 완전 개방 라이선스여서 상업적 활용이나 재배포가 필요한 경우에 적합합니다. KEGG와 병행 분석하면 서로 검증할 수 있어, 양쪽 모두 유의한 경로는 더 신뢰할 수 있고 한쪽에서만 유의한 경로는 더 신중히 해석해야 합니다."],
          ["중약 통합에 제공하는 정보", "경로 식별자, 이름, 계층 내 위치, 경로별 배경 단백질 수, 그리고 중약 표적이 어떤 반응과 경로에 속하는지. 플랫폼에는 인간 경로 2,867개, 배경 단백질 12,155개가 있습니다. 이를 통해 약재의 표적이 어떤 세부 생화학 반응에 모이는지, 어떤 대분류에 속하는지, KEGG 결과와 일치하는지 답할 수 있습니다."],
          ["본 플랫폼 연동 방식", "UniProt 기록의 Reactome 교차 참조는 그 자체가 경로 식별자여서 KEGG처럼 변환할 필요가 없고, 플랫폼은 공식 파일 UniProt2Reactome_All_Levels로 등록번호별 경로 이름과 배경 단백질 수를 가져옵니다. Reactome과 KEGG는 하나의 경로 테이블을 공유하고 출처 열로 구분하며, 농축 분석도 초기하 검정과 Benjamini-Hochberg 보정을 사용합니다. 표준화된 표적 1,265개 중 1,180개(93%)가 Reactome 경로에 연결됩니다."],
          ["연구 활용", "Reactome 웹사이트는 온라인 경로 브라우저와 분석 도구를 제공하여, 유전자 목록을 올리면 해당 위치가 경로도 어디에 분포하는지 볼 수 있습니다. 연구자는 이를 이용해 KEGG가 다루지 않는 세부 사항, 예를 들어 신호 경로의 어느 반응 단계가 해당되는지, 상류·하류 분자가 무엇인지를 보완하고 성분이 작용할 수 있는 지점을 추론합니다. 본 플랫폼에서는 Reactome과 KEGG의 농축 결과를 나란히 보여 주며, 양쪽 모두 유의한 경로를 우선 추적할 가치가 있습니다."],
          ["사용상 한계", "KEGG와 마찬가지로 방향성이 없습니다. 경로 수가 많아 다중 검정 부담이 더 크고, 계층 구조 때문에 같은 유전자가 상위·하위 경로에 동시에 나타나므로 같은 유전자 집합이 중복 집계되어 하나의 발견이 여러 개로 보이지 않도록 주의해야 합니다. 먼저 하위의 구체적인 경로를 보고, 그다음 상위 대분류와 대조하기를 권합니다."],
        ],
      },
    },
    {
      key: "OncoKB", url: "https://www.oncokb.org/",
      tw: {
        name: "OncoKB", manual: "腫瘤基因秘錄", star: "開陽",
        sub: "美國紀念斯隆凱特琳癌症中心（MSK）精準腫瘤學知識庫",
        sections: [
          ["重點摘要", "OncoKB 是判斷「這個靶點是不是癌症基因」的參考標準，由 MSK 癌症中心維護，部分內容獲 FDA 認可。平台用它的公開癌症基因清單（1,245 個基因）建立暗黑基因模組，從上百個中藥靶點中篩出最值得深入研究的少數基因；但它只代表研究線索，不代表療效。"],
          ["維運單位", "OncoKB 是美國紀念斯隆凱特琳癌症中心（Memorial Sloan Kettering Cancer Center，MSK）建置的精準腫瘤學知識庫，2016 年起公開，由臨床醫師與研究人員組成的團隊持續審閱更新。2021 年部分內容獲美國食品藥物管理局（FDA）認可，是第一個獲此認可的腫瘤突變資料庫。"],
          ["資料庫簡介", "OncoKB 整理癌症相關基因與其突變的生物學效應與臨床意義，並把針對特定突變的治療依證據強度分級（Level 1 至 4，以及抗藥性的 R1、R2）。另外提供公開的癌症基因清單，標註每個基因屬於致癌基因或抑癌基因，以及是否已有 OncoKB 的詳細註解。"],
          ["關鍵數字", "2016 年公開，2021 年部分內容獲 FDA 認可。治療證據等級：Level 1（FDA 核准）、Level 2（標準治療）、Level 3（臨床證據）、Level 4（生物學證據），以及抗藥性的 R1、R2。本平台使用公開癌症基因清單 1,245 個基因；經 UniProt 標準化後，中藥靶點與癌症基因的比對率從 2.6% 提升到 18.0%。"],
          ["重要性", "中藥靶點清單裡往往有上百個基因，哪些和癌症有關？OncoKB 是腫瘤學界公認的參考標準，用它判斷「這個靶點是不是癌症基因」，比自行查文獻更一致，也可以追溯。對以抗腫瘤機轉為目標的研究來說，它是從大量靶點中聚焦的第一道篩網，能把研究資源集中在最值得深入的少數基因上。"],
          ["可提供的中藥整合資訊", "平台使用 OncoKB 公開的癌症基因清單（1,245 個基因），內容包括基因符號、致癌基因或抑癌基因的標註，以及是否有 OncoKB 註解。這些資訊可以回答：某味藥的靶點中，有哪些是公認的癌症基因？它們屬於致癌基因還是抑癌基因？哪幾味藥材共同打到同一個癌症基因？"],
          ["本平台介接方式", "匯入腳本讀入癌症基因清單，建立平台的「暗黑基因」模組。這裡的暗黑基因指受到關注、但仍少被研究的蛋白編碼基因，和基因體中約 98% 的非編碼區（dark genome）是不同的概念。比對的鍵是基因符號，因此必須先完成 UniProt 標準化；模組支援增量更新，並把比對結果回寫到統計數字中，可在暗黑基因相關查詢站查看。"],
          ["研究應用", "研究者常把中藥靶點與 OncoKB 癌症基因取交集，再依致癌基因或抑癌基因分類，推敲中藥成分若影響某個癌症基因的產物，可能對應到哪些腫瘤機轉，作為提出研究假說的起點。在本平台，暗黑基因查詢站可以從癌症基因出發，查回哪些中藥成分與藥材連到這個基因；也可以從人參等藥材出發，看它的靶點中有哪些是癌症基因。"],
          ["使用限制與注意", "平台只使用公開的基因清單，沒有使用需授權的突變層級註解與 API（學術使用可免費申請，商業使用需付費授權）。OncoKB 的證據等級是針對特定突變與已核准藥物，不能延伸解讀成中藥成分的療效；「靶點是癌症基因」只代表這條線索值得進一步研究，而不代表這味藥材能治療該癌症。"],
        ],
      },
      en: {
        name: "OncoKB", manual: "Secret Record of Cancer Genes", star: "Mizar",
        sub: "Precision oncology knowledge base · Memorial Sloan Kettering Cancer Center (MSK)",
        sections: [
          ["In brief", "OncoKB is the reference standard for deciding whether a target is a cancer gene; it is maintained by MSK and partly recognized by the FDA. The platform uses its public cancer gene list (1,245 genes) to build the dark-gene module, narrowing hundreds of herbal targets down to the few genes most worth studying — a research lead, not evidence of efficacy."],
          ["Maintained by", "OncoKB is a precision oncology knowledge base built by Memorial Sloan Kettering Cancer Center (MSK). Public since 2016, it is continuously reviewed and updated by a team of clinicians and researchers. In 2021 parts of it were recognized by the US Food and Drug Administration (FDA), making it the first tumor mutation database to receive such recognition."],
          ["About the database", "OncoKB curates cancer-related genes and the biological effects and clinical significance of their mutations, and ranks treatments for specific mutations by strength of evidence (Levels 1 to 4, plus R1 and R2 for resistance). It also publishes an open cancer gene list noting whether each gene is an oncogene or a tumor suppressor and whether it has detailed OncoKB annotation."],
          ["Key figures", "Public since 2016; parts recognized by the FDA in 2021. Treatment evidence levels: Level 1 (FDA-recognized), Level 2 (standard care), Level 3 (clinical evidence), Level 4 (biological evidence), plus R1 and R2 for resistance. The platform uses the public cancer gene list of 1,245 genes; after UniProt standardization the match rate between herbal targets and cancer genes rose from 2.6% to 18.0%."],
          ["Why it matters", "An herb's target list often contains a hundred or more genes — which ones relate to cancer? OncoKB is a widely accepted reference in oncology; using it to decide whether a target is a cancer gene is more consistent and traceable than ad-hoc literature searches. For research aimed at anti-tumor mechanisms it is the first filter for narrowing many targets down to the few genes most worth pursuing."],
          ["What it adds to herb integration", "The platform uses OncoKB's public cancer gene list (1,245 genes), including gene symbols, oncogene / tumor-suppressor flags and whether each gene is annotated. These answer: which of an herb's targets are recognized cancer genes, are they oncogenes or tumor suppressors, and which herbs share a hit on the same cancer gene?"],
          ["How this platform connects", "An import script reads the cancer gene list into the platform's \"dark gene\" module. Here \"dark genes\" means protein-coding genes that draw interest but remain under-studied — a different concept from the roughly 98% of the genome that is non-coding (the \"dark genome\"). Matching is by gene symbol, so UniProt standardization must come first; the module supports incremental updates, writes match results back into its statistics, and can be explored in the dark-gene query stations."],
          ["Research use", "Researchers often intersect herbal targets with OncoKB cancer genes and sort them into oncogenes and tumor suppressors, reasoning about which tumor mechanisms a component might relate to if it affects a cancer gene's product — a starting point for a research hypothesis. On this platform the dark-gene query station works from a cancer gene back to the herbal components and herbs linked to it, or from an herb such as ginseng to see which of its targets are cancer genes."],
          ["Limitations", "The platform uses only the public gene list, not the licensed mutation-level annotations or API (free on application for academic use, paid license for commercial use). OncoKB evidence levels concern specific mutations and approved drugs and cannot be extended to the efficacy of herbal components; \"the target is a cancer gene\" only means the lead deserves further study, not that the herb treats that cancer."],
        ],
      },
      ko: {
        name: "OncoKB", manual: "종양유전자비록", star: "개양",
        sub: "미국 메모리얼 슬론 케터링 암센터(MSK) 정밀 종양학 지식베이스",
        sections: [
          ["한눈에 보기", "OncoKB는 '이 표적이 암 유전자인가'를 판단하는 기준으로, MSK 암센터가 운영하며 일부 내용이 FDA의 인정을 받았습니다. 플랫폼은 공개 암 유전자 목록(1,245개)으로 다크 유전자 모듈을 만들어 수백 개의 중약 표적 중 가장 깊이 연구할 가치가 있는 소수 유전자를 골라냅니다. 다만 이는 연구 단서일 뿐 효능을 뜻하지 않습니다."],
          ["운영 기관", "OncoKB는 미국 메모리얼 슬론 케터링 암센터(MSK)가 구축한 정밀 종양학 지식베이스로, 2016년부터 공개되어 임상의와 연구자로 이루어진 팀이 계속 검토·갱신합니다. 2021년 일부 내용이 미국 식품의약국(FDA)의 인정을 받아, 이러한 인정을 받은 최초의 종양 돌연변이 데이터베이스가 되었습니다."],
          ["데이터베이스 소개", "OncoKB는 암 관련 유전자와 그 돌연변이의 생물학적 효과 및 임상적 의미를 정리하고, 특정 돌연변이에 대한 치료를 근거 강도에 따라 등급화합니다(Level 1~4, 내성은 R1, R2). 또한 각 유전자가 종양유전자인지 종양억제유전자인지, OncoKB의 상세 주석이 있는지를 표시한 공개 암 유전자 목록을 제공합니다."],
          ["핵심 수치", "2016년 공개, 2021년 일부 내용 FDA 인정. 치료 근거 등급: Level 1(FDA 인정), Level 2(표준 치료), Level 3(임상 근거), Level 4(생물학적 근거), 내성은 R1, R2. 플랫폼은 공개 암 유전자 목록 1,245개를 사용하며, UniProt 표준화 후 중약 표적과 암 유전자의 매칭률이 2.6%에서 18.0%로 높아졌습니다."],
          ["중요성", "중약 표적 목록에는 백 개가 넘는 유전자가 있는 경우가 많은데, 어느 것이 암과 관련될까요? OncoKB는 종양학계에서 널리 인정받는 기준으로, 이를 통해 '이 표적이 암 유전자인가'를 판단하면 개별 문헌 검색보다 일관되고 추적 가능합니다. 항종양 기전을 목표로 하는 연구에서 많은 표적 가운데 가장 깊이 볼 가치가 있는 소수 유전자로 좁히는 첫 번째 거름망입니다."],
          ["중약 통합에 제공하는 정보", "플랫폼은 OncoKB의 공개 암 유전자 목록(1,245개 유전자)을 사용하며, 유전자 기호, 종양유전자·종양억제유전자 표시, 주석 여부를 포함합니다. 이를 통해 약재 표적 중 인정된 암 유전자는 무엇인지, 종양유전자인지 종양억제유전자인지, 어떤 약재들이 같은 암 유전자를 공유하는지 답할 수 있습니다."],
          ["본 플랫폼 연동 방식", "가져오기 스크립트가 암 유전자 목록을 읽어 플랫폼의 '다크 유전자' 모듈을 만듭니다. 여기서 다크 유전자는 관심은 받지만 아직 연구가 적은 단백질 암호화 유전자를 뜻하며, 유전체의 약 98%를 차지하는 비암호화 영역(다크 게놈)과는 다른 개념입니다. 비교 키가 유전자 기호이므로 UniProt 표준화가 먼저 필요하며, 모듈은 증분 업데이트를 지원하고 비교 결과를 통계에 반영하며 다크 유전자 관련 조회에서 볼 수 있습니다."],
          ["연구 활용", "연구자는 흔히 중약 표적과 OncoKB 암 유전자의 교집합을 구한 뒤 종양유전자와 종양억제유전자로 나누어, 성분이 어떤 암 유전자 산물에 영향을 준다면 어떤 종양 기전과 관련될 수 있을지 추론하고 이를 연구 가설의 출발점으로 삼습니다. 본 플랫폼의 다크 유전자 조회에서는 암 유전자에서 출발해 연결된 중약 성분과 약재를 찾거나, 인삼 같은 약재에서 출발해 그 표적 중 암 유전자를 확인할 수 있습니다."],
          ["사용상 한계", "플랫폼은 공개 유전자 목록만 사용하며, 라이선스가 필요한 돌연변이 수준 주석과 API는 사용하지 않습니다(학술 이용은 신청 시 무료, 상업 이용은 유료). OncoKB 근거 등급은 특정 돌연변이와 승인된 약물에 관한 것이므로 중약 성분의 효능으로 확대 해석할 수 없습니다. '표적이 암 유전자'라는 것은 더 연구할 가치가 있는 단서라는 뜻일 뿐, 그 약재가 해당 암을 치료한다는 뜻이 아닙니다."],
        ],
      },
    },
    {
      key: "DepMap", url: "https://depmap.org/",
      tw: {
        name: "DepMap", manual: "細胞依存心法", star: "瑤光",
        sub: "癌症依賴圖譜・美國博德研究所（Broad Institute）",
        sections: [
          ["重點摘要", "DepMap 提供實驗上的外部效度：在上千株腫瘤細胞中逐一剔除基因，看哪些靶點是特定癌別細胞存活所必需。平台用 24Q2 公開版扣除泛必需基因後，找出具選擇性依賴的靶點，作為後續細胞實驗挑選模型與靶點的依據。"],
          ["維運單位", "DepMap（Cancer Dependency Map，癌症依賴圖譜）由美國博德研究所（Broad Institute of MIT and Harvard）主導，並與多個國際夥伴合作，每年定期發布數個版本（例如 24Q2）。公開版資料以 CC BY 4.0 授權釋出，可自由下載使用。"],
          ["資料庫簡介", "DepMap 在上千株人類腫瘤細胞株上，以 CRISPR 基因剔除技術逐一關閉每個基因，再用 Chronos 演算法計算剔除後細胞存活受影響的程度（gene effect，數值越負代表細胞越依賴這個基因）。每株細胞都附有 Oncotree 譜系、原發疾病與亞型等分類，方便依癌別比較。"],
          ["關鍵數字", "本平台使用 24Q2 公開版：細胞株 1,208 株、基因 1,239 個、達門檻的依賴配對 130,865 筆。96 個泛必需基因佔掉 71.1% 的配對，扣除後每個基因平均只在約 2.7% 的細胞株中達門檻，那才是選擇性訊號的量級。人參案例：118 個靶點中 105 個有依賴資料，70 個具選擇性依賴；最強訊號為 BCL2 在 OCI-LY-19 的 −2.62。"],
          ["重要性", "通路分析只能說明靶點「可能參與」哪些過程；DepMap 則提供實驗上的外部效度：這個靶點在哪些腫瘤細胞裡真的是存活所必需？它只在特定癌別中被依賴（選擇性依賴），還是所有細胞都需要（泛必需）？選擇性依賴的靶點，才是抗腫瘤研究值得優先關注的方向。"],
          ["可提供的中藥整合資訊", "細胞株編號（ACH-xxxxxx）、名稱、譜系與疾病類別；每個靶點在每株細胞的依賴強度；跨細胞株的摘要統計（依賴株數、平均值、最強的細胞株）與泛必需基因標記。這些資訊可以回答：某味藥的靶點，在哪些腫瘤細胞株中被選擇性依賴？最強的訊號落在哪一種癌別？"],
          ["本平台介接方式", "平台使用 24Q2 公開版，涵蓋 1,208 株細胞、1,239 個基因、130,865 筆達門檻的依賴配對。匯入腳本讀取 CRISPRGeneEffect 檔案，以 UniProt 標準化後的基因符號精確比對，並先扣除 96 個泛必需基因。結果可在「腫瘤細胞株依賴查詢站」查詢。以人參為例，118 個靶點中有 70 個具選擇性依賴，最強訊號是 BCL2 在 OCI-LY-19 細胞株（成熟 B 細胞腫瘤）的 −2.62。"],
          ["研究應用", "研究者可以用 DepMap 為候選靶點排優先順序：選擇性依賴越強、依賴的細胞株越集中在某一癌別，就越適合作為後續細胞實驗的模型與靶點。例如發現某中藥成分打到的靶點只在特定淋巴瘤細胞株中被強烈依賴，就可以優先挑選那幾株細胞做體外測試，節省實驗成本。在本平台，腫瘤細胞株依賴查詢站可以依靶點查看依賴的細胞株、譜系與依賴強度。"],
          ["使用限制與注意", "DepMap 量測的是「剔除這個基因會怎樣」，不是「使用這個化合物會怎樣」，因此不能直接推論中藥成分的細胞毒性或藥效；細胞株也不等於病人。藥物敏感性資料庫 GDSC 因使用條款禁止轉售與商業服務，平台不予納入。解讀依賴性結果時，請一併確認該基因不是泛必需基因。"],
        ],
      },
      en: {
        name: "DepMap", manual: "Art of Cell Dependency", star: "Alkaid",
        sub: "Cancer Dependency Map · Broad Institute",
        sections: [
          ["In brief", "DepMap adds experimental external validity: by knocking out genes one at a time in over a thousand tumor cell lines, it shows which targets specific cancer types need to survive. Using the 24Q2 public release with common-essential genes removed, the platform finds targets with selective dependency to guide the choice of models and targets for follow-up cell experiments."],
          ["Maintained by", "DepMap (the Cancer Dependency Map) is led by the Broad Institute of MIT and Harvard together with international partners, with several releases each year (for example 24Q2). The public release is published under CC BY 4.0 and can be freely downloaded and used."],
          ["About the database", "Across more than a thousand human tumor cell lines, DepMap switches off each gene one at a time with CRISPR knockout and uses the Chronos algorithm to estimate how much cell survival is affected (the gene effect — the more negative, the more the cells depend on that gene). Each cell line is annotated with its Oncotree lineage, primary disease and subtype for comparison across cancer types."],
          ["Key figures", "The platform uses the 24Q2 public release: 1,208 cell lines, 1,239 genes and 130,865 dependency pairs above threshold. 96 common-essential genes take up 71.1% of the pairs; after removing them, each gene reaches the threshold in only about 2.7% of cell lines on average — the true scale of a selective signal. Ginseng: 105 of 118 targets have dependency data and 70 show selective dependency; the strongest signal is BCL2 at −2.62 in OCI-LY-19."],
          ["Why it matters", "Pathway analysis can only say a target may take part in a process; DepMap adds experimental external validity: in which tumor cells is this target actually required for survival? Is it needed only in particular cancer types (a selective dependency) or by every cell (common essential)? Selective dependencies are the ones anti-tumor research should look at first."],
          ["What it adds to herb integration", "Cell-line IDs (ACH-xxxxxx), names, lineages and disease categories; the dependency strength of each target in each cell line; cross-line summaries (number of dependent lines, mean, strongest line) and common-essential flags. These answer: in which tumor cell lines are an herb's targets selectively depended on, and in which cancer type is the strongest signal?"],
          ["How this platform connects", "The platform uses the 24Q2 public release: 1,208 cell lines, 1,239 genes and 130,865 dependency pairs above threshold. An import script reads the CRISPRGeneEffect file, matches exactly on UniProt-standardized gene symbols and first removes 96 common-essential genes. Results are in the tumor cell-line dependency query station. For ginseng, 70 of 118 targets show selective dependency; the strongest signal is BCL2 at −2.62 in the OCI-LY-19 cell line (mature B-cell neoplasm)."],
          ["Research use", "Researchers can use DepMap to rank candidate targets: the stronger the selective dependency and the more the dependent lines concentrate in one cancer type, the better suited the target and those cell models are for follow-up experiments. If a target hit by an herbal component is strongly depended on only in certain lymphoma cell lines, for example, those lines can be chosen first for in-vitro testing, saving experimental cost. On this platform the tumor cell-line dependency query station shows, for each target, the dependent cell lines, their lineages and the dependency strength."],
          ["Limitations", "DepMap measures what happens when a gene is knocked out, not what happens when a compound is applied, so it cannot directly tell us the cytotoxicity or efficacy of herbal components — and cell lines are not patients. The drug-sensitivity database GDSC is not included because its terms forbid resale and commercial services. When reading dependency results, always check that the gene is not common-essential."],
        ],
      },
      ko: {
        name: "DepMap", manual: "세포의존심법", star: "요광",
        sub: "암 의존성 지도 · 미국 브로드연구소(Broad Institute)",
        sections: [
          ["한눈에 보기", "DepMap은 실험적 외적 타당성을 제공합니다. 천여 종의 종양 세포주에서 유전자를 하나씩 제거해 어떤 표적이 특정 암종 세포의 생존에 필수인지 보여 줍니다. 플랫폼은 24Q2 공개판에서 범필수 유전자를 제외한 뒤 선택적 의존을 보이는 표적을 찾아, 후속 세포 실험의 모델과 표적 선정 근거로 삼습니다."],
          ["운영 기관", "DepMap(Cancer Dependency Map, 암 의존성 지도)은 미국 브로드연구소(Broad Institute of MIT and Harvard)가 주도하고 여러 국제 파트너와 협력하며, 매년 여러 차례 버전(예: 24Q2)을 발표합니다. 공개판 데이터는 CC BY 4.0 라이선스로 배포되어 자유롭게 내려받아 사용할 수 있습니다."],
          ["데이터베이스 소개", "DepMap은 천여 종의 인간 종양 세포주에서 CRISPR 유전자 녹아웃으로 유전자를 하나씩 끄고, Chronos 알고리즘으로 세포 생존이 받는 영향(gene effect, 음수가 클수록 세포가 그 유전자에 더 의존)을 계산합니다. 각 세포주에는 Oncotree 계통, 원발 질환, 아형 등의 분류가 있어 암종별로 비교할 수 있습니다."],
          ["핵심 수치", "플랫폼은 24Q2 공개판을 사용합니다: 세포주 1,208개, 유전자 1,239개, 기준을 넘는 의존 쌍 130,865건. 범필수 유전자 96개가 쌍의 71.1%를 차지하며, 이를 제외하면 유전자 하나가 기준에 도달하는 세포주는 평균 약 2.7%에 불과한데, 그것이 선택적 신호의 실제 규모입니다. 인삼 사례: 표적 118개 중 105개에 의존 데이터가 있고 70개가 선택적 의존을 보이며, 가장 강한 신호는 OCI-LY-19의 BCL2 −2.62입니다."],
          ["중요성", "경로 분석은 표적이 어떤 과정에 '관여할 수 있다'는 것만 말해 줍니다. DepMap은 실험적 외적 타당성을 더합니다. 이 표적이 어떤 종양 세포에서 실제로 생존에 필수인지, 특정 암종에서만 의존되는지(선택적 의존) 아니면 모든 세포에 필요한지(범필수)를 알려 줍니다. 선택적으로 의존되는 표적이 항종양 연구에서 우선 살펴볼 방향입니다."],
          ["중약 통합에 제공하는 정보", "세포주 번호(ACH-xxxxxx), 이름, 계통과 질환 분류; 각 표적의 세포주별 의존 강도; 세포주 전체 요약(의존 세포주 수, 평균, 가장 강한 세포주)과 범필수 유전자 표시. 이를 통해 약재의 표적이 어떤 종양 세포주에서 선택적으로 의존되는지, 가장 강한 신호가 어떤 암종에 있는지 답할 수 있습니다."],
          ["본 플랫폼 연동 방식", "플랫폼은 24Q2 공개판을 사용하며 세포주 1,208개, 유전자 1,239개, 기준을 넘는 의존 쌍 130,865건을 포함합니다. 가져오기 스크립트는 CRISPRGeneEffect 파일을 읽어 UniProt으로 표준화한 유전자 기호와 정확히 비교하고, 먼저 범필수 유전자 96개를 제외합니다. 결과는 '종양 세포주 의존성 조회'에서 볼 수 있습니다. 인삼의 경우 표적 118개 중 70개가 선택적 의존을 보였고, 가장 강한 신호는 OCI-LY-19 세포주(성숙 B세포 종양)의 BCL2 −2.62입니다."],
          ["연구 활용", "연구자는 DepMap으로 후보 표적의 우선순위를 정할 수 있습니다. 선택적 의존이 강하고 의존 세포주가 특정 암종에 집중될수록 후속 세포 실험의 모델과 표적으로 적합합니다. 예를 들어 중약 성분의 표적이 특정 림프종 세포주에서만 강하게 의존된다면, 그 세포주를 먼저 골라 시험관 실험을 하여 비용을 아낄 수 있습니다. 본 플랫폼의 '종양 세포주 의존성 조회'에서는 표적별로 의존 세포주, 계통, 의존 강도를 볼 수 있습니다."],
          ["사용상 한계", "DepMap은 '이 유전자를 제거하면 어떻게 되는가'를 측정할 뿐 '이 화합물을 쓰면 어떻게 되는가'가 아니므로, 중약 성분의 세포 독성이나 약효를 직접 추론할 수 없으며 세포주는 환자와 같지 않습니다. 약물 감수성 데이터베이스 GDSC는 이용 약관이 재판매와 상업 서비스를 금지하여 포함하지 않았습니다. 의존성 결과를 해석할 때는 해당 유전자가 범필수 유전자가 아닌지 함께 확인하세요."],
        ],
      },
    },
  ];

  const herbs = {
    url: null,
    tw: {
      name: "502 種中藥", manual: "", star: "", sub: "藥草花園・TCMSP 收錄、平台上架的藥材",
      sections: [
        ["收錄範圍", "平台收錄 TCMSP 的 502 種中藥材，花園裡的每一朵花草代表一味藥材。每味藥材都連到它的化學成分、作用靶點與相關疾病，疾病並標註是否屬於腫瘤。"],
        ["人參示範案例", "人參是平台的示範案例：190 種成分中有 22 種通過活性篩選（OB ≥ 30%、DL ≥ 0.18），連到 118 個靶點；經 UniProt 標準化與 DepMap 比對後，有 70 個靶點在特定腫瘤細胞株中呈現選擇性依賴。"],
        ["怎麼查", "登入後可在「TCMSP 藥材關聯查詢站」查詢任何一味藥材，查看成分、靶點、疾病與關聯圖；也可以從疾病關聯查詢站反向查回藥材。"],
        ["閱讀提醒", "「藥材的靶點連到某種腫瘤」只代表分子層級的關聯，不代表這味藥對該腫瘤有效。所有結果都需要實驗與臨床研究進一步驗證。"],
      ],
    },
    en: {
      name: "502 herbs", manual: "", star: "", sub: "Herb garden · herbs indexed in TCMSP and available on this platform",
      sections: [
        ["Coverage", "The platform holds 502 herbs from TCMSP; each flower in the garden stands for one herb. Every herb links to its chemical components, targets and related diseases, and diseases are flagged as tumor or non-tumor."],
        ["Ginseng showcase", "Ginseng is the platform's showcase: 22 of its 190 components pass the activity screen (OB ≥ 30%, DL ≥ 0.18) and link to 118 targets; after UniProt standardization and DepMap matching, 70 targets show selective dependency in specific tumor cell lines."],
        ["How to search", "After signing in, look up any herb in the TCMSP herb query station to see its components, targets, diseases and network graph, or work backwards from a disease in the disease query station."],
        ["Reading note", "\"An herb's target links to a tumor\" is only a molecular-level association, not evidence that the herb works against that tumor. All results need further experimental and clinical validation."],
      ],
    },
    ko: {
      name: "502종 중약", manual: "", star: "", sub: "약초 정원 · TCMSP에 수록되어 플랫폼에 등록된 약재",
      sections: [
        ["수록 범위", "플랫폼은 TCMSP의 중약재 502종을 수록하며, 정원의 꽃과 풀 하나하나가 약재 하나를 나타냅니다. 각 약재는 화학 성분, 작용 표적, 관련 질병과 연결되고, 질병에는 종양 여부가 표시됩니다."],
        ["인삼 시범 사례", "인삼은 플랫폼의 시범 사례입니다. 190개 성분 중 22개가 활성 선별(OB ≥ 30%, DL ≥ 0.18)을 통과해 118개 표적과 연결되며, UniProt 표준화와 DepMap 비교 후 70개 표적이 특정 종양 세포주에서 선택적 의존을 보입니다."],
        ["조회 방법", "로그인 후 'TCMSP 약재 연관 조회'에서 어떤 약재든 성분, 표적, 질병, 관계도를 볼 수 있고, '질병 연관 조회'에서 질병으로부터 약재를 역으로 찾을 수도 있습니다."],
        ["해석 주의", "'약재의 표적이 어떤 종양과 연결된다'는 것은 분자 수준의 연관일 뿐, 그 약재가 해당 종양에 효과가 있다는 뜻이 아닙니다. 모든 결과는 추가 실험과 임상 연구로 검증해야 합니다."],
      ],
    },
  };

  const wizard = {
    url: null, email: "steer425@gmail.com",
    tw: {
      name: "煉蠱巫師", manual: "", star: "", sub: "花園的守園人・本站維護者 Steer 的化身",
      sections: [
        ["我是誰", "我在花園裡彎腰採藥、搗藥、提煉，再把精華化成花瓣灑回花園——就像平台把 502 味中藥拆解、比對、整合成研究線索。"],
        ["本站維護", "本站台由 Steer 進行維護。"],
        ["聯絡方式", "若有相關建議、資料錯誤回報或合作洽詢，歡迎來信："],
        ["小提醒", "本平台為科研輔助工具，不作為醫療診斷或治療建議。"],
      ],
    },
    en: {
      name: "Gu-brewing Wizard", manual: "", star: "", sub: "Keeper of the garden · the avatar of Steer, who maintains this site",
      sections: [
        ["Who am I", "I bend down to gather herbs, grind them, refine them, and scatter the essence back over the garden as petals — just as the platform breaks down, matches and integrates 502 herbs into research leads."],
        ["Site maintenance", "This site is maintained by Steer."],
        ["Contact", "For suggestions, data error reports or collaboration inquiries, please write to:"],
        ["Note", "This platform is a research-support tool, not for medical diagnosis or treatment advice."],
      ],
    },
    ko: {
      name: "고(蠱)를 빚는 마법사", manual: "", star: "", sub: "정원지기 · 사이트 관리자 Steer의 분신",
      sections: [
        ["나는 누구인가", "나는 정원에서 허리를 굽혀 약초를 캐고, 빻고, 정제한 뒤 그 정수를 꽃잎으로 바꿔 정원에 다시 뿌립니다. 플랫폼이 502종 중약을 분해·비교·통합해 연구 단서로 만드는 것처럼요."],
        ["사이트 관리", "이 사이트는 Steer가 관리합니다."],
        ["연락처", "제안, 데이터 오류 신고, 협업 문의는 다음 주소로 메일 주세요:"],
        ["참고", "본 플랫폼은 연구 보조 도구이며, 의료 진단이나 치료 권고로 사용되지 않습니다."],
      ],
    },
  };

  // 依目前介面語言取出一份內容；cn 由繁中經 OpenCC 轉換
  function pick(entry) {
    const lang = window.loginLang || "tw";
    if (lang === "en" || lang === "ko") return Object.assign({ url: entry.url, email: entry.email }, entry[lang]);
    const tw = entry.tw, t = (s) => (window.loginT ? window.loginT(s) : s);
    return { url: entry.url, email: entry.email, name: t(tw.name), manual: tw.manual ? t(tw.manual) : "", star: tw.star ? t(tw.star) : "",
      sub: t(tw.sub), sections: tw.sections.map(([k, v]) => [t(k), t(v)]) };
  }
  return { db, herbs, wizard, pick };
})();
