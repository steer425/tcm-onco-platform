"""
GenCC 疾病名稱的預設翻譯種子資料（繁體中文／簡體中文／韓文）。

範圍：只涵蓋「已比對到 TCMSP 靶點」的疾病（`has_tcmsp_target=True`）——這是使用者
在查詢站實際會看到、會用到的子集，全部 3 萬筆逐一翻譯不切實際也沒有必要（沒比對到
中藥靶點的疾病，使用者在查詢站幾乎不會接觸到）。

依「英文疾病名稱（disease_title）」做比對，同一個疾病名稱可能對應資料庫裡好幾筆
不同的 GenccDisease 紀錄（同一個疾病被不同基因、不同審查小組各自提交），這支腳本
會一次把符合的全部紀錄都補上翻譯。

使用方式：
    python -m app.seed_gencc_translations

**只補目前是空值的欄位，不覆蓋既有翻譯**——如果後台已經有人手動編輯過某筆資料的
翻譯，這支腳本不會覆蓋掉，比照 disease_cn_name_seed.json（TCMSP 疾病中文名稱種子）
的做法。可以重複執行，也可以放心在補完後又手動修改個別筆資料，不用擔心下次執行
這支腳本時被洗掉。

擴充方式：之後如果匯入新版 GenCC 資料、比對到更多新的疾病，只要把新疾病的翻譯
加進下面的 TRANSLATIONS 字典，重新執行這支腳本即可補上，不需要清空重來。
"""
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal, engine, Base

