# 内置跨语言术语表（builtin，机器可读）

**用途**：为跨语种 known-item 检索提供确定性的术语对齐基座。脚本 `scripts/cards.py`
读下方 `tsv` 代码块（制表符分列），据此生成「概念 → 各语种写法」索引，用于
①从问题文本抽取概念锚点；②生成逐语种查询式；③做术语回译（逆映射）复核。

**来源与许可**：作者自编，依据公开的通用科研方法学词汇（流行病学/临床研究/文献计量
的常用术语）整理，不含任何具体案例的标题、作者或答案。许可 MIT，可自由复用与扩展。

**字段**：`cid`（概念号）｜`en`｜`pt`｜`es`｜`fr`｜`de`，同一语种多个写法用 `;` 分隔。

**扩展方法**：新增一行即可（保持 cid 唯一、按概念而非按文献组织）；脚本无需改动。
术语表只覆盖「概念级」对齐，不覆盖个案专名（人名、机构、期刊名、疾病亚型），
专名靠 `DOI / 引号短语 / 作者姓 / 年份` 四个专名锚点匹配，避免术语表把无关文献拉进来。

**边界**：这是有限词典，不是机器翻译。术语表未收录的概念会在
`false_positive_check.risks` 里标 `review`，并在 `pending_human` 提示人工核对，
脚本绝不臆造译法。

```tsv
cid	en	pt	es	fr	de
G01	systematic review	revisão sistemática	revisión sistemática	revue systématique	systematische Übersicht
G02	meta-analysis	metanálise;meta-análise	metaanálisis;meta-análisis	méta-analyse	Metaanalyse
G03	randomized controlled trial	ensaio clínico randomizado;ensaio clínico aleatorizado	ensayo clínico aleatorizado	essai contrôlé randomisé	randomisierte kontrollierte Studie
G04	clinical trial	ensaio clínico	ensayo clínico	essai clinique	klinische Studie
G05	cohort study	estudo de coorte	estudio de cohorte	étude de cohorte	Kohortenstudie
G06	cross-sectional study	estudo transversal	estudio transversal	étude transversale	Querschnittsstudie
G07	case-control study	estudo caso-controle	estudio de casos y controles	étude cas-témoins	Fall-Kontroll-Studie
G08	sample size	tamanho da amostra	tamaño de la muestra	taille de l'échantillon	Stichprobengröße
G09	participants	participantes;voluntários	participantes;voluntarios	participants	Teilnehmende
G10	mortality	mortalidade	mortalidad	mortalité	Sterblichkeit
G11	incidence	incidência	incidencia	incidence	Inzidenz
G12	prevalence	prevalência	prevalencia	prévalence	Prävalenz
G13	sensitivity	sensibilidade	sensibilidad	sensibilité	Sensitivität
G14	specificity	especificidade	especificidad	spécificité	Spezifität
G15	diagnostic accuracy	acurácia diagnóstica;acuidade diagnóstica	exactitud diagnóstica	exactitude diagnostique	diagnostische Genauigkeit
G16	biomarker	biomarcador	biomarcador	biomarqueur	Biomarker
G17	gene expression	expressão gênica;expressão génica	expresión génica	expression génique	Genexpression
G18	protein	proteína	proteína	protéine	Protein
G19	cell	célula	célula	cellule	Zelle
G20	tissue	tecido	tejido	tissu	Gewebe
G21	animal model	modelo animal	modelo animal	modèle animal	Tiermodell
G22	questionnaire	questionário	cuestionario	questionnaire	Fragebogen
G23	qualitative study	estudo qualitativo	estudio cualitativo	étude qualitative	qualitative Studie
G24	longitudinal	longitudinal	longitudinal	longitudinal	Längsschnitt
G25	follow-up	seguimento;acompanhamento	seguimiento	suivi	Nachbeobachtung
G26	statistical significance	significância estatística	significación estadística	signification statistique	statistische Signifikanz
G27	confidence interval	intervalo de confiança	intervalo de confianza	intervalle de confiance	Konfidenzintervall
G28	regression	regressão	regresión	régression	Regression
G29	validation	validação	validación	validation	Validierung
G30	cross-cultural adaptation	adaptação transcultural	adaptación transcultural	adaptation transculturelle	kulturelle Anpassung
G31	translation	tradução	traducción	traduction	Übersetzung
G32	reproducibility	reprodutibilidade	reproducibilidad	reproductibilité	Reproduzierbarkeit
G33	open access	acesso aberto	acceso abierto	accès ouvert	Open Access
G34	peer review	revisão por pares	revisión por pares	évaluation par les pairs	Peer Review
G35	informed consent	consentimento informado	consentimiento informado	consentement éclairé	informierte Einwilligung
G36	ethics approval	aprovação ética;comitê de ética	aprobación ética	approbation éthique	Ethikvotum
G37	funding	financiamento	financiamiento	financement	Finanzierung
G38	conflict of interest	conflito de interesses	conflicto de intereses	conflit d'intérêts	Interessenkonflikt
G39	supplementary material	material suplementar	material suplementario	matériel supplémentaire	Zusatzmaterial
G40	primary care	atenção primária;atenção básica	atención primaria	soins primaires	Primärversorgung
G41	public health	saúde pública	salud pública	santé publique	öffentliche Gesundheit
G42	mental health	saúde mental	salud mental	santé mentale	psychische Gesundheit
G43	nursing	enfermagem	enfermería	soins infirmiers	Pflege
G44	pregnancy	gestação;gravidez	embarazo	grossesse	Schwangerschaft
G45	children	crianças	niños	enfants	Kinder
G46	elderly	idosos;pessoas idosas	adultos mayores	personnes âgées	Ältere
G47	diabetes	diabetes	diabetes	diabète	Diabetes
G48	hypertension	hipertensão	hipertensión	hypertension	Hypertonie
G49	vaccine	vacina	vacuna	vaccin	Impfstoff
G50	antimicrobial resistance	resistência antimicrobiana	resistencia antimicrobiana	résistance antimicrobienne	Antibiotikaresistenz
G51	telehealth	telessaúde;telemedicina	telesalud	télésanté	Telemedizin
G52	cost-effectiveness	custo-efetividade	costo-efectividad	rapport coût-efficacité	Kosteneffektivität
G53	health education	educação em saúde	educación para la salud	éducation à la santé	Gesundheitserziehung
G54	machine learning	aprendizado de máquina;aprendizagem de máquina	aprendizaje automático	apprentissage automatique	maschinelles Lernen
G55	dataset	conjunto de dados	conjunto de datos	jeu de données	Datensatz
G56	interview	entrevista	entrevista	entretien	Interview
G57	survey	inquérito;levantamento	encuesta	enquête	Umfrage
G58	scale	escala	escala	échelle	Skala
G59	adherence	adesão	adherencia	observance	Adhärenz
G60	quality of life	qualidade de vida	calidad de vida	qualité de vie	Lebensqualität
```

