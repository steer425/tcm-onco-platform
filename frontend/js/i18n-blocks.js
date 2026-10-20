// 段落翻譯字典（v1.50.0）。機制見 frontend/js/site-lang.js 檔頭「段落翻譯」。
//
// - key 是元素 [data-i18n-block] 的「整段文字」（textContent）。比對前兩邊都會正規化：
//   連續空白縮成一個、中文字與全形標點旁的空白拿掉，所以 key 可以照畫面上的句子寫，不用管原始碼的換行。
// - value 是翻好的 **HTML**，會整段換掉 innerHTML。粗體、<code>、class 要自己保留。
//   這裡的 HTML 是我們自己寫的靜態內容；佔位 {0}、{1} 填回的實際文字會先跳脫（可能來自資料庫）。
// - 帶數字的句子用 {0}、{1}… 佔位；同一個編號在 key 與 value 裡代表同一個值。
// - en 與 ko 的 key 必須一模一樣、佔位編號也要一致——tests/test_i18n_blocks.js 會檢查。
// - 原文改了一個字，這一段就會比對不到、退回顯示中文（不會壞掉，只是沒翻）。改原文時記得同步改這裡。
//
// 目前涵蓋：藥材活性成分（F1-7）、通路富集（F1-5）、腫瘤細胞株依賴（F1-8）。