# 格式：{英文疾病名稱: (繁體中文, 簡體中文, 韓文)}
TRANSLATIONS = {
    "ATM-related cancer predisposition": ("ATM相關癌症易感性", "ATM相关癌症易感性", "ATM 관련 암 감수성"),
    "BAP1-related tumor predisposition syndrome": ("BAP1相關腫瘤易感症候群", "BAP1相关肿瘤易感综合征", "BAP1 관련 종양 소인 증후군"),
    "BRCA1-related cancer predisposition": ("BRCA1相關癌症易感性", "BRCA1相关癌症易感性", "BRCA1 관련 암 감수성"),
    "Bannayan-Riley-Ruvalcaba syndrome": ("巴納揚-賴利-魯瓦爾卡巴症候群", "巴纳扬-赖利-鲁瓦尔卡巴综合征", "바나얀-라일리-루발카바 증후군"),
    "Berardinelli-Seip congenital lipodystrophy": ("貝拉迪內利-塞普先天性脂肪失養症", "贝拉迪内利-塞普先天性脂肪营养不良", "베라르디넬리-세이프 선천성 지방이영양증"),
    "Bruton-type agammaglobulinemia": ("布魯頓型無丙種球蛋白血症", "布鲁顿型无丙种球蛋白血症", "브루톤형 무감마글로불린혈증"),
    "Burkitt lymphoma": ("柏基特氏淋巴瘤", "伯基特淋巴瘤", "버킷 림프종"),
    "C3 glomerulonephritis": ("C3腎絲球腎炎", "C3肾小球肾炎", "C3 사구체신염"),
    "Costello syndrome": ("柯斯特洛症候群", "科斯特洛综合征", "코스텔로 증후군"),
    "Cowden disease": ("考登氏症", "考登病", "카우덴병"),
    "Cowden syndrome 1": ("考登症候群第1型", "考登综合征1型", "카우덴 증후군 1형"),
    "Ehlers-Danlos syndrome, periodontal type 1": ("埃勒斯-當洛斯症候群（牙周型1型）", "埃勒斯-当洛斯综合征（牙周型1型）", "엘러스-단로스 증후군(치주형 1형)"),
    "Ehlers-Danlos syndrome, periodontitis type": ("埃勒斯-當洛斯症候群（牙周炎型）", "埃勒斯-当洛斯综合征（牙周炎型）", "엘러스-단로스 증후군(치주염형)"),
    "FADD-related immunodeficiency": ("FADD相關免疫缺乏症", "FADD相关免疫缺陷病", "FADD 관련 면역결핍증"),
    "FG syndrome 4": ("FG症候群第4型", "FG综合征4型", "FG 증후군 4형"),
    "Fanconi anemia": ("范康尼氏貧血", "范可尼贫血", "판코니 빈혈"),
    "Fanconi anemia complementation group R": ("范康尼氏貧血互補群R", "范可尼贫血互补群R", "판코니 빈혈 상보군 R"),
    "Fanconi anemia, complementation group S": ("范康尼氏貧血互補群S", "范可尼贫血互补群S", "판코니 빈혈 상보군 S"),
    "Kury-Isidor syndrome": ("庫里-伊西多爾症候群", "库里-伊西多尔综合征", "쿠리-이시도르 증후군"),
    "Lhermitte-Duclos disease": ("萊爾米特-杜克洛斯氏病", "莱尔米特-杜克洛斯病", "레르미트-뒤클로병"),
    "Li-Fraumeni syndrome": ("李佛美尼症候群", "利-弗劳梅尼综合征", "리-프라우메니 증후군"),
    "Meier-Gorlin syndrome": ("邁爾-戈爾林症候群", "迈尔-戈林综合征", "마이어-고를린 증후군"),
    "Meier-Gorlin syndrome 4": ("邁爾-戈爾林症候群第4型", "迈尔-戈林综合征4型", "마이어-고를린 증후군 4형"),
    "Noonan syndrome": ("努南症候群", "努南综合征", "누난 증후군"),
    "Noonan syndrome 3": ("努南症候群第3型", "努南综合征3型", "누난 증후군 3형"),
    "PTEN hamartoma tumor syndrome": ("PTEN錯構瘤腫瘤症候群", "PTEN错构瘤肿瘤综合征", "PTEN 과오종 종양 증후군"),
    "Proteus-like syndrome": ("類普羅透斯症候群", "类普罗透斯综合征", "프로테우스 유사 증후군"),
    "RHO-related retinopathy": ("RHO相關視網膜病變", "RHO相关视网膜病变", "RHO 관련 망막병증"),
    "T-B+ severe combined immunodeficiency due to JAK3 deficiency": ("JAK3缺乏所致T-B+重度複合型免疫缺乏症", "JAK3缺乏所致T-B+重度联合免疫缺陷病", "JAK3 결핍으로 인한 T-B+ 중증복합면역결핍증"),
    "White-Kernohan syndrome": ("懷特-科諾漢症候群", "怀特-科诺汉综合征", "화이트-커노한 증후군"),
    "X-linked syndromic intellectual disability": ("X連鎖症候群型智能障礙", "X连锁综合征型智力障碍", "X연관 증후군성 지적장애"),
    "activated PI3K-delta syndrome": ("活化型PI3K-delta症候群", "活化型PI3K-delta综合征", "활성화 PI3K-델타 증후군"),
    "amyotrophic lateral sclerosis": ("肌萎縮性側索硬化症（漸凍症）", "肌萎缩侧索硬化症（渐冻症）", "근위축성 측삭경화증(루게릭병)"),
    "amyotrophic lateral sclerosis type 6": ("肌萎縮性側索硬化症第6型", "肌萎缩侧索硬化症6型", "근위축성 측삭경화증 6형"),
    "arrhythmogenic right ventricular cardiomyopathy": ("致心律不整性右心室心肌病變", "致心律失常性右室心肌病", "부정맥성 우심실 심근병증"),
    "ataxia telangiectasia": ("運動失調微血管擴張症", "共济失调毛细血管扩张症", "모세혈관확장성 운동실조증"),
    "atrioventricular block": ("房室傳導阻滯", "房室传导阻滞", "방실 차단"),
    "atypical hemolytic-uremic syndrome with C3 anomaly": ("伴C3異常之非典型溶血性尿毒症候群", "伴C3异常的非典型溶血性尿毒综合征", "C3 이상을 동반한 비정형 용혈성 요독 증후군"),
    "autoimmune lymphoproliferative syndrome type 2B": ("自體免疫淋巴增生症候群第2B型", "自身免疫性淋巴增殖综合征2B型", "자가면역 림프증식 증후군 2B형"),
    "autoimmune lymphoproliferative syndrome type 4": ("自體免疫淋巴增生症候群第4型", "自身免疫性淋巴增殖综合征4型", "자가면역 림프증식 증후군 4형"),
    "autoinflammation with arthritis and vasculitis": ("伴關節炎與血管炎之自體發炎症", "伴关节炎与血管炎的自身炎症性疾病", "관절염과 혈관염을 동반한 자가염증"),
    "autoinflammation, immune dysregulation, and eosinophilia": ("自體發炎、免疫失調與嗜酸性球增多症", "自身炎症、免疫失调与嗜酸性粒细胞增多症", "자가염증, 면역조절이상, 호산구증가증"),
    "autosomal dominant non-syndromic intellectual disability": ("體染色體顯性非症候群型智能障礙", "常染色体显性非综合征型智力障碍", "상염색체 우성 비증후군성 지적장애"),
    "autosomal systemic lupus erythematosus type 16": ("體染色體型全身性紅斑性狼瘡第16型", "常染色体型系统性红斑狼疮16型", "상염색체 전신홍반루푸스 16형"),
    "breast-ovarian cancer, familial, susceptibility to, 1": ("家族性乳癌卵巢癌易感性第1型", "家族性乳腺癌卵巢癌易感性1型", "가족성 유방-난소암 감수성 1형"),
    "cardiofaciocutaneous syndrome": ("心臉皮症候群", "心-面-皮肤综合征", "심장-안면-피부 증후군"),
    "cardiofaciocutaneous syndrome 2": ("心臉皮症候群第2型", "心-面-皮肤综合征2型", "심장-안면-피부 증후군 2형"),
    "cerebral palsy": ("腦性麻痺", "脑瘫", "뇌성마비"),
    "colorectal cancer": ("大腸直腸癌", "结直肠癌", "대장암"),
    "complement component 3 deficiency": ("補體第3成分缺乏症", "补体第3成分缺乏症", "보체 3 결핍증"),
    "complement component 5 deficiency": ("補體第5成分缺乏症", "补体第5成分缺乏症", "보체 5 결핍증"),
    "complex neurodevelopmental disorder": ("複雜型神經發展障礙", "复杂型神经发育障碍", "복합 신경발달장애"),
    "congenital heart disease": ("先天性心臟病", "先天性心脏病", "선천성 심장병"),
    "congenital prothrombin deficiency": ("先天性凝血酶原缺乏症", "先天性凝血酶原缺乏症", "선천성 프로트롬빈 결핍증"),
    "congenital stationary night blindness": ("先天性固定型夜盲症", "先天性静止性夜盲症", "선천성 정지형 야맹증"),
    "congenital stationary night blindness autosomal dominant 1": ("先天性固定型夜盲症體染色體顯性第1型", "先天性静止性夜盲症常染色体显性1型", "선천성 정지형 야맹증 상염색체 우성 1형"),
    "dilated cardiomyopathy 1I": ("擴張型心肌病變第1I型", "扩张型心肌病1I型", "확장성 심근병증 1I형"),
    "ectodermal dysplasia with facial dysmorphism and acral, ocular, and brain anomalies": ("伴顏面畸形及肢端、眼部、腦部異常之外胚層發育不良", "伴面部畸形及肢端、眼部、脑部异常的外胚层发育不良", "안면기형 및 사지, 안구, 뇌 이상을 동반한 외배엽형성이상"),
    "encephalopathy, acute, infection-induced (herpes-specific), susceptibility to, 8": ("感染誘發性（皰疹特異性）急性腦病變易感性第8型", "感染诱发性（疱疹特异性）急性脑病易感性8型", "감염 유발성(헤르페스 특이) 급성 뇌병증 감수성 8형"),
    "familial atypical multiple mole melanoma syndrome": ("家族性非典型多發痣黑色素瘤症候群", "家族性非典型多发痣黑色素瘤综合征", "가족성 비정형 다발성 모반 흑색종 증후군"),
    "familial colorectal cancer": ("家族性大腸直腸癌", "家族性结直肠癌", "가족성 대장암"),
    "familial congenital mirror movements": ("家族性先天性鏡像運動", "家族性先天性镜像运动", "가족성 선천성 거울운동"),
    "familial isolated dilated cardiomyopathy": ("家族性孤立型擴張型心肌病變", "家族性孤立型扩张型心肌病", "가족성 고립성 확장성 심근병증"),
    "familial thrombocytosis": ("家族性血小板增多症", "家族性血小板增多症", "가족성 혈소판증가증"),
    "frontotemporal dementia and/or amyotrophic lateral sclerosis 4": ("額顳葉型失智症合併/或肌萎縮性側索硬化症第4型", "额颞叶痴呆合并/或肌萎缩侧索硬化症4型", "전두측두엽 치매 및/또는 근위축성 측삭경화증 4형"),
    "frontotemporal dementia with motor neuron disease": ("伴運動神經元病之額顳葉型失智症", "伴运动神经元病的额颞叶痴呆", "운동신경세포병을 동반한 전두측두엽 치매"),
    "fundus albipunctatus": ("眼底白點症", "眼底白点症", "안저백점증"),
    "gastric carcinoma": ("胃癌", "胃癌", "위암"),
    "genetic developmental and epileptic encephalopathy": ("遺傳性發展性癲癇性腦病變", "遗传性发育性癫痫性脑病", "유전성 발달 및 뇌전증성 뇌병증"),
    "glioma susceptibility 2": ("神經膠質瘤易感性第2型", "胶质瘤易感性2型", "신경교종 감수성 2형"),
    "hereditary breast carcinoma": ("遺傳性乳癌", "遗传性乳腺癌", "유전성 유방암"),
    "hereditary breast ovarian cancer syndrome": ("遺傳性乳癌卵巢癌症候群", "遗传性乳腺癌卵巢癌综合征", "유전성 유방-난소암 증후군"),
    "hereditary nonpolyposis colon cancer": ("遺傳性非息肉症大腸癌（林奇症候群）", "遗传性非息肉病性结肠癌（林奇综合征）", "유전성 비용종증 대장암(린치 증후군)"),
    "hyper-IgM syndrome type 3": ("高IgM症候群第3型", "高IgM综合征3型", "고IgM 증후군 3형"),
    "idiopathic juvenile osteoporosis": ("特發性青少年骨質疏鬆症", "特发性青少年骨质疏松症", "특발성 소아 골다공증"),
    "immunodeficiency 123 with HPV-related verrucosis": ("伴HPV相關疣狀增生之免疫缺乏症第123型", "伴HPV相关疣状增生的免疫缺陷病123型", "HPV 관련 사마귀증을 동반한 면역결핍증 123형"),
    "immunodeficiency 79": ("免疫缺乏症第79型", "免疫缺陷病79型", "면역결핍증 79형"),
    "immunodeficiency 82 with systemic inflammation": ("伴全身性發炎之免疫缺乏症第82型", "伴全身性炎症的免疫缺陷病82型", "전신염증을 동반한 면역결핍증 82형"),
    "intellectual disability": ("智能障礙", "智力障碍", "지적장애"),
    "intellectual disability, autosomal dominant 58": ("智能障礙體染色體顯性第58型", "智力障碍常染色体显性58型", "지적장애 상염색체 우성 58형"),
    "isolated growth hormone deficiency type III": ("孤立性生長激素缺乏症第III型", "孤立性生长激素缺乏症III型", "고립성 성장호르몬 결핍증 III형"),
    "juvenile amyotrophic lateral sclerosis": ("幼年型肌萎縮性側索硬化症", "青少年型肌萎缩侧索硬化症", "청소년형 근위축성 측삭경화증"),
    "leiomyosarcoma": ("平滑肌肉瘤", "平滑肌肉瘤", "평활근육종"),
    "lessel-kubisch syndrome": ("萊塞爾-庫比施症候群", "莱塞尔-库比施综合征", "레셀-쿠비쉬 증후군"),
    "leukemia, acute lymphocytic, susceptibility to, 1": ("急性淋巴性白血病易感性第1型", "急性淋巴细胞白血病易感性1型", "급성 림프구성 백혈병 감수성 1형"),
    "linear nevus sebaceous syndrome": ("線狀皮脂腺母斑症候群", "线状皮脂腺痣综合征", "선상 피지선모반 증후군"),
    "macrocephaly-autism syndrome": ("巨頭症合併自閉症候群", "巨头畸形-自闭症综合征", "대두증-자폐 증후군"),
    "macrocephaly-intellectual disability-neurodevelopmental disorder-small thorax syndrome": ("巨頭症-智能障礙-神經發展障礙-小胸腔症候群", "巨头畸形-智力障碍-神经发育障碍-小胸腔综合征", "대두증-지적장애-신경발달장애-소흉곽 증후군"),
    "melanoma and neural system tumor syndrome": ("黑色素瘤合併神經系統腫瘤症候群", "黑色素瘤合并神经系统肿瘤综合征", "흑색종 및 신경계 종양 증후군"),
    "melanoma, cutaneous malignant, susceptibility to, 2": ("皮膚惡性黑色素瘤易感性第2型", "皮肤恶性黑色素瘤易感性2型", "피부 악성 흑색종 감수성 2형"),
    "melanoma-pancreatic cancer syndrome": ("黑色素瘤-胰臟癌症候群", "黑色素瘤-胰腺癌综合征", "흑색종-췌장암 증후군"),
    "methylmalonic acidemia due to transcobalamin receptor defect": ("轉鈷胺素受體缺陷所致甲基丙二酸血症", "转钴胺素受体缺陷所致甲基丙二酸血症", "트랜스코발라민 수용체 결함으로 인한 메틸말론산혈증"),
    "microcephaly 30, primary, autosomal recessive": ("原發性體染色體隱性小頭症第30型", "原发性常染色体隐性小头畸形30型", "원발성 상염색체 열성 소두증 30형"),
    "mirror movements 2": ("鏡像運動第2型", "镜像运动2型", "거울운동 2형"),
    "mosaic variegated aneuploidy syndrome": ("鑲嵌型多樣性非整倍體症候群", "嵌合型多变异倍体综合征", "모자이크 다양성 이수성 증후군"),
    "myofibrillar myopathy 1": ("肌原纖維肌病變第1型", "肌原纤维肌病1型", "근원섬유병증 1형"),
    "neurodevelopmental disorder": ("神經發展障礙", "神经发育障碍", "신경발달장애"),
    "neurodevelopmental disorder with cardiomyopathy, spasticity, and brain abnormalities": ("伴心肌病變、痙攣及腦部異常之神經發展障礙", "伴心肌病、痉挛及脑部异常的神经发育障碍", "심근병증, 경직, 뇌이상을 동반한 신경발달장애"),
    "neurodevelopmental disorder with dysmorphic facies, sleep disturbance, and brain abnormalities": ("伴顏面畸形、睡眠障礙及腦部異常之神經發展障礙", "伴面部畸形、睡眠障碍及脑部异常的神经发育障碍", "안면기형, 수면장애, 뇌이상을 동반한 신경발달장애"),
    "neurogenic scapuloperoneal syndrome, Kaeser type": ("凱瑟型神經性肩胛腓骨症候群", "凯瑟型神经源性肩胛腓骨综合征", "카에저형 신경성 견갑비골 증후군"),
    "osteogenesis imperfecta type 15": ("成骨不全症第15型", "成骨不全15型", "골형성부전증 15형"),
    "osteogenesis imperfecta type 17": ("成骨不全症第17型", "成骨不全17型", "골형성부전증 17형"),
    "osteogenesis imperfecta type 3": ("成骨不全症第3型", "成骨不全3型", "골형성부전증 3형"),
    "osteogenesis imperfecta type 4": ("成骨不全症第4型", "成骨不全4型", "골형성부전증 4형"),
    "overgrowth syndrome and/or cerebral malformations due to abnormalities in MTOR pathway genes": ("MTOR路徑基因異常所致過度生長症候群合併/或腦部畸形", "MTOR通路基因异常所致过度生长综合征合并/或脑部畸形", "MTOR 경로 유전자 이상으로 인한 과성장 증후군 및/또는 뇌기형"),
    "pancreatic cancer, susceptibility to, 4": ("胰臟癌易感性第4型", "胰腺癌易感性4型", "췌장암 감수성 4형"),
    "prostate cancer": ("攝護腺癌", "前列腺癌", "전립선암"),
    "renal cell carcinoma": ("腎細胞癌", "肾细胞癌", "신세포암"),
    "retinitis pigmentosa": ("視網膜色素變性", "视网膜色素变性", "망막색소변성증"),
    "retinitis pigmentosa 4": ("視網膜色素變性第4型", "视网膜色素变性4型", "망막색소변성증 4형"),
    "sarcoma": ("肉瘤", "肉瘤", "육종"),
    "short stature due to isolated growth hormone deficiency with X-linked hypogammaglobulinemia": ("伴X連鎖低丙種球蛋白血症之孤立性生長激素缺乏所致身材矮小", "伴X连锁低丙种球蛋白血症的孤立性生长激素缺乏所致身材矮小", "X연관 저감마글로불린혈증을 동반한 고립성 성장호르몬 결핍으로 인한 저신장증"),
    "syndromic X-linked intellectual disability Najm type": ("納吉姆型X連鎖症候群型智能障礙", "纳吉姆型X连锁综合征型智力障碍", "나짐형 X연관 증후군성 지적장애"),
    "thrombocythemia 3": ("血小板增多症第3型", "血小板增多症3型", "혈소판증가증 3형"),
    "thrombocytopenia 6": ("血小板減少症第6型", "血小板减少症6型", "혈소판감소증 6형"),
    "thrombophilia due to thrombin defect": ("凝血酶缺陷所致血栓形成傾向", "凝血酶缺陷所致血栓形成倾向", "트롬빈 결함으로 인한 혈전성향증"),
    "tremor, hereditary essential, 4": ("遺傳性原發性顫抖症第4型", "遗传性原发性震颤4型", "유전성 본태성 진전 4형"),
}