## 停用词与检索动作词（同一文件，机器可读）

分词后用于「内容词」提取：这些词不参与锚点打分，避免检索动作词（search/find/找到/检索）
把无关视图拉高。`q` 行是问题句式里的动作词与元词。

```tsv-stop
lang	words
en	a an the of and or to in on for with by from as at is are was were be been being this that these those it its their our we you they he she not no more than then there here which who whom whose what when where how why all any both each few most other some such only own same so too very can will just should now about into over under between among during before after above below up down out off again further once because while if but nor do does did doing have has had having me my mine
pt	de da do das dos que os as um uma para com nao em por mais como tambem entre sobre foram foi ser seu sua pelo pela nas nos ao se numa num sao esta estao esse essa este esta
es	el la los las del y es son fue fueron su sus al mas estos datos este esta para con por como entre sobre se
fr	les des et est dans pour qui aux sur avec pas plus par sont au du une le ce cette ces nous il elle ils elles son sa
de	der die das und den von mit ist im zu sich des auf fur nicht werden wird auch bei aus dem ein eine als diese
it	il lo la gli le di che e per con non sono una del della nel piu anche questo questa
q	search find locate identify retrieve paper article study studies research report journal author authors published publication year title doi please want need looking known item exact version translation abstract full text
```

```tsv-stop
lang	words
q	frage pregunta pergunta questao questão objetivo objective objective_ method methods resultado resultados result results tabela table figura figure doi isbn issn http https www org com br
q	the this that these those study research paper article journal revista universidade university school department institute center centre faculty hospital clinica clinic english portuguese spanish french german brazil brasil portugal lisboa paulo janeiro resumo abstract introduction methods results discussion conclusion references figure table version original translation duplicate skill agent draft team system page january february march april may june july august september october november december data based using used between during aims objective background findings
```