(function () {
  // ---------------------------------------------------------------- 共用片段
  const DISCLAIMER = "本平台為科研輔助工具，所有結果為公開資料庫的統計關聯，不作為醫療診斷或治療建議。";

  const en = {
    // ============================================================ 藥材活性成分（herb-ingredients）
    "先用OB（口服生物利用度）與DL（類藥性）兩道門檻篩出這味藥材的活性成分，再逐一顯示每個成分有沒有成功對應到PubChem的化學結構。後續的靶點、通路與細胞株分析都只使用這些活性成分，不是全部成分。沒通過門檻的成分可切換到「非活性成分」查看，並標示是哪一道門檻沒過。":
      "The herb's active ingredients are first selected with two thresholds, <b>OB (oral bioavailability)</b> and <b>DL (drug-likeness)</b>; each ingredient is then checked for a successful match to a PubChem chemical structure. Downstream target, pathway and cell-line analyses <b>use only these active ingredients</b>, not all ingredients. Ingredients that fail a threshold are listed under “Inactive Ingredients”, with the threshold they failed.",
    "怎麼讀這一頁：「已標準化」只算自動採用與已確認兩種狀態——待確認是還沒審過的候選，拿它當成果會高估。分子量差欄位若標示「疑似苷元誤配」，代表名稱雖然對上、但查到的很可能是帶糖基的另一個分子，這種一律要人工判斷，不可直接採用。":
      "<b>How to read this page:</b> “Standardised” counts only the <b>auto-accepted</b> and <b>confirmed</b> statuses — “pending” entries are unreviewed candidates, and counting them as results would overstate coverage. When the MW-difference column says “possible aglycone mismatch”, the name matched but the record found is most likely <b>a different molecule carrying sugar groups</b>; such entries always need manual review and must not be accepted as-is.",
    "名稱來源：成分名稱為TCMSP的英文原名；「IUPAC系統名稱」來自PubChem，只有已對應到CID的成分才有。化合物沒有拉丁文名稱（拉丁學名是給藥材物種用的），化合物的國際標準命名就是IUPAC系統名稱。資料庫沒有中文名稱與化學分類欄位，本頁因此不提供。":
      "<b>Name sources:</b> ingredient names are TCMSP's original English names; the “IUPAC systematic name” comes from PubChem and exists only for ingredients matched to a CID. Compounds have no Latin names (Latin binomials apply to the herb's species); the international standard name for a compound is its IUPAC systematic name. The database has <b>no Chinese-name or chemical-class field</b>, so this page does not show them.",
    "非活性成分：上方的「已標準化、有SMILES」等數字只算活性成分；非活性成分另列在「非活性成分」分頁，不進入後續的靶點、通路與細胞株分析。":
      "<b>Inactive ingredients:</b> the figures above (“Standardised”, “With SMILES”, etc.) <b>count active ingredients only</b>; inactive ingredients are listed separately on the “Inactive Ingredients” tab and are not used in the downstream target, pathway and cell-line analyses.",
    "目前這味藥材還有{0}個活性成分尚未完成標準化。":
      "<b>{0}</b> active ingredient(s) of this herb have not been standardised yet.",
    "這味藥材的活性成分已全部完成標準化。":
      "All active ingredients of this herb have been standardised.",
    [DISCLAIMER]:
      "This platform is a research-support tool. All results are statistical associations from public databases and <b>are not medical diagnosis or treatment advice</b>.",

    // 欄位說明視窗（標題與內文各是一個段落）
    "Mol ID（TCMSP成分編號）": "Mol ID (TCMSP ingredient ID)",
    "TCMSP自己發給每個成分的編號，格式是MOL加6碼數字（例如MOL000098）。它只在TCMSP這一套系統裡有意義——拿Mol ID去PubChem、UniProt或任何其他資料庫都查不到東西，也沒有化學結構的資訊在裡面。正因為如此，本平台才要做「成分標準化」，把每個Mol ID對應到下面那三個國際通用的編號。點編號可到中藥關聯查詢站看這個成分的靶點與疾病關聯。":
      "TCMSP's own ID for each ingredient: “MOL” followed by six digits (e.g. MOL000098). It only means something inside TCMSP — searching PubChem, UniProt or any other database for a Mol ID returns nothing, and it carries no structural information. That is exactly why this platform performs ingredient standardisation: mapping every Mol ID to the three internationally used identifiers below. Click an ID to see the ingredient's targets and disease links in the TCM Association Explorer.",
    "PubChem CID — PubChem Compound ID（化合物編號）": "PubChem CID — PubChem Compound ID",
    "美國國家生物技術資訊中心（NCBI）旗下PubChem資料庫發給每個化合物的編號，是一串純數字。這是國際通用的編號，拿著它可以到PubChem查到分子結構、物化性質、生物活性試驗與文獻。本頁的CID是由成分名稱比對後對應過來的，狀態要是「自動採用」或「已確認」才算數。":
      "A purely numeric ID assigned to each compound by PubChem, run by the US National Center for Biotechnology Information (NCBI). It is used internationally; with it you can look up the structure, physicochemical properties, bioassays and literature on PubChem. The CIDs on this page were mapped by matching ingredient names, and only count when the status is “auto-accepted” or “confirmed”.",
    "InChIKey — International Chemical Identifier Key（國際化學標識符雜湊碼）": "InChIKey — International Chemical Identifier Key",
    "由IUPAC（國際純化學暨應用化學聯合會）制定，直接從分子結構算出來的27碼固定長度指紋，格式是14碼-10碼-1碼。它不是誰發的號碼，而是結構的計算結果，所以同一個分子在任何資料庫算出來都一樣，是跨資料庫比對最可靠的鍵值，也可以直接丟進Google搜尋。":
      "A fixed-length, 27-character fingerprint computed directly from the molecular structure, defined by IUPAC (International Union of Pure and Applied Chemistry), in the form 14-10-1 characters. It is not an assigned number but the result of a calculation on the structure, so the same molecule yields the same key in every database — the most reliable key for cross-database matching. You can also paste it straight into Google.",
    "SMILES — Simplified Molecular Input Line Entry System（簡化分子線性輸入規範）": "SMILES — Simplified Molecular Input Line Entry System",
    "用一行文字描述分子結構的寫法：原子用元素符號（C、N、O…），單鍵省略、雙鍵寫=、三鍵寫#，括號表示分支，數字表示環的開合。例如乙醇是CCO，苯是c1ccccc1（小寫代表芳香環）。有了SMILES，就能把分子畫出來、算物化性質、做結構相似性比對與分子對接，是後續結構分析與AI模型的輸入格式。同一個分子可以有好幾種寫法，所以跨資料庫比對請用InChIKey，不要直接比SMILES字串。本欄✓表示這個成分已從PubChem取得SMILES（只算標準化狀態為「自動採用」或「已確認」的那一筆）；✗表示尚未對應到結構。點PubChem CID可以看到完整的SMILES與結構圖。":
      "A one-line text notation for molecular structure: atoms are element symbols (C, N, O…), single bonds are implied, double bonds are written =, triple bonds #, parentheses mark branches and digits open and close rings. Ethanol is CCO; benzene is c1ccccc1 (lower case marks an aromatic ring).\n\nWith SMILES you can draw the molecule, compute properties, run structural-similarity searches and docking — it is the input format for later structural analysis and AI models. The same molecule can be written several ways, so use the InChIKey for cross-database matching, not raw SMILES strings.\n\n✓ in this column means a SMILES was obtained from PubChem for the ingredient (counting only the record whose status is “auto-accepted” or “confirmed”); ✗ means no structure has been matched yet. Click the PubChem CID to see the full SMILES and structure drawing.",
    "IUPAC系統名稱— IUPAC Systematic Name": "IUPAC Systematic Name",
    "由IUPAC（國際純化學暨應用化學聯合會）規則從分子結構推導出來的標準化學名稱，全世界通用，看名稱就能還原出結構。關於「拉丁文名稱」：拉丁學名是給生物物種用的（例如藥材人參的學名Panax ginseng C. A. Mey.），化合物本身沒有拉丁文名稱；化合物的國際標準命名就是這個IUPAC系統名稱。資料來自PubChem，只有已對應到PubChem CID的成分才有。天然物（皂苷、多醣類）的系統名稱常常很長，表格只顯示前三行，滑鼠移上去可看全文。":
      "The standard chemical name derived from the molecular structure by IUPAC (International Union of Pure and Applied Chemistry) rules. It is used worldwide, and the structure can be reconstructed from the name.\n\nAbout “Latin names”: Latin binomials are for biological species (e.g. ginseng is Panax ginseng C. A. Mey.); compounds themselves have no Latin name — their international standard name is this IUPAC systematic name.\n\nThe data come from PubChem and exist only for ingredients matched to a PubChem CID. Systematic names of natural products (saponins, polysaccharides) are often very long; the table shows the first three lines — hover to read the full name.",
    "未納入原因": "Exclusion Reason",
    "這個成分沒有被列為活性成分的原因：・OB未達：口服生物利用度低於門檻，吃下去大多吸收不到。・DL未達：類藥性低於門檻，結構不像一般藥物分子。・OB、DL皆未達：兩道門檻都沒過。・ADME缺值：TCMSP沒有這個成分的OB或DL數值，無法判定，一律排除（不是因為數值低）。門檻值顯示在頁面上方，由管理者在系統設定調整。非活性成分不進入後續的靶點、通路與細胞株分析，但其中有些可能經腸道菌代謝後才轉為活性形式，研究上仍可參考。":
      "Why this ingredient is not counted as active:\n・OB below threshold: oral bioavailability is below the threshold — little of it is absorbed when taken orally.\n・DL below threshold: drug-likeness is below the threshold — the structure does not resemble typical drug molecules.\n・OB & DL below threshold: fails both thresholds.\n・ADME missing: TCMSP has no OB or DL value for this ingredient, so it cannot be assessed and is always excluded (not because the value is low).\n\nThe thresholds are shown at the top of the page and set by an administrator in System Settings. Inactive ingredients are not used in the downstream target, pathway and cell-line analyses, though some may become active only after gut-microbial metabolism and can still be of research interest.",
    "CAS號— CAS Registry Number（化學文摘社登記號）": "CAS Registry Number",
    "美國化學文摘社（Chemical Abstracts Service，隸屬美國化學會）發給每一個已登錄物質的編號，格式是「數字-數字-檢查碼」（例如50-00-0）。化工、法規、安全資料表（SDS）與採購上最常用這個編號，要跟法規清單或試劑供應商對照時，CAS號通常比CID更通用。它是商業資料庫，並非所有化合物都有登錄號。":
      "The number assigned to every registered substance by the Chemical Abstracts Service (a division of the American Chemical Society), in the form “digits-digits-check digit” (e.g. 50-00-0). It is the identifier most used in the chemical industry, regulation, safety data sheets (SDS) and purchasing; when matching against regulatory lists or reagent suppliers, a CAS number is usually more widely accepted than a CID. CAS is a commercial registry, and not every compound has a number.",

    // ============================================================ 腫瘤細胞株依賴（tumor-cells）
    "藥材的活性成分→靶點→哪些靶點是特定腫瘤細胞株的選擇性依賴（DepMap CRISPR篩選）。先排除泛必需基因（命中它們是細胞毒性，不是抗腫瘤機轉），再以選擇性當門檻、效應量當排序。每一列都是一個可以被否證的驗證方案起點：具體基因、具體細胞株、具體癌別。":
      "Herb active ingredients → targets → <b>which targets are selective dependencies of specific tumour cell lines</b> (DepMap CRISPR screens). <b>Common-essential genes</b> are excluded first (hitting them is cytotoxicity, not an anti-tumour mechanism); then <b>selectivity is the threshold and effect size the ranking</b>. Each row is the starting point of a falsifiable validation plan: a specific gene, a specific cell line, a specific cancer type.",
    "有依賴：gene effect ≤ {0}；強依賴：≤ {1}。換了門檻，數字的意義就不同，兩次結果不能直接比較。":
      "Dependent: gene effect ≤ {0}; strongly dependent: ≤ {1}. Changing the thresholds changes what the numbers mean, so results from different thresholds are not directly comparable.",
    "選擇性靶點（{0}）": "Selective targets ({0})",
    "被門檻刷掉（{0}）": "Filtered out ({0})",
    "泛必需（已排除）（{0}）": "Common essential (excluded) ({0})",
    "排序：通過選擇性門檻後，依最強效應由強到弱（不是依株數——株數多代表廣度，不是選擇性）。":
      "Ranking: after passing the selectivity threshold, by <b>strongest effect</b>, strongest first (not by number of lines — many lines means breadth, not selectivity).",
    "這些不是沒有訊號，而是訊號不具選擇性——在很多細胞株都依賴的基因，抑制它比較像細胞毒性而不是機轉。要看它們可以放寬上方的門檻。":
      "These are not signal-free — their signal is <b>not selective</b>. Inhibiting a gene that many cell lines depend on looks more like cytotoxicity than a mechanism. Relax the threshold above to include them.",
    "這些基因在幾乎每一株細胞都是存活必需。任何有細胞毒性的物質都會「命中」它們，所以不能拿來當抗腫瘤機轉的證據。":
      "These genes are essential for survival in almost every cell line. Anything cytotoxic will “hit” them, so they <b>cannot</b> be used as evidence of an anti-tumour mechanism.",
    "這張表不是「這味藥能治這些癌」。它說的是：這味藥材的活性成分在TCMSP被註記為作用於這些靶點，而這些靶點在那些細胞株是選擇性依賴。兩件事之間還缺實際的結合與活性驗證—— TCMSP的成分–靶點關係有相當比例是對接預測，不是實測結合，目前尚未分層。":
      "<b>This table does not say “this herb treats these cancers”.</b> It says: this herb's active ingredients are annotated in TCMSP as acting on these targets, and these targets are selective dependencies of those cell lines. Between the two, actual binding and activity validation is still missing — <b>a substantial share of TCMSP ingredient–target links are docking predictions, not measured binding</b>, and they have not yet been tiered.",
    "⚠️方向性：CRISPR依賴量的是「移除這個基因，細胞會不會死」，要轉成治療假說，前提是化合物抑制該靶點；TCMSP不記錄作用方向。":
      "<b>⚠️ Direction:</b> CRISPR dependency measures “does the cell die when this gene is <b>removed</b>”. Turning it into a therapeutic hypothesis requires the compound to <b>inhibit</b> the target; TCMSP does not record the direction of action.",
    "本表有{0}個標為「受體」——核受體與配體門控受體的天然配體通常是活化劑，方向反了效果可能相反。":
      "<b>{0}</b> target(s) in this table are flagged “receptor” — natural ligands of nuclear and ligand-gated receptors are usually activators, so the effect may be the opposite.",
    "受體標記是啟發式的，只用來提醒；沒被標記也不代表方向沒問題。":
      "The receptor flag is heuristic and only a reminder; no flag does not mean the direction is fine.",
    "強依賴株數為「—」的列請當成雜訊看待：只在少數細胞、效應剛越過門檻的配對，在這個規模的矩陣裡本來就會隨機出現。":
      "<b>Treat rows with “—” strongly dependent lines as noise:</b> pairs seen in only a few lines with effects just past the threshold occur by chance in a matrix of this size.",
    "CRISPR敲除≠化合物抑制；DepMap只有腫瘤細胞株，這裡的「選擇性」是腫瘤株之間的比較，不是腫瘤vs正常細胞。":
      "<b>CRISPR knockout ≠ compound inhibition</b>; DepMap contains only tumour cell lines, so “selectivity” here compares tumour lines with each other, not tumour vs normal cells.",
    "本頁不提供lineage（癌別）富集：以人參為例，該富集經對照基因集檢定後落在隨機範圍內，不能解讀為這味藥材的特性。":
      "This page does not show lineage (cancer-type) enrichment: for ginseng, that enrichment fell within the random range when tested against control gene sets, so it cannot be read as a property of the herb.",
    "這株細胞依賴、而且是「{0}」選擇性靶點的基因（{1}個），依這株的效應由強到弱：":
      "Genes this cell line depends on that are selective targets of “{0}” ({1}), by effect in this line, strongest first:",

    // ============================================================ 通路富集（pathways）
    "分析鏈路的第四站：中藥→成分→靶點→通路。靶點標準化（F1-4）解析UniProt時已經順手把每個靶點的KEGG基因編號與Reactome通路編號存下來，所以這裡不必再跑一輪外部解析，只需要向KEGG／Reactome要通路目錄本身。":
      "The fourth stage of the analysis chain: <b>herb → ingredient → target → pathway</b>. Target standardisation (F1-4) already stored each target's KEGG gene ID and Reactome pathway IDs while resolving UniProt, so no further external resolution is needed here — only the pathway catalogues themselves are fetched from KEGG / Reactome.",
    "富集檢定用的是超幾何分布（over-representation analysis），並以Benjamini–Hochberg校正多重檢定。一次對數千條通路做檢定，就算全是雜訊，在p<0.05這條線下也會有上百條「顯著」——所以請以q值（FDR校正後）為準，不要只看p值。":
      "<b>Enrichment uses the hypergeometric distribution</b> (over-representation analysis), with Benjamini–Hochberg correction for multiple testing. Testing thousands of pathways at once, even pure noise would give hundreds of “significant” results at p&lt;0.05 — so rely on the <b>q value</b> (FDR-corrected), not the p value alone.",
    "兩個預設開啟的篩選，關掉之前請先知道自己在關什麼：只用活性成分——TCMSP收錄的是這個藥材裡偵測得到的所有化合物，多數口服吸收率極低或不具類藥性，到不了體內任何靶點。預設先用OB ≥ 30%、DL ≥ 0.18篩過（TCMSP原始論文的建議值，也是本專案目標一Step 1定義的條件）。排除非癌症疾病類通路——KEGG的結核病、動脈粥狀硬化、B型肝炎這類通路，每一條都塞了AKT1／BCL2／CASP3／IL6／TP53這組通用發炎凋亡機器，所以任何靶點集合都會對它們「顯著」。那是統計假象，不是藥理發現。癌症通路與抗腫瘤抗藥性通路不受此排除影響。":
      "<b>Two filters are on by default — know what you are turning off before you turn them off:</b><br><b>Active ingredients only</b> — TCMSP lists <b>every</b> compound detectable in the herb; most have very low oral absorption or poor drug-likeness and never reach any target in the body. By default they are filtered with OB ≥ 30% and DL ≥ 0.18 (the values recommended in the original TCMSP paper, and the condition defined in Step 1 of this project's Goal 1).<br><b>Exclude non-cancer disease pathways</b> — KEGG pathways such as tuberculosis, atherosclerosis and hepatitis B each contain the generic inflammation/apoptosis machinery AKT1 / BCL2 / CASP3 / IL6 / TP53, so <b>any</b> target set looks “significant” for them. That is a statistical artefact, not a pharmacological finding. Cancer pathways and anti-tumour drug-resistance pathways are not affected by this exclusion.",
    "⚠️同步需要對外連線到rest.kegg.jp與reactome.org，請在已部署的Render環境操作。本結果為文獻資料庫的統計關聯，屬研究輔助資訊，不構成任何醫療診斷或治療建議。":
      "⚠️ Syncing needs outbound access to rest.kegg.jp and reactome.org — run it on the deployed Render environment. These results are statistical associations from literature databases, provided for research support only, and <b>do not constitute medical diagnosis or treatment advice</b>.",

    // 富集結果上方的說明（數字以 {0}… 佔位）
    "未套用活性成分篩選。這個藥材全部{0}個成分的靶點都被納入。TCMSP收錄的是偵測得到的所有化合物，多數到不了體內靶點——這個結果只適合當對照，不適合當成正式分析。":
      "<b style=\"color:#a83232;\">Active-ingredient filter not applied.</b> Targets of all {0} ingredients of this herb are included. TCMSP lists every detectable compound, most of which never reach targets in the body — use this result only as a control, <b>not as a formal analysis</b>.",
    "活性成分篩選：OB ≥ {0}%、DL ≥ {1}。{2}個成分中有{3}個通過（{4}%），對應{5}個靶點。":
      "<b>Active-ingredient filter: OB ≥ {0}%, DL ≥ {1}.</b> <b>{3}</b> of {2} ingredients pass ({4}%), mapping to <b>{5}</b> targets.",
    "活性成分篩選：OB ≥ {0}%、DL ≥ {1}。{2}個成分中有{3}個通過（{4}%），對應{5}個靶點。另有{6}個成分因為ADME資料缺值而排除（缺值不等於不活性，只是TCMSP沒收錄這個數字）。":
      "<b>Active-ingredient filter: OB ≥ {0}%, DL ≥ {1}.</b> <b>{3}</b> of {2} ingredients pass ({4}%), mapping to <b>{5}</b> targets. Another {6} ingredient(s) were excluded for missing ADME data (missing does not mean inactive — TCMSP simply has no value).",
    "母體：全部已標準化的中藥靶點。這次分析的樣本是這個藥材的{0}個有通路註解的靶點基因，母體{1}個基因。回答的是「這條通路在這個藥材裡，是否比在中藥靶點整體裡更常出現」。這會消掉「TCMSP的靶點本來就偏向可成藥蛋白」造成的系統性偏差，適合拿來比較不同藥材；但不是學界慣例，寫進論文要額外說明。":
      "<b>Background: all standardised TCM targets.</b> This analysis uses the herb's <b>{0}</b> pathway-annotated target genes against a background of <b>{1}</b> genes. It answers “does this pathway occur more often in <b>this</b> herb than across TCM targets as a whole?”. This removes the systematic bias that TCMSP targets are skewed towards druggable proteins, which suits comparisons between herbs — but it is not the field's convention, so explain it if you use it in a paper.",
    "母體：該資料庫收錄的全部人類基因（學界慣例）。這次分析的樣本是這個藥材的{0}個有通路註解的靶點基因，母體{1}個基因。回答的是「這條通路在這個藥材的靶點裡，是否比在全人類基因裡更常出現」。注意TCMSP的靶點本身就偏向傳統可成藥的蛋白（受體、酶、離子通道），所以訊號傳導與代謝類通路會被系統性高估——想消掉這個偏差請改用另一種母體。":
      "<b>Background: all human genes in the database (field convention).</b> This analysis uses the herb's <b>{0}</b> pathway-annotated target genes against a background of <b>{1}</b> genes. It answers “does this pathway occur more often among this herb's targets than among all human genes?”. Note that TCMSP targets are themselves skewed towards traditionally druggable proteins (receptors, enzymes, ion channels), so signalling and metabolic pathways are systematically overestimated — switch to the other background to remove this bias.",
    "{0}：共檢定{1}條通路": "{0}: {1} pathways tested",
    "（已排除{0}條非癌症疾病類通路）": " ({0} non-cancer disease pathways excluded)",
    "，{0}條達FDR q<0.05，": "; <b>{0}</b> reach FDR q&lt;0.05; ",
    "其中{0}條是獨立的基因組合（其餘與更高名次重疊≥80%，並列在報告裡會高估證據強度）；":
      "<b>{0}</b> of them are independent gene sets (the rest overlap ≥80% with higher-ranked pathways — listing them side by side in a report overstates the evidence); ",
    "以下依富集倍率排序，顯示前{0}條。": "sorted by fold enrichment, showing the top {0}.",
    "以下依統計顯著性排序，顯示前{0}條。": "sorted by statistical significance, showing the top {0}.",

    // 欄位說明視窗：每一節（標題＋內文）是一個段落。{0}＝母體基因數 N、{1}＝樣本基因數 n、{2}＝受檢通路數
    "這張表在做什麼：通路富集分析回答一個問題：這個藥材打到的蛋白，有沒有不成比例地集中在某些生物過程上？用彈珠來想：袋子裡有{0}顆彈珠（母體＝該資料庫收錄的全部基因），其中某條通路佔了其中幾顆（＝「通路基因」欄）。你閉眼抓出{1}顆（＝這個藥材有通路註解的靶點基因）。如果抓到的數量遠多於隨機預期，這條通路就是「富集」了。整份分析就是把這件事對{2}條通路各做一次，再排序。":
      "<h4>What this table does: pathway enrichment analysis</h4><p>It answers one question: <b>are the proteins hit by this herb disproportionately concentrated in particular biological processes?</b></p><p>Think of marbles: a bag holds <b>{0}</b> marbles (the background = all genes in the database), and a given pathway accounts for some of them (= the “pathway genes” column). With your eyes closed you draw <b>{1}</b> marbles (= this herb's pathway-annotated target genes). If you draw far more from that pathway than chance would predict, the pathway is “enriched”.</p><p>The analysis repeats this for each of <b>{2}</b> pathways and then ranks them.</p>",
    "# —名次目前排序方式下的名次。綠色代表這一列達FDR q<0.05。切成「依富集倍率」排序時，序號下方會多一行小字p #12，那是它在統計顯著性排序裡的名次。兩種排序都看一次比較不會漏——理由見「倍率」欄的說明。":
      "<h4># — rank</h4><p>Rank under the current sort order. <b>Green</b> means the row reaches FDR q&lt;0.05.</p><p>When sorted by fold enrichment, a small line <code>p #12</code> appears under the rank: its rank in the significance ordering. <b>Look at both orderings so nothing slips through</b> — see the “Fold” column for why.</p>",
    "通路—識別碼KEGG或Reactome給這條通路的唯一編號。hsa代表人類（Homo sapiens）。點一下編號就會在新分頁開啟原始通路圖。KEGG的連結會把這個藥材命中的基因直接標色——不只是「這條通路顯著」，而是看得到這些靶點落在通路圖的哪個位置、彼此的上下游關係是什麼。那才是判斷機轉是否說得通的依據。Reactome的連結會開啟PathwayBrowser。":
      "<h4>Pathway — identifier</h4><p>The unique ID KEGG or Reactome assigns to the pathway. <code>hsa</code> means human (Homo sapiens).</p><p><b>Click the ID to open the original pathway map in a new tab.</b></p><p>KEGG links <b>colour the genes hit by this herb directly on the map</b> — not just “this pathway is significant”, but where these targets sit on the map and how they relate upstream and downstream. That is what tells you whether a mechanism makes sense.</p><p>Reactome links open the PathwayBrowser.</p>",
    "名稱—這條通路在做什麼通路名稱。底下灰字是資料庫自己的分類階層，例如Environmental Information Processing / Signaling molecules and interaction前半是大類、後半是次類。分類很有用：一眼分辨這是核心訊號通路、代謝通路、還是疾病通路。標成癌症相關的是KEGG官方癌症分類，加上本平台另外標記的核心腫瘤訊號通路。標成重複的，代表它命中的基因有80%以上已經出現在更高名次的通路裡——那不是一項獨立發現，詳見「命中的基因」欄說明。":
      "<h4>Name — what the pathway does</h4><p>The pathway name. The grey text below is the database's own <b>classification</b>, e.g. <code>Environmental Information Processing / Signaling molecules and interaction</code> — top level first, then sub-class.</p><p>The classification tells you at a glance whether this is a core signalling, metabolic or disease pathway. Pathways marked <b>cancer-related</b> are KEGG's official cancer classes plus core tumour-signalling pathways tagged by this platform.</p><p>A <b>duplicate</b> mark means at least 80% of its hit genes already appear in higher-ranked pathways — <span class=\"warn\">that is not an independent finding</span>; see the “Hit genes” column.</p>",
    "命中—這個藥材打中這條通路的幾個基因這個藥材的{1}個靶點基因裡，有幾個落在這條通路內。它跟「通路基因」一起決定後面所有的數字。命中數太少（例如2、3個）時，就算倍率很高也不穩——換一份資料很可能就不見了。":
      "<h4>Hits — how many of the herb's genes fall in this pathway</h4><p>How many of this herb's <b>{1}</b> target genes fall within this pathway.</p><p>Together with “pathway genes” it determines every number that follows. <b>With very few hits (say 2 or 3), even a high fold enrichment is unstable</b> — it may well disappear with a different dataset.</p>",
    "通路基因—這條通路總共有幾個基因這條通路在母體裡的總成員數，也就是富集計算的分母之一。這個數字會隨你選的母體改變。選「全人類基因」時是該通路在全基因體中的大小；選「全部中藥靶點」時，只算其中有被中藥靶點涵蓋到的部分，所以會小很多。兩者不能直接互相比較。":
      "<h4>Pathway genes — total genes in this pathway</h4><p>The pathway's total membership within the background — one of the denominators in the enrichment calculation.</p><p><b>This number changes with the background you choose.</b> With “all human genes” it is the pathway's genome-wide size; with “all TCM targets” only the members covered by TCM targets count, so it is much smaller. The two are not directly comparable.</p>",
    "倍率—效果有多強實際命中數÷隨機抽樣的期望命中數。倍率=（命中÷ {1}）÷（通路基因÷ {0}）倍率1.0表示跟隨機一樣、完全沒有富集；3.0表示比隨機預期多了三倍。倍率是「效果有多強」，p值是「有多不可能是巧合」——這兩件事最常被混為一談。一條有五百個基因的大通路很容易命中很多、p值很小，但倍率可能只有兩倍。注意：p值同時取決於倍率與絕對命中數，而命中數多則統計檢定力高，所以依p值排序會系統性偏袒基因數多的大通路，把高特異性的小通路往後推。這是富集分析的固有特性，不是程式問題——所以本頁提供「依倍率排序」。":
      "<h4>Fold — how strong the effect is</h4><p>Observed hits ÷ hits expected by random sampling.</p><span class=\"formula\">Fold = (hits ÷ {1}) ÷ (pathway genes ÷ {0})</span><p>A fold of 1.0 is the same as chance — no enrichment at all; 3.0 means three times more than chance would predict.</p><p><b>Fold is “how strong the effect is”; the p value is “how unlikely it is to be coincidence” — the two are most often confused.</b> A large pathway with five hundred genes easily collects many hits and a tiny p value, yet its fold may be only two.</p><p class=\"warn\">Note: the p value depends on both fold and the absolute number of hits, and more hits means more statistical power, so <b>sorting by p systematically favours large pathways</b> and pushes small, highly specific ones down. This is inherent to enrichment analysis, not a bug — which is why this page offers “sort by fold”.</p>",
    "p值—有多不可能是巧合如果這個藥材的靶點其實是隨機抽的，抓到這麼多（或更多）命中的機率有多大。用的是超幾何分布。1.73e-9就是0.00000000173，約十億分之1.7——機率極低，代表「隨機碰巧」這個解釋站不住腳。但判讀時請不要用p值，要用q值。原因見下一欄。":
      "<h4>p value — how unlikely it is to be coincidence</h4><p>If this herb's targets had been drawn at random, the probability of getting this many hits (or more). Computed with the hypergeometric distribution.</p><p><code>1.73e-9</code> is 0.00000000173 — about 1.7 in a billion. Such a low probability means “random coincidence” does not hold up as an explanation.</p><p class=\"warn\"><b>But do not interpret results by p — use q.</b> See the next column for why.</p>",
    "q值（FDR）—判讀請看這一欄p值有一個陷阱：你不是只檢驗一條通路，這次同時檢驗了{2}條。如果用p<0.05當標準，就算這些通路全部都是雜訊，光靠運氣也會有約5%通過。你會很開心地把它們寫進報告——而它們全是假的。q值（false discovery rate，Benjamini–Hochberg校正）已經把「你做了{2}次檢定」這件事算進去了。判讀規則：看q值，不看p值。q < 0.05才算顯著。q值一定大於或等於同一列的p值，這是校正的本質。":
      "<h4>q value (FDR) — use this column to interpret results</h4><p>The p value has a trap: you are not testing one pathway — this run tested <b>{2}</b> at once.</p><p>With p&lt;0.05 as the cut-off, <b>even if every pathway were noise</b>, about 5% would pass by luck alone. You would happily put them in a report — and every one would be false.</p><p>The q value (false discovery rate, Benjamini–Hochberg correction) already accounts for the fact that you ran {2} tests.</p><span class=\"formula\">Rule: read q, not p. Only q &lt; 0.05 counts as significant.</span><p>q is always greater than or equal to the p value in the same row — that is the nature of the correction.</p>",
    "命中的基因—以及為什麼「顯著通路數」會騙人這條通路裡被這個藥材打中的基因。粗體綠色是新出現的、灰色是更高名次已經出現過的，下方標「新增N / M個基因」。為什麼要這樣標：KEGG／Reactome的通路定義大量重疊，同一組基因會同時落在好幾條通路裡。實測人參的例子：Apoptosis命中BAX、BCL2、CASP3、CASP8、CASP9、MAPK8 p53 signaling BAX、BCL2、CASP3、CASP8、CASP9、CDK1 →六個裡有五個完全相同並列成兩項發現會被讀成交叉印證，實際上是同一個觀察被算了兩次。所以摘要行除了「顯著通路數」還會給「獨立發現數」——扣掉與更高名次重疊≥80%的之後還剩幾條。寫進報告要引用的是獨立發現數，不是顯著通路數。":
      "<h4>Hit genes — and why “number of significant pathways” misleads</h4><p>Genes in this pathway hit by this herb. <b>Bold green</b> genes are new; <span class=\"sym-old\">grey</span> genes already appeared in higher-ranked pathways, with “N / M genes new” noted below.</p><p><b>Why mark them this way:</b> KEGG / Reactome pathway definitions overlap heavily, and the same genes fall into several pathways at once. A real ginseng example:</p><span class=\"formula\">Apoptosis hits      BAX, BCL2, CASP3, CASP8, CASP9, MAPK8\np53 signaling       BAX, BCL2, CASP3, CASP8, CASP9, CDK1\n                    → five of six identical</span><p>Listed as two findings, they read as cross-confirmation — <span class=\"warn\">in fact the same observation counted twice</span>.</p><p>So besides “significant pathways”, the summary line gives “<b>independent findings</b>” — how many remain after removing those overlapping ≥80% with higher-ranked pathways. <b class=\"warn\">Cite the number of independent findings in reports, not the number of significant pathways.</b></p>",

    // ---- 帶數字的短句（純文字，一般文字節點也會用到，見 site-lang.js convertText）----
    "{0}個成分": "{0} ingredient(s)",
    "共{0}種藥材": "{0} herbs",
    "篩選門檻OB ≥ {0}%、DL ≥ {1}": "Thresholds OB ≥ {0}%, DL ≥ {1}",
    "已標準化（{0}%）": "Standardised ({0}%)",
    "共{0}個活性成分": "{0} active ingredients",
    "共{0}個非活性成分": "{0} inactive ingredients",
    "顯示{0} / {1}個": "Showing {0} / {1}",
    "活性成分（OB ≥ {0}%、DL ≥ {1}）": "Active ingredients (OB ≥ {0}%, DL ≥ {1})",
    "資料來源：{0}": "Source: {0}",
    "新增{0} / {1}個基因": "{0} / {1} genes new",
    "KEGG：{0}條靶點↔通路關聯，背景基因{1}，最後同步{2}": "KEGG: {0} target↔pathway links, {1} background genes, last synced {2}",
    "Reactome：{0}條靶點↔通路關聯，背景基因{1}，最後同步{2}": "Reactome: {0} target↔pathway links, {1} background genes, last synced {2}",
    "KEGG：{0}條靶點↔通路關聯，背景基因{1}，最後同步{2} Reactome：{3}條靶點↔通路關聯，背景基因{4}，最後同步{5}": "KEGG: {0} target↔pathway links, {1} background genes, last synced {2}\nReactome: {3} target↔pathway links, {4} background genes, last synced {5}",
  };

  const ko = {
    // ============================================================ 藥材活性成分（herb-ingredients）
    "先用OB（口服生物利用度）與DL（類藥性）兩道門檻篩出這味藥材的活性成分，再逐一顯示每個成分有沒有成功對應到PubChem的化學結構。後續的靶點、通路與細胞株分析都只使用這些活性成分，不是全部成分。沒通過門檻的成分可切換到「非活性成分」查看，並標示是哪一道門檻沒過。":
      "먼저 <b>OB(경구 생체이용률)</b>와 <b>DL(약물 유사성)</b> 두 가지 기준으로 이 약재의 활성 성분을 선별한 뒤, 각 성분이 PubChem 화학 구조에 성공적으로 매칭되었는지 하나씩 보여 줍니다. 이후의 표적·경로·세포주 분석은 <b>이 활성 성분만 사용</b>하며 전체 성분을 쓰지 않습니다. 기준을 통과하지 못한 성분은 「비활성 성분」 탭에서 볼 수 있으며, 어느 기준에서 탈락했는지 표시됩니다.",
    "怎麼讀這一頁：「已標準化」只算自動採用與已確認兩種狀態——待確認是還沒審過的候選，拿它當成果會高估。分子量差欄位若標示「疑似苷元誤配」，代表名稱雖然對上、但查到的很可能是帶糖基的另一個分子，這種一律要人工判斷，不可直接採用。":
      "<b>이 페이지 읽는 법:</b> 「표준화 완료」는 <b>자동 채택</b>과 <b>확인 완료</b> 두 상태만 셉니다. 「확인 대기」는 아직 검토되지 않은 후보이므로 성과로 계산하면 과대평가됩니다. 분자량 차이 열에 「아글리콘 오매칭 의심」이 표시되면 이름은 일치했지만 찾은 기록이 <b>당이 결합된 다른 분자</b>일 가능성이 높다는 뜻이므로, 반드시 사람이 판단해야 하며 그대로 채택해서는 안 됩니다.",
    "名稱來源：成分名稱為TCMSP的英文原名；「IUPAC系統名稱」來自PubChem，只有已對應到CID的成分才有。化合物沒有拉丁文名稱（拉丁學名是給藥材物種用的），化合物的國際標準命名就是IUPAC系統名稱。資料庫沒有中文名稱與化學分類欄位，本頁因此不提供。":
      "<b>명칭 출처:</b> 성분명은 TCMSP의 영문 원명이며, 「IUPAC 체계명」은 PubChem에서 가져온 것으로 CID에 매칭된 성분에만 있습니다. 화합물에는 라틴어 이름이 없습니다(라틴어 학명은 약재의 생물 종에 쓰입니다). 화합물의 국제 표준 명칭이 바로 IUPAC 체계명입니다. 데이터베이스에 <b>중국어 명칭과 화학 분류 필드가 없으므로</b> 이 페이지에서는 제공하지 않습니다.",
    "非活性成分：上方的「已標準化、有SMILES」等數字只算活性成分；非活性成分另列在「非活性成分」分頁，不進入後續的靶點、通路與細胞株分析。":
      "<b>비활성 성분:</b> 위의 「표준화 완료」, 「SMILES 보유」 등의 수치는 <b>활성 성분만 집계</b>합니다. 비활성 성분은 「비활성 성분」 탭에 따로 표시되며, 이후의 표적·경로·세포주 분석에는 사용되지 않습니다.",
    "目前這味藥材還有{0}個活性成分尚未完成標準化。":
      "이 약재에는 아직 표준화되지 않은 활성 성분이 <b>{0}</b>개 있습니다.",
    "這味藥材的活性成分已全部完成標準化。":
      "이 약재의 활성 성분은 모두 표준화되었습니다.",
    [DISCLAIMER]:
      "본 플랫폼은 연구 보조 도구이며, 모든 결과는 공개 데이터베이스의 통계적 연관성으로 <b>의학적 진단이나 치료 권고가 아닙니다</b>.",

    "Mol ID（TCMSP成分編號）": "Mol ID (TCMSP 성분 번호)",
    "TCMSP自己發給每個成分的編號，格式是MOL加6碼數字（例如MOL000098）。它只在TCMSP這一套系統裡有意義——拿Mol ID去PubChem、UniProt或任何其他資料庫都查不到東西，也沒有化學結構的資訊在裡面。正因為如此，本平台才要做「成分標準化」，把每個Mol ID對應到下面那三個國際通用的編號。點編號可到中藥關聯查詢站看這個成分的靶點與疾病關聯。":
      "TCMSP가 각 성분에 부여한 자체 번호로, MOL 뒤에 숫자 6자리가 붙는 형식입니다(예: MOL000098). TCMSP 안에서만 의미가 있으며, Mol ID로 PubChem, UniProt 등 다른 데이터베이스를 검색해도 아무것도 나오지 않고 화학 구조 정보도 담고 있지 않습니다. 그래서 본 플랫폼은 「성분 표준화」를 통해 각 Mol ID를 아래의 국제 공통 식별자 세 가지에 매핑합니다. 번호를 클릭하면 한약 연관 조회 사이트에서 이 성분의 표적과 질병 연관을 볼 수 있습니다.",
    "PubChem CID — PubChem Compound ID（化合物編號）": "PubChem CID — PubChem Compound ID (화합물 번호)",
    "美國國家生物技術資訊中心（NCBI）旗下PubChem資料庫發給每個化合物的編號，是一串純數字。這是國際通用的編號，拿著它可以到PubChem查到分子結構、物化性質、生物活性試驗與文獻。本頁的CID是由成分名稱比對後對應過來的，狀態要是「自動採用」或「已確認」才算數。":
      "미국 국립생물공학정보센터(NCBI)의 PubChem 데이터베이스가 각 화합물에 부여하는 숫자로만 된 번호입니다. 국제적으로 통용되며, 이 번호로 PubChem에서 분자 구조, 물리화학적 성질, 생물활성 시험과 문헌을 찾을 수 있습니다. 이 페이지의 CID는 성분명을 대조해 매핑한 것으로, 상태가 「자동 채택」 또는 「확인 완료」일 때만 인정됩니다.",
    "InChIKey — International Chemical Identifier Key（國際化學標識符雜湊碼）": "InChIKey — International Chemical Identifier Key (국제 화학 식별자 해시)",
    "由IUPAC（國際純化學暨應用化學聯合會）制定，直接從分子結構算出來的27碼固定長度指紋，格式是14碼-10碼-1碼。它不是誰發的號碼，而是結構的計算結果，所以同一個分子在任何資料庫算出來都一樣，是跨資料庫比對最可靠的鍵值，也可以直接丟進Google搜尋。":
      "IUPAC(국제순수·응용화학연맹)가 정한 방식으로 분자 구조에서 직접 계산한 27자리 고정 길이 지문이며, 형식은 14자리-10자리-1자리입니다. 누군가 부여한 번호가 아니라 구조를 계산한 결과이므로 같은 분자는 어느 데이터베이스에서 계산해도 같은 값이 나옵니다. 데이터베이스 간 대조에 가장 신뢰할 수 있는 키이며, Google 검색에 그대로 넣어도 됩니다.",
    "SMILES — Simplified Molecular Input Line Entry System（簡化分子線性輸入規範）": "SMILES — Simplified Molecular Input Line Entry System (간이 분자 선형 표기법)",
    "用一行文字描述分子結構的寫法：原子用元素符號（C、N、O…），單鍵省略、雙鍵寫=、三鍵寫#，括號表示分支，數字表示環的開合。例如乙醇是CCO，苯是c1ccccc1（小寫代表芳香環）。有了SMILES，就能把分子畫出來、算物化性質、做結構相似性比對與分子對接，是後續結構分析與AI模型的輸入格式。同一個分子可以有好幾種寫法，所以跨資料庫比對請用InChIKey，不要直接比SMILES字串。本欄✓表示這個成分已從PubChem取得SMILES（只算標準化狀態為「自動採用」或「已確認」的那一筆）；✗表示尚未對應到結構。點PubChem CID可以看到完整的SMILES與結構圖。":
      "분자 구조를 한 줄의 문자로 표기하는 방법입니다. 원자는 원소 기호(C, N, O…)로 쓰고, 단일 결합은 생략하며 이중 결합은 =, 삼중 결합은 #로 씁니다. 괄호는 가지, 숫자는 고리의 열고 닫음을 나타냅니다. 예를 들어 에탄올은 CCO, 벤젠은 c1ccccc1(소문자는 방향족 고리)입니다.\n\nSMILES가 있으면 분자를 그리고, 물성을 계산하고, 구조 유사성 비교와 분자 도킹을 할 수 있어 이후 구조 분석과 AI 모델의 입력 형식이 됩니다. 같은 분자도 여러 방식으로 쓸 수 있으므로 데이터베이스 간 대조에는 SMILES 문자열이 아니라 InChIKey를 사용하세요.\n\n이 열의 ✓는 PubChem에서 SMILES를 얻었다는 뜻이며(표준화 상태가 「자동 채택」 또는 「확인 완료」인 기록만 집계), ✗는 아직 구조가 매칭되지 않았다는 뜻입니다. PubChem CID를 클릭하면 전체 SMILES와 구조도를 볼 수 있습니다.",
    "IUPAC系統名稱— IUPAC Systematic Name": "IUPAC 체계명 — IUPAC Systematic Name",
    "由IUPAC（國際純化學暨應用化學聯合會）規則從分子結構推導出來的標準化學名稱，全世界通用，看名稱就能還原出結構。關於「拉丁文名稱」：拉丁學名是給生物物種用的（例如藥材人參的學名Panax ginseng C. A. Mey.），化合物本身沒有拉丁文名稱；化合物的國際標準命名就是這個IUPAC系統名稱。資料來自PubChem，只有已對應到PubChem CID的成分才有。天然物（皂苷、多醣類）的系統名稱常常很長，表格只顯示前三行，滑鼠移上去可看全文。":
      "IUPAC(국제순수·응용화학연맹) 규칙에 따라 분자 구조에서 유도한 표준 화학 명칭으로, 전 세계에서 통용되며 이름만으로 구조를 복원할 수 있습니다.\n\n「라틴어 이름」에 관하여: 라틴어 학명은 생물 종에 쓰는 것이며(예: 인삼의 학명 Panax ginseng C. A. Mey.), 화합물 자체에는 라틴어 이름이 없습니다. 화합물의 국제 표준 명칭이 바로 이 IUPAC 체계명입니다.\n\n데이터는 PubChem에서 가져오며, PubChem CID에 매칭된 성분에만 있습니다. 천연물(사포닌, 다당류)의 체계명은 매우 긴 경우가 많아 표에는 처음 세 줄만 표시되며, 마우스를 올리면 전체를 볼 수 있습니다.",
    "未納入原因": "제외 사유",
    "這個成分沒有被列為活性成分的原因：・OB未達：口服生物利用度低於門檻，吃下去大多吸收不到。・DL未達：類藥性低於門檻，結構不像一般藥物分子。・OB、DL皆未達：兩道門檻都沒過。・ADME缺值：TCMSP沒有這個成分的OB或DL數值，無法判定，一律排除（不是因為數值低）。門檻值顯示在頁面上方，由管理者在系統設定調整。非活性成分不進入後續的靶點、通路與細胞株分析，但其中有些可能經腸道菌代謝後才轉為活性形式，研究上仍可參考。":
      "이 성분이 활성 성분으로 분류되지 않은 이유:\n・OB 기준 미달: 경구 생체이용률이 기준보다 낮아 복용해도 대부분 흡수되지 않습니다.\n・DL 기준 미달: 약물 유사성이 기준보다 낮아 구조가 일반적인 약물 분자와 다릅니다.\n・OB·DL 모두 미달: 두 기준을 모두 통과하지 못했습니다.\n・ADME 결측: TCMSP에 이 성분의 OB 또는 DL 값이 없어 판단할 수 없으므로 일괄 제외합니다(값이 낮아서가 아닙니다).\n\n기준값은 페이지 상단에 표시되며 관리자가 시스템 설정에서 조정합니다. 비활성 성분은 이후의 표적·경로·세포주 분석에 사용되지 않지만, 일부는 장내 미생물 대사를 거쳐 활성형으로 바뀔 수 있어 연구상 참고할 가치가 있습니다.",
    "CAS號— CAS Registry Number（化學文摘社登記號）": "CAS 번호 — CAS Registry Number (화학초록서비스 등록번호)",
    "美國化學文摘社（Chemical Abstracts Service，隸屬美國化學會）發給每一個已登錄物質的編號，格式是「數字-數字-檢查碼」（例如50-00-0）。化工、法規、安全資料表（SDS）與採購上最常用這個編號，要跟法規清單或試劑供應商對照時，CAS號通常比CID更通用。它是商業資料庫，並非所有化合物都有登錄號。":
      "미국 화학초록서비스(Chemical Abstracts Service, 미국화학회 소속)가 등록된 모든 물질에 부여하는 번호로, 형식은 「숫자-숫자-검사 숫자」입니다(예: 50-00-0). 화학 산업, 규제, 물질안전보건자료(SDS), 구매에서 가장 많이 쓰이며, 규제 목록이나 시약 공급업체와 대조할 때는 보통 CID보다 CAS 번호가 더 널리 통용됩니다. 상업 데이터베이스이므로 모든 화합물에 등록번호가 있는 것은 아닙니다.",

    // ============================================================ 腫瘤細胞株依賴（tumor-cells）
    "藥材的活性成分→靶點→哪些靶點是特定腫瘤細胞株的選擇性依賴（DepMap CRISPR篩選）。先排除泛必需基因（命中它們是細胞毒性，不是抗腫瘤機轉），再以選擇性當門檻、效應量當排序。每一列都是一個可以被否證的驗證方案起點：具體基因、具體細胞株、具體癌別。":
      "약재 활성 성분 → 표적 → <b>어떤 표적이 특정 종양 세포주의 선택적 의존성인가</b>(DepMap CRISPR 스크리닝). 먼저 <b>범필수 유전자</b>를 제외하고(이를 맞히는 것은 세포독성이지 항종양 기전이 아닙니다), <b>선택성을 기준으로, 효과 크기를 순위로</b> 삼습니다. 각 행은 반증 가능한 검증 계획의 출발점입니다: 구체적인 유전자, 구체적인 세포주, 구체적인 암종.",
    "有依賴：gene effect ≤ {0}；強依賴：≤ {1}。換了門檻，數字的意義就不同，兩次結果不能直接比較。":
      "의존: gene effect ≤ {0}; 강한 의존: ≤ {1}. 기준을 바꾸면 수치의 의미가 달라지므로 서로 다른 기준의 결과는 직접 비교할 수 없습니다.",
    "選擇性靶點（{0}）": "선택적 표적 ({0})",
    "被門檻刷掉（{0}）": "기준에서 탈락 ({0})",
    "泛必需（已排除）（{0}）": "범필수 (제외됨) ({0})",
    "排序：通過選擇性門檻後，依最強效應由強到弱（不是依株數——株數多代表廣度，不是選擇性）。":
      "정렬: 선택성 기준을 통과한 뒤 <b>최대 효과</b>가 강한 순(세포주 수 기준이 아님 — 세포주가 많다는 것은 범위이지 선택성이 아닙니다).",
    "這些不是沒有訊號，而是訊號不具選擇性——在很多細胞株都依賴的基因，抑制它比較像細胞毒性而不是機轉。要看它們可以放寬上方的門檻。":
      "신호가 없는 것이 아니라 <b>신호에 선택성이 없는</b> 것입니다. 많은 세포주가 의존하는 유전자를 억제하는 것은 기전이라기보다 세포독성에 가깝습니다. 보려면 위의 기준을 완화하세요.",
    "這些基因在幾乎每一株細胞都是存活必需。任何有細胞毒性的物質都會「命中」它們，所以不能拿來當抗腫瘤機轉的證據。":
      "이 유전자들은 거의 모든 세포주에서 생존에 필수입니다. 세포독성이 있는 물질이라면 무엇이든 이들을 「맞히므로」 항종양 기전의 근거로 <b>사용할 수 없습니다</b>.",
    "這張表不是「這味藥能治這些癌」。它說的是：這味藥材的活性成分在TCMSP被註記為作用於這些靶點，而這些靶點在那些細胞株是選擇性依賴。兩件事之間還缺實際的結合與活性驗證—— TCMSP的成分–靶點關係有相當比例是對接預測，不是實測結合，目前尚未分層。":
      "<b>이 표는 「이 약재가 이 암들을 치료한다」는 뜻이 아닙니다.</b> 이 약재의 활성 성분이 TCMSP에서 이 표적들에 작용한다고 주석되어 있고, 이 표적들이 해당 세포주들의 선택적 의존성이라는 뜻입니다. 둘 사이에는 실제 결합과 활성 검증이 아직 빠져 있습니다 — <b>TCMSP의 성분–표적 관계 중 상당 부분은 실측 결합이 아니라 도킹 예측</b>이며, 아직 등급화되지 않았습니다.",
    "⚠️方向性：CRISPR依賴量的是「移除這個基因，細胞會不會死」，要轉成治療假說，前提是化合物抑制該靶點；TCMSP不記錄作用方向。":
      "<b>⚠️ 방향성:</b> CRISPR 의존성은 「이 유전자를 <b>제거</b>하면 세포가 죽는가」를 측정합니다. 이를 치료 가설로 바꾸려면 화합물이 해당 표적을 <b>억제</b>한다는 전제가 필요한데, TCMSP는 작용 방향을 기록하지 않습니다.",
    "本表有{0}個標為「受體」——核受體與配體門控受體的天然配體通常是活化劑，方向反了效果可能相反。":
      "이 표에는 「수용체」로 표시된 표적이 <b>{0}</b>개 있습니다 — 핵수용체와 리간드 개폐 수용체의 천연 리간드는 보통 활성화제이므로, 방향이 반대면 효과도 반대일 수 있습니다.",
    "受體標記是啟發式的，只用來提醒；沒被標記也不代表方向沒問題。":
      "수용체 표시는 휴리스틱으로 상기용일 뿐이며, 표시되지 않았다고 방향에 문제가 없다는 뜻은 아닙니다.",
    "強依賴株數為「—」的列請當成雜訊看待：只在少數細胞、效應剛越過門檻的配對，在這個規模的矩陣裡本來就會隨機出現。":
      "<b>강한 의존 세포주 수가 「—」인 행은 잡음으로 보세요:</b> 소수의 세포에서만, 효과가 기준을 겨우 넘는 조합은 이 규모의 행렬에서 원래 무작위로 나타납니다.",
    "CRISPR敲除≠化合物抑制；DepMap只有腫瘤細胞株，這裡的「選擇性」是腫瘤株之間的比較，不是腫瘤vs正常細胞。":
      "<b>CRISPR 녹아웃 ≠ 화합물 억제</b>입니다. DepMap에는 종양 세포주만 있으므로 여기서 「선택성」은 종양 세포주끼리의 비교이지, 종양 대 정상 세포의 비교가 아닙니다.",
    "本頁不提供lineage（癌別）富集：以人參為例，該富集經對照基因集檢定後落在隨機範圍內，不能解讀為這味藥材的特性。":
      "이 페이지는 lineage(암종) 농축을 제공하지 않습니다. 인삼의 경우 대조 유전자 세트로 검정한 결과 무작위 범위 안에 들어, 이 약재의 특성으로 해석할 수 없습니다.",
    "這株細胞依賴、而且是「{0}」選擇性靶點的基因（{1}個），依這株的效應由強到弱：":
      "이 세포주가 의존하면서 「{0}」의 선택적 표적인 유전자({1}개), 이 세포주에서의 효과가 강한 순:",

    // ============================================================ 通路富集（pathways）
    "分析鏈路的第四站：中藥→成分→靶點→通路。靶點標準化（F1-4）解析UniProt時已經順手把每個靶點的KEGG基因編號與Reactome通路編號存下來，所以這裡不必再跑一輪外部解析，只需要向KEGG／Reactome要通路目錄本身。":
      "분석 체인의 네 번째 단계: <b>한약 → 성분 → 표적 → 경로</b>. 표적 표준화(F1-4)에서 UniProt을 조회할 때 각 표적의 KEGG 유전자 번호와 Reactome 경로 번호를 이미 저장해 두었으므로, 여기서는 외부 조회를 다시 할 필요 없이 KEGG / Reactome에서 경로 목록만 받아오면 됩니다.",
    "富集檢定用的是超幾何分布（over-representation analysis），並以Benjamini–Hochberg校正多重檢定。一次對數千條通路做檢定，就算全是雜訊，在p<0.05這條線下也會有上百條「顯著」——所以請以q值（FDR校正後）為準，不要只看p值。":
      "<b>농축 검정은 초기하분포를 사용</b>하며(over-representation analysis), Benjamini–Hochberg 방법으로 다중 검정을 보정합니다. 수천 개의 경로를 한꺼번에 검정하면 모두 잡음이라도 p&lt;0.05 기준에서 수백 개가 「유의」하게 나옵니다. 따라서 p값만 보지 말고 <b>q값</b>(FDR 보정 후)을 기준으로 하세요.",
    "兩個預設開啟的篩選，關掉之前請先知道自己在關什麼：只用活性成分——TCMSP收錄的是這個藥材裡偵測得到的所有化合物，多數口服吸收率極低或不具類藥性，到不了體內任何靶點。預設先用OB ≥ 30%、DL ≥ 0.18篩過（TCMSP原始論文的建議值，也是本專案目標一Step 1定義的條件）。排除非癌症疾病類通路——KEGG的結核病、動脈粥狀硬化、B型肝炎這類通路，每一條都塞了AKT1／BCL2／CASP3／IL6／TP53這組通用發炎凋亡機器，所以任何靶點集合都會對它們「顯著」。那是統計假象，不是藥理發現。癌症通路與抗腫瘤抗藥性通路不受此排除影響。":
      "<b>기본으로 켜져 있는 필터 두 가지 — 끄기 전에 무엇을 끄는지 알아 두세요:</b><br><b>활성 성분만 사용</b> — TCMSP는 이 약재에서 검출되는 <b>모든</b> 화합물을 수록하지만, 대부분은 경구 흡수율이 매우 낮거나 약물 유사성이 없어 체내의 어떤 표적에도 도달하지 못합니다. 기본값으로 OB ≥ 30%, DL ≥ 0.18로 걸러냅니다(TCMSP 원 논문의 권장값이자 본 프로젝트 목표 1 Step 1에서 정의한 조건).<br><b>비암 질환 경로 제외</b> — 결핵, 죽상동맥경화증, B형 간염 같은 KEGG 경로에는 모두 AKT1 / BCL2 / CASP3 / IL6 / TP53이라는 범용 염증·세포사멸 장치가 들어 있어 <b>어떤</b> 표적 집합이든 「유의」하게 나옵니다. 이는 통계적 착시이지 약리학적 발견이 아닙니다. 암 경로와 항종양 약물 내성 경로는 이 제외의 영향을 받지 않습니다.",
    "⚠️同步需要對外連線到rest.kegg.jp與reactome.org，請在已部署的Render環境操作。本結果為文獻資料庫的統計關聯，屬研究輔助資訊，不構成任何醫療診斷或治療建議。":
      "⚠️ 동기화에는 rest.kegg.jp와 reactome.org로의 외부 연결이 필요하므로 배포된 Render 환경에서 실행하세요. 이 결과는 문헌 데이터베이스의 통계적 연관성으로 연구 보조 정보이며, <b>어떠한 의학적 진단이나 치료 권고도 아닙니다</b>.",

    "未套用活性成分篩選。這個藥材全部{0}個成分的靶點都被納入。TCMSP收錄的是偵測得到的所有化合物，多數到不了體內靶點——這個結果只適合當對照，不適合當成正式分析。":
      "<b style=\"color:#a83232;\">활성 성분 필터가 적용되지 않았습니다.</b> 이 약재의 전체 {0}개 성분의 표적이 모두 포함되었습니다. TCMSP는 검출 가능한 모든 화합물을 수록하며 대부분은 체내 표적에 도달하지 못합니다. 이 결과는 대조용으로만 적합하며 <b>정식 분석으로는 적합하지 않습니다</b>.",
    "活性成分篩選：OB ≥ {0}%、DL ≥ {1}。{2}個成分中有{3}個通過（{4}%），對應{5}個靶點。":
      "<b>활성 성분 필터: OB ≥ {0}%, DL ≥ {1}.</b> {2}개 성분 중 <b>{3}</b>개 통과({4}%), 표적 <b>{5}</b>개에 해당합니다.",
    "活性成分篩選：OB ≥ {0}%、DL ≥ {1}。{2}個成分中有{3}個通過（{4}%），對應{5}個靶點。另有{6}個成分因為ADME資料缺值而排除（缺值不等於不活性，只是TCMSP沒收錄這個數字）。":
      "<b>활성 성분 필터: OB ≥ {0}%, DL ≥ {1}.</b> {2}개 성분 중 <b>{3}</b>개 통과({4}%), 표적 <b>{5}</b>개에 해당합니다. 그 밖에 {6}개 성분은 ADME 데이터 결측으로 제외되었습니다(결측은 비활성을 뜻하지 않으며, TCMSP에 값이 없을 뿐입니다).",
    "母體：全部已標準化的中藥靶點。這次分析的樣本是這個藥材的{0}個有通路註解的靶點基因，母體{1}個基因。回答的是「這條通路在這個藥材裡，是否比在中藥靶點整體裡更常出現」。這會消掉「TCMSP的靶點本來就偏向可成藥蛋白」造成的系統性偏差，適合拿來比較不同藥材；但不是學界慣例，寫進論文要額外說明。":
      "<b>모집단: 표준화된 전체 한약 표적.</b> 이번 분석의 표본은 이 약재의 경로 주석이 있는 표적 유전자 <b>{0}</b>개이며, 모집단은 <b>{1}</b>개 유전자입니다. 「이 경로가 <b>이</b> 약재에서 한약 표적 전체보다 더 자주 나타나는가」에 답합니다. 「TCMSP 표적은 원래 약물 표적이 되기 쉬운 단백질에 치우쳐 있다」는 체계적 편향을 없애 약재 간 비교에 적합하지만, 학계 관례는 아니므로 논문에 쓸 때는 따로 설명해야 합니다.",
    "母體：該資料庫收錄的全部人類基因（學界慣例）。這次分析的樣本是這個藥材的{0}個有通路註解的靶點基因，母體{1}個基因。回答的是「這條通路在這個藥材的靶點裡，是否比在全人類基因裡更常出現」。注意TCMSP的靶點本身就偏向傳統可成藥的蛋白（受體、酶、離子通道），所以訊號傳導與代謝類通路會被系統性高估——想消掉這個偏差請改用另一種母體。":
      "<b>모집단: 해당 데이터베이스에 수록된 전체 인간 유전자(학계 관례).</b> 이번 분석의 표본은 이 약재의 경로 주석이 있는 표적 유전자 <b>{0}</b>개이며, 모집단은 <b>{1}</b>개 유전자입니다. 「이 경로가 이 약재의 표적에서 전체 인간 유전자보다 더 자주 나타나는가」에 답합니다. TCMSP 표적은 원래 전통적으로 약물 표적이 되기 쉬운 단백질(수용체, 효소, 이온 채널)에 치우쳐 있어 신호 전달·대사 경로가 체계적으로 과대평가됩니다 — 이 편향을 없애려면 다른 모집단을 선택하세요.",
    "{0}：共檢定{1}條通路": "{0}: 경로 {1}개 검정",
    "（已排除{0}條非癌症疾病類通路）": " (비암 질환 경로 {0}개 제외)",
    "，{0}條達FDR q<0.05，": ", <b>{0}</b>개가 FDR q&lt;0.05 도달, ",
    "其中{0}條是獨立的基因組合（其餘與更高名次重疊≥80%，並列在報告裡會高估證據強度）；":
      "그중 <b>{0}</b>개는 독립적인 유전자 조합입니다(나머지는 상위 경로와 80% 이상 겹치며, 보고서에 나란히 쓰면 근거 강도가 과대평가됩니다). ",
    "以下依富集倍率排序，顯示前{0}條。": "농축 배수 순으로 정렬, 상위 {0}개 표시.",
    "以下依統計顯著性排序，顯示前{0}條。": "통계적 유의성 순으로 정렬, 상위 {0}개 표시.",

    "這張表在做什麼：通路富集分析回答一個問題：這個藥材打到的蛋白，有沒有不成比例地集中在某些生物過程上？用彈珠來想：袋子裡有{0}顆彈珠（母體＝該資料庫收錄的全部基因），其中某條通路佔了其中幾顆（＝「通路基因」欄）。你閉眼抓出{1}顆（＝這個藥材有通路註解的靶點基因）。如果抓到的數量遠多於隨機預期，這條通路就是「富集」了。整份分析就是把這件事對{2}條通路各做一次，再排序。":
      "<h4>이 표가 하는 일: 경로 농축 분석</h4><p>한 가지 질문에 답합니다: <b>이 약재가 맞히는 단백질이 특정 생물학적 과정에 불균형하게 몰려 있는가?</b></p><p>구슬로 생각해 보세요. 주머니에 구슬이 <b>{0}</b>개 있고(모집단 = 데이터베이스에 수록된 전체 유전자), 어떤 경로가 그중 몇 개를 차지합니다(= 「경로 유전자」 열). 눈을 감고 <b>{1}</b>개를 뽑습니다(= 이 약재의 경로 주석이 있는 표적 유전자). 뽑힌 수가 무작위 기대치보다 훨씬 많으면 그 경로가 「농축」된 것입니다.</p><p>전체 분석은 이 일을 <b>{2}</b>개 경로에 각각 한 번씩 한 뒤 정렬하는 것입니다.</p>",
    "# —名次目前排序方式下的名次。綠色代表這一列達FDR q<0.05。切成「依富集倍率」排序時，序號下方會多一行小字p #12，那是它在統計顯著性排序裡的名次。兩種排序都看一次比較不會漏——理由見「倍率」欄的說明。":
      "<h4># — 순위</h4><p>현재 정렬 방식에서의 순위입니다. <b>녹색</b>은 이 행이 FDR q&lt;0.05에 도달했다는 뜻입니다.</p><p>「농축 배수 순」으로 바꾸면 번호 아래에 작은 글씨 <code>p #12</code>가 한 줄 더 나오는데, 통계적 유의성 순서에서의 순위입니다. <b>두 정렬을 모두 한 번씩 보면 놓치는 것이 적습니다</b> — 이유는 「배수」 열 설명을 보세요.</p>",
    "通路—識別碼KEGG或Reactome給這條通路的唯一編號。hsa代表人類（Homo sapiens）。點一下編號就會在新分頁開啟原始通路圖。KEGG的連結會把這個藥材命中的基因直接標色——不只是「這條通路顯著」，而是看得到這些靶點落在通路圖的哪個位置、彼此的上下游關係是什麼。那才是判斷機轉是否說得通的依據。Reactome的連結會開啟PathwayBrowser。":
      "<h4>경로 — 식별자</h4><p>KEGG 또는 Reactome이 이 경로에 부여한 고유 번호입니다. <code>hsa</code>는 인간(Homo sapiens)을 뜻합니다.</p><p><b>번호를 클릭하면 새 탭에서 원본 경로도가 열립니다.</b></p><p>KEGG 링크는 <b>이 약재가 맞힌 유전자를 경로도에 직접 색으로 표시</b>합니다 — 「이 경로가 유의하다」는 것만이 아니라 이 표적들이 경로도의 어디에 있고 서로 상하류 관계가 어떤지 볼 수 있습니다. 그것이 기전이 타당한지 판단하는 근거입니다.</p><p>Reactome 링크는 PathwayBrowser를 엽니다.</p>",
    "名稱—這條通路在做什麼通路名稱。底下灰字是資料庫自己的分類階層，例如Environmental Information Processing / Signaling molecules and interaction前半是大類、後半是次類。分類很有用：一眼分辨這是核心訊號通路、代謝通路、還是疾病通路。標成癌症相關的是KEGG官方癌症分類，加上本平台另外標記的核心腫瘤訊號通路。標成重複的，代表它命中的基因有80%以上已經出現在更高名次的通路裡——那不是一項獨立發現，詳見「命中的基因」欄說明。":
      "<h4>이름 — 이 경로가 하는 일</h4><p>경로 이름입니다. 아래 회색 글씨는 데이터베이스 자체의 <b>분류 계층</b>으로, 예를 들어 <code>Environmental Information Processing / Signaling molecules and interaction</code>에서 앞부분이 대분류, 뒷부분이 소분류입니다.</p><p>분류를 보면 핵심 신호 경로인지, 대사 경로인지, 질환 경로인지 한눈에 알 수 있습니다. <b>암 관련</b>으로 표시된 것은 KEGG 공식 암 분류와 본 플랫폼이 별도로 표시한 핵심 종양 신호 경로입니다.</p><p><b>중복</b>으로 표시된 것은 맞힌 유전자의 80% 이상이 이미 상위 경로에 나왔다는 뜻입니다 — <span class=\"warn\">독립적인 발견이 아닙니다</span>. 「맞힌 유전자」 열 설명을 보세요.</p>",
    "命中—這個藥材打中這條通路的幾個基因這個藥材的{1}個靶點基因裡，有幾個落在這條通路內。它跟「通路基因」一起決定後面所有的數字。命中數太少（例如2、3個）時，就算倍率很高也不穩——換一份資料很可能就不見了。":
      "<h4>적중 — 이 약재가 이 경로에서 맞힌 유전자 수</h4><p>이 약재의 표적 유전자 <b>{1}</b>개 중 몇 개가 이 경로 안에 있는지입니다.</p><p>「경로 유전자」와 함께 뒤의 모든 수치를 결정합니다. <b>적중 수가 너무 적으면(예: 2~3개) 배수가 높아도 불안정합니다</b> — 다른 데이터에서는 사라질 가능성이 큽니다.</p>",
    "通路基因—這條通路總共有幾個基因這條通路在母體裡的總成員數，也就是富集計算的分母之一。這個數字會隨你選的母體改變。選「全人類基因」時是該通路在全基因體中的大小；選「全部中藥靶點」時，只算其中有被中藥靶點涵蓋到的部分，所以會小很多。兩者不能直接互相比較。":
      "<h4>경로 유전자 — 이 경로의 전체 유전자 수</h4><p>모집단 안에서 이 경로의 전체 구성원 수로, 농축 계산의 분모 중 하나입니다.</p><p><b>이 수치는 선택한 모집단에 따라 달라집니다.</b> 「전체 인간 유전자」를 선택하면 전체 유전체에서의 경로 크기이고, 「전체 한약 표적」을 선택하면 한약 표적이 포함하는 부분만 세므로 훨씬 작아집니다. 둘은 직접 비교할 수 없습니다.</p>",
    "倍率—效果有多強實際命中數÷隨機抽樣的期望命中數。倍率=（命中÷ {1}）÷（通路基因÷ {0}）倍率1.0表示跟隨機一樣、完全沒有富集；3.0表示比隨機預期多了三倍。倍率是「效果有多強」，p值是「有多不可能是巧合」——這兩件事最常被混為一談。一條有五百個基因的大通路很容易命中很多、p值很小，但倍率可能只有兩倍。注意：p值同時取決於倍率與絕對命中數，而命中數多則統計檢定力高，所以依p值排序會系統性偏袒基因數多的大通路，把高特異性的小通路往後推。這是富集分析的固有特性，不是程式問題——所以本頁提供「依倍率排序」。":
      "<h4>배수 — 효과가 얼마나 강한가</h4><p>실제 적중 수 ÷ 무작위 추출 시 기대 적중 수.</p><span class=\"formula\">배수 = (적중 ÷ {1}) ÷ (경로 유전자 ÷ {0})</span><p>배수 1.0은 무작위와 같아 농축이 전혀 없다는 뜻이고, 3.0은 무작위 기대치보다 세 배 많다는 뜻입니다.</p><p><b>배수는 「효과가 얼마나 강한가」, p값은 「우연일 가능성이 얼마나 낮은가」입니다 — 이 둘이 가장 자주 혼동됩니다.</b> 유전자가 오백 개인 큰 경로는 쉽게 많이 적중하고 p값도 매우 작지만, 배수는 두 배에 그칠 수 있습니다.</p><p class=\"warn\">주의: p값은 배수와 절대 적중 수에 모두 좌우되며, 적중 수가 많으면 검정력이 높아지므로 <b>p값 순 정렬은 유전자가 많은 큰 경로를 체계적으로 우대</b>하고 특이성이 높은 작은 경로를 뒤로 밉니다. 이는 농축 분석의 고유한 특성이지 프로그램 문제가 아니며, 그래서 이 페이지는 「배수 순 정렬」을 제공합니다.</p>",
    "p值—有多不可能是巧合如果這個藥材的靶點其實是隨機抽的，抓到這麼多（或更多）命中的機率有多大。用的是超幾何分布。1.73e-9就是0.00000000173，約十億分之1.7——機率極低，代表「隨機碰巧」這個解釋站不住腳。但判讀時請不要用p值，要用q值。原因見下一欄。":
      "<h4>p값 — 우연일 가능성이 얼마나 낮은가</h4><p>이 약재의 표적이 실제로는 무작위로 뽑힌 것이라면, 이만큼(또는 그 이상) 적중할 확률입니다. 초기하분포를 사용합니다.</p><p><code>1.73e-9</code>는 0.00000000173, 약 10억분의 1.7입니다 — 확률이 극히 낮아 「무작위 우연」이라는 설명은 성립하지 않습니다.</p><p class=\"warn\"><b>하지만 해석할 때는 p값이 아니라 q값을 쓰세요.</b> 이유는 다음 열을 보세요.</p>",
    "q值（FDR）—判讀請看這一欄p值有一個陷阱：你不是只檢驗一條通路，這次同時檢驗了{2}條。如果用p<0.05當標準，就算這些通路全部都是雜訊，光靠運氣也會有約5%通過。你會很開心地把它們寫進報告——而它們全是假的。q值（false discovery rate，Benjamini–Hochberg校正）已經把「你做了{2}次檢定」這件事算進去了。判讀規則：看q值，不看p值。q < 0.05才算顯著。q值一定大於或等於同一列的p值，這是校正的本質。":
      "<h4>q값 (FDR) — 해석은 이 열을 보세요</h4><p>p값에는 함정이 있습니다. 경로 하나만 검정하는 것이 아니라 이번에 <b>{2}</b>개를 동시에 검정했습니다.</p><p>p&lt;0.05를 기준으로 하면 <b>이 경로들이 모두 잡음이라도</b> 운만으로 약 5%가 통과합니다. 기쁘게 보고서에 쓰겠지만 — 전부 가짜입니다.</p><p>q값(false discovery rate, Benjamini–Hochberg 보정)은 「검정을 {2}번 했다」는 사실을 이미 반영했습니다.</p><span class=\"formula\">해석 규칙: p값이 아니라 q값을 보세요. q &lt; 0.05여야 유의합니다.</span><p>q값은 같은 행의 p값보다 항상 크거나 같습니다. 이것이 보정의 본질입니다.</p>",
    "命中的基因—以及為什麼「顯著通路數」會騙人這條通路裡被這個藥材打中的基因。粗體綠色是新出現的、灰色是更高名次已經出現過的，下方標「新增N / M個基因」。為什麼要這樣標：KEGG／Reactome的通路定義大量重疊，同一組基因會同時落在好幾條通路裡。實測人參的例子：Apoptosis命中BAX、BCL2、CASP3、CASP8、CASP9、MAPK8 p53 signaling BAX、BCL2、CASP3、CASP8、CASP9、CDK1 →六個裡有五個完全相同並列成兩項發現會被讀成交叉印證，實際上是同一個觀察被算了兩次。所以摘要行除了「顯著通路數」還會給「獨立發現數」——扣掉與更高名次重疊≥80%的之後還剩幾條。寫進報告要引用的是獨立發現數，不是顯著通路數。":
      "<h4>맞힌 유전자 — 그리고 「유의한 경로 수」가 속이는 이유</h4><p>이 경로에서 이 약재가 맞힌 유전자입니다. <b>굵은 녹색</b>은 새로 나온 것, <span class=\"sym-old\">회색</span>은 상위 경로에서 이미 나온 것이며, 아래에 「신규 N / M개 유전자」가 표시됩니다.</p><p><b>이렇게 표시하는 이유:</b> KEGG / Reactome의 경로 정의는 많이 겹쳐서 같은 유전자 묶음이 여러 경로에 동시에 들어갑니다. 인삼의 실제 예:</p><span class=\"formula\">Apoptosis 적중     BAX, BCL2, CASP3, CASP8, CASP9, MAPK8\np53 signaling      BAX, BCL2, CASP3, CASP8, CASP9, CDK1\n                   → 여섯 개 중 다섯 개가 동일</span><p>두 가지 발견으로 나란히 쓰면 교차 검증처럼 읽히지만, <span class=\"warn\">실제로는 같은 관찰을 두 번 센 것입니다</span>.</p><p>그래서 요약 줄에는 「유의한 경로 수」 외에 「<b>독립 발견 수</b>」도 표시합니다 — 상위 경로와 80% 이상 겹치는 것을 뺀 뒤 남는 수입니다. <b class=\"warn\">보고서에 인용할 것은 유의한 경로 수가 아니라 독립 발견 수입니다.</b></p>",

    // ---- 帶數字的短句（純文字，一般文字節點也會用到，見 site-lang.js convertText）----
    "{0}個成分": "성분 {0}개",
    "共{0}種藥材": "약재 {0}종",
    "篩選門檻OB ≥ {0}%、DL ≥ {1}": "선별 기준 OB ≥ {0}%, DL ≥ {1}",
    "已標準化（{0}%）": "표준화 완료 ({0}%)",
    "共{0}個活性成分": "활성 성분 {0}개",
    "共{0}個非活性成分": "비활성 성분 {0}개",
    "顯示{0} / {1}個": "{0} / {1}개 표시",
    "活性成分（OB ≥ {0}%、DL ≥ {1}）": "활성 성분 (OB ≥ {0}%, DL ≥ {1})",
    "資料來源：{0}": "데이터 출처: {0}",
    "新增{0} / {1}個基因": "신규 {0} / {1}개 유전자",
    "KEGG：{0}條靶點↔通路關聯，背景基因{1}，最後同步{2}": "KEGG: 표적↔경로 연관 {0}개, 배경 유전자 {1}개, 마지막 동기화 {2}",
    "Reactome：{0}條靶點↔通路關聯，背景基因{1}，最後同步{2}": "Reactome: 표적↔경로 연관 {0}개, 배경 유전자 {1}개, 마지막 동기화 {2}",
    "KEGG：{0}條靶點↔通路關聯，背景基因{1}，最後同步{2} Reactome：{3}條靶點↔通路關聯，背景基因{4}，最後同步{5}": "KEGG: 표적↔경로 연관 {0}개, 배경 유전자 {1}개, 마지막 동기화 {2}\nReactome: 표적↔경로 연관 {3}개, 배경 유전자 {4}개, 마지막 동기화 {5}",
  };

  window.I18N_BLOCKS = { en, ko };
})();