def seed_gencc_translations(db: Session):
    updated_count = 0
    skipped_existing = 0
    not_found_titles = []

    for disease_title, (tw, cn, ko) in TRANSLATIONS.items():
        rows = db.query(models.GenccDisease).filter(models.GenccDisease.disease_title == disease_title).all()
        if not rows:
            not_found_titles.append(disease_title)
            continue
        for row in rows:
            changed = False
            # 只補空值，不覆蓋既有翻譯（可能是後台已經手動編輯過的內容）
            if not row.disease_cn_name:
                row.disease_cn_name = tw
                changed = True
            if not row.disease_name_cn:
                row.disease_name_cn = cn
                changed = True
            if not row.disease_name_ko:
                row.disease_name_ko = ko
                changed = True
            if changed:
                updated_count += 1
            else:
                skipped_existing += 1

    db.commit()
    print(f"完成！更新 {updated_count} 筆紀錄的翻譯（只補空值欄位）、{skipped_existing} 筆已有完整翻譯不需更動。")
    if not_found_titles:
        print(f"注意：{len(not_found_titles)} 個疾病名稱在資料庫裡找不到對應紀錄（可能是資料還沒匯入，或名稱有出入）：")
        for t in not_found_titles:
            print("  -", t)


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_gencc_translations(db)
    finally:
        db.close()
