# ProjectLens AI Ogrenme Notlari

Bu dosya, projeyi yaparken kavramlari sade sekilde hatirlamak icin var.

## Ayak 1: Scanner

Scanner, bir kod reposunun odalarini gezen kisi gibidir. Henuz AI kullanmaz.
Klasorleri, dosyalari, README dosyasini, testleri ve Python fonksiyon/class
isimlerini yerelde okur.

Bu asamada amacimiz su soruya cevap vermek:

> ProjectLens repoyu guvenli ve tekrar edilebilir sekilde haritalayabiliyor mu?

AI, embedding, MCP ve hybrid search daha sonraki ayaklarda eklenecek.

## Akilda Tutulacak Mimari

ProjectLens su anda ana hatlariyla su parcalardan olusuyor:

- `scanner`: repoyu yerelde gezer ve ham harita cikarir.
- `packer`: bu haritayi AI'a verilebilir duzenli rapora cevirir.
- `search`: soru ile alakali dosyalari AI kullanmadan bulur.
- `index_store`: scan sonucunu yerel SQLite veritabanina kaydeder.
- `chunks`: kodu fonksiyon/class/dosya parcalarina ayirir.
- `embeddings`: local/openai/disabled backend durumunu yonetir.
- `embedding_store`: hazir backend ile chunk vektorlerini SQLite'a yazar.
- `semantic_search`: soru vektoru ile kayitli chunk vektorlerini karsilastirir.
- `config`: kullanicinin yerel ayarlarini saklar.
- `cli`: terminalden komut vermeni saglar.
- `tests`: ekledigimiz seyler bozuluyor mu kontrol eder.

Bu dosya proje boyunca ders defteri gibi kullanilacak. Yeni kavramlar,
kararlar ve mimari ozetleri gerektikce buraya eklenecek.

## Search Katmani: Ilk Surum

`search`, AI cevabi uretmez. Sadece bir soruyla alakali olabilecek dosyalari
bulur. Bu bilincli bir ayrimdir: once dogru dosyayi bulma kalitesini olceriz,
sonra AI cevap katmanini ekleriz.

Ilk search surumu uc ucuz kanit kullanir:

- keyword: dosya iceriginde kelime geciyor mu?
- symbol: fonksiyon/class adinda eslesme var mi?
- path: dosya yolu veya dosya adi ipucu veriyor mu?

Embedding eklenince sistem semantic search yapabilir. Ileride bu iki taraf
birlesince hybrid search olacak: aciklanabilir arama + anlamsal arama birlikte
calisacak.

## SQLite Index Katmani

`index`, scan sonucunu her seferinde yeniden hesaplamak yerine yerel bir
veritabanina kaydeder. Dosya yolu sudur:

`.projectlens/index.sqlite`

SQLite'i kucuk bir dosya icinde duran tablo defteri gibi dusunebilirsin. Bu
asamada su tablolar tutulur:

- `metadata`: repo kok yolu, olusturma zamani, teknoloji listesi gibi genel bilgiler.
- `files`: taranan dosyalar, boyutlari, uzantilari ve rolleri.
- `symbols`: Python fonksiyon/class kayitlari.
- `imports`: Python import kayitlari.
- `chunks`: embedding ve semantic search icin kod parcalari.
- `embeddings`: chunk'larin sayisal vektorleri.

Komutlar:

- `projectlens index .`: index dosyasini olusturur veya gunceller.
- `projectlens status .`: index var mi, kac dosya/symbol/chunk kayitli gosterir.
- `projectlens search "database connection" . --indexed`: canli scan yerine kaydedilmis index'i kullanir.

## Config Katmani

`config`, ProjectLens'in ayar defteridir. Dosya yolu sudur:

`.projectlens/config.toml`

Bu dosya git'e eklenmez; cunku kullanicinin kendi makinesine ve tercihine bagli
ayarlar tasir. Ornek dosya olarak `config-example.toml` repoda tutulur.

Su anda onemli ayarlar:

- `embedding.backend = "local"`: ucretsiz varsayilan mod; kod makinede kalir.
- `embedding.backend = "openai"`: ileride daha kaliteli semantic search icin API kullanir.
- `embedding.backend = "disabled"`: embedding kapali; keyword/symbol/path search calismaya devam eder.
- `llm.provider = "none"`: henuz standalone cevap uretimi yok.
- `runtime.privacy_mode = true`: varsayilan olarak gizlilik dostu davran.

Komutlar:

- `projectlens config init .`: varsayilan config dosyasini olusturur.
- `projectlens config show .`: mevcut/effective ayarlari gosterir.
- `projectlens config set embedding.backend openai .`: embedding backend ayarini degistirir.

## Embedding Katmani

Embedding, bir metin veya kod parcasini sayisal vektore cevirme isidir. Bu
vektorleri anlam koordinati gibi dusunebilirsin. Iki parca anlam olarak yakinsa
vektorleri de birbirine yakin olur.

Burada uc farkli durum var ve bunlari ayirmak onemli:

- Paket kurulu: `sentence-transformers` gibi Python kutuphanesi var.
- Model hazir: `all-MiniLM-L6-v2` gibi asil model dosyalari cache'te var ve yuklenebiliyor.
- Repo embedding'i hazir: bu repodaki chunk'larin vektorleri SQLite'a yazilmis.

Onceki uzun bekleme bu ayrim net olmadigi icin oldu. Sistem paket kurulu diye
tam repo build'e girdi, ama model indirme/yukleme asamasinda sessizce bekledi.
Simdi akisi guvenli hale getirdik:

- `projectlens embed status .`: paket/backend durumunu gosterir.
- `projectlens embed test .`: model cache'te mi, tek kucuk metinle test eder.
- `projectlens embed test . --download-model`: model yoksa indirmeye acik izin verir.
- `projectlens embed build .`: model hazirsa repo chunk vektorlerini yazar.
- `projectlens embed build . --limit 5`: sadece ilk 5 chunk ile kucuk deneme yapar.
- `projectlens search "database connection" . --semantic`: kayitli embedding varsa semantic search yapar.

Onemli ayrim:

- keyword/symbol/path search hemen calisir.
- semantic search icin model + repo embedding'i gerekir.
- model hazir degilse sistem bozulmaz; acik hata mesaji verir ve ne yapacagini soyler.

## Local Embedding Neden Ucretsiz?

Local embedding, modeli senin bilgisayarinda calistirir. API'ye metin gondermez,
bu yuzden kullanim basina ucret yoktur. Bedeli para degil; disk alani, ilk
indirme suresi ve bilgisayarin islem gucudur.

OpenAI embedding ise modeli bulutta calistirir. Kurulumu daha hafif olabilir ve
kalitesi bazi durumlarda daha iyi olabilir, ama kod parcalarini API'ye gonderir
ve kullanim ucreti dogurur.
## Bug Dersi: Uzun Suren Model Indirme

Bu adimda `projectlens embed test . --download-model` ilk denemede cok uzun
surdu. Sebep ProjectLens'in repo taramasi degildi; Hugging Face model indirme
katmani takiliyordu.

Cozum su oldu:

- once tam repo build yerine tek metinlik `embed test` kullandik,
- sonra model indirmeyi dogrudan Hugging Face cache'e aldik,
- `HF_HUB_DISABLE_XET=1` ile problemli xet indirme katmanini kapattik,
- bu ayari ProjectLens local backend icinde varsayilan yaptik,
- model hazir olunca tam repo build 152 chunk icin yaklasik saniyeler icinde bitti.

Buradaki profesyonel ders: Bir AI/ML ozelliginde "paket kurulu" demek "model
hazir" demek degildir. Uc ayri kapi vardir: kutuphane kurulu mu, model dosyasi
cache'te mi, bu repo icin embedding vektorleri uretilmis mi?

Son durum:

- `projectlens embed test .`: local model yukleniyor ve 384 boyutlu vektor uretiyor.
- `projectlens embed build .`: 152 chunk icin 152 embedding vektorunu SQLite'a yazdi.
- `projectlens search "database connection" . --semantic`: kayitli vektorlerle semantic search yapiyor.

## Semantic Search Kalite Dersi

Ilk semantic search sonucunda test dosyalari ust siraya cikti. Bu tamamen hata
degildi; testler de ilgili kelimeleri tasiyordu. Ama kullanici genelde once
kaynak kodu okumak ister. Bu yuzden semantic search sonucuna `role` bilgisini
ekledik ve test dosyalarini sadece soru testlerle ilgiliyse one cikacak sekilde
ayarladik.

Bu bize hybrid search mantigini ogretir: En iyi arama sistemi tek bir skora
körü korüne guvenmez. Semantic skor onemlidir, ama dosya rolu, path, symbol ve
kullanicinin niyetiyle birlikte degerlendirilmelidir.
## Hybrid Search Katmani

Hybrid search, tek bir arama yontemine guvenmek yerine birden fazla kaniti
birlikte kullanir. Bunu bir ise alim mulakatindaki aday degerlendirmesi gibi
dusunebilirsin: sadece CV'ye bakmazsin, teknik test, proje, referans ve gorusme
performansini birlikte tartarsin.

ProjectLens'te hybrid search su kanitlari birlestirir:

- lexical kanit: kelime, path ve dosya icerigi eslesmeleri,
- symbol kaniti: fonksiyon/class adlari,
- semantic kanit: embedding vektor yakinligi,
- role kaniti: source/test/documentation/config ayrimi.

Bu adimda `projectlens search "..." . --hybrid` komutu eklendi. Eger embedding
vektorleri varsa semantic skoru da kullanir. Eger embedding yoksa sistem bozulmaz;
lexical sonuclara fallback yapar ve kullaniciya semantic tarafin neden
devrede olmadigini soyler.

Gercek CLI testinde `database connection` sorgusunda once source dosyalari geldi,
test dosyalari ise daha asagi alindi. Bu onemli bir kalite karari: Test dosyalari
bazen ilgili kelimeleri tasir, ama kullanici genellikle once uygulamanin asil
kodunu okumak ister.
## Source-Grounded Ask Katmani

`ask` komutu su anda LLM cevabi uretmez. Bunun yerine soruyla ilgili en guclu
kaynak kanitlarini dosya ve satir numaralariyla gosterir. Bu bilincli bir tasarim
kararidir: once kanit secme sistemini dogru yapariz, sonra istersek LLM'i bu
kanitlarin ustune koyariz.

Bunu hukuk dosyasi gibi dusunebilirsin. Avukat once delilleri ve sayfa
numaralarini cikarir; sonra savunmayi yazar. ProjectLens'in `ask` modu da once
kod delillerini cikariyor:

- hybrid search ile ilgili dosyalari bulur,
- en iyi chunk veya en iyi query satiri etrafindan kucuk snippet alir,
- dosya yolu ve satir araligi verir,
- LLM cagrisi yapmadigini acikca soyler.

Komut:

`projectlens ask "where is configuration handled?" .`

Bu adim ilerideki LLM-backed ask modu icin temel olacak. O zaman LLM butun repoyu
degil, ProjectLens'in secip verdigi kanit paketini okuyacak.
## Ayak 6: Checks + Reports

Bu adimda ProjectLens'e `checks` komutu eklendi. Bu komut AI cevabi uretmez;
repo icin deterministik kalite kontrolu yapar. Deterministik demek: ayni repo,
ayni kurallar, ayni sonuc. Bu tarz kontroller CI sistemlerine de uygundur.

Kontrol edilen basliklar:

- README yeterli mi ve public proje bolumleri var mi?
- LICENSE var mi?
- `pyproject.toml` gecerli mi ve console script tanimli mi?
- `tests/` altinda test dosyalari var mi?
- `.gitignore` local ortam, secret, SQLite ve generated dosyalari koruyor mu?
- `.env`, `secrets.json`, `credentials.json` gibi secret-like dosyalar kokte var mi?
- `config-example.toml` kullaniciya ayarlari gosteriyor mu?
- GitHub Actions workflow var mi?

Komutlar:

`projectlens checks .`

`projectlens checks . --json`

Buradaki profesyonel ders su: Kaliteli developer tool sadece ozelligi calistirmaz,
kendi projesinin yayinlanabilirligini de olcer. Bu, GitHub'a koymadan once
"README eksik mi, test var mi, secret riski var mi?" gibi sorulara otomatik ve
tekrar edilebilir cevap verir.
## Ayak 7: MCP Integration

MCP, AI araclari icin ortak priz gibidir. Codex, Claude Desktop veya Cursor gibi
istemciler farkli arayuzlere sahip olabilir; ama MCP sayesinde ayni tool server'i
calistirip ayni komutlari cagirabilirler.

ProjectLens'te MCP katmani yeni bir analiz motoru degildir. Var olan ProjectLens
motorunu disariya acan ince bir adaptor katmanidir:

- `mcp_tools`: test edilebilir saf Python wrapper fonksiyonlari.
- `mcp_server`: bu fonksiyonlari MCP tool olarak kaydeden stdio server.
- `projectlens-mcp`: MCP istemcisinin calistiracagi komut.

STDIO mantigi su: AI istemcisi ProjectLens server'ini arka planda child process
olarak baslatir. Mesajlar terminal gibi stdin/stdout uzerinden JSON-RPC formatinda
gider gelir. Kullanici normalde bu server terminalini gormez; sorularini Codex
veya baska MCP destekli istemcinin icinden sorar.

Bu adimdaki profesyonel karar, MCP fonksiyonlarini dogrudan test edilebilir hale
getirmek oldu. Boylece MCP paketi kurulu olmasa bile `mcp_tools` testleri scanner,
index, search, ask ve checks davranisinin dogru oldugunu kontrol eder. MCP paketi
kurulunca `projectlens-mcp --help` ve istemci konfigurasyonu ile server baglantisi
test edilir.
## Ayak 7.5: Language Support + Capability Report

Bu adim, senin fark ettigin onemli eksigi kapatir: ProjectLens sadece Python
reposu gorecek diye varsayamaz. Gercek hayatta indirilen repo TypeScript, Go,
Rust veya baska bir dilde olabilir. Profesyonel arac bu durumda susup yanlis
kesinlik uretmez; kendi kapsamini acikca soyler.

Bu yuzden `LanguageCapability` modeli eklendi. Bu model her dil icin sunlari
soyluyor:

- kac dosya gorduk,
- kac symbol ve import cikardik,
- destek seviyesi ne: `deep`, `structured` veya `fallback`,
- parser guveni ne: high, medium veya low,
- sonucu nasil yorumlamak gerekir.

`deep` demek, Python'daki `ast` gibi guclu bir parser kullaniliyor demektir.
`structured` demek, JS/TS icin testli ve navigasyon odakli bir parser var ama bu
TypeScript compiler seviyesinde tam tip analizi degil demektir. `fallback` demek,
ProjectLens dosyayi okuyabilir, arayabilir, embedding'e koyabilir; ama fonksiyon
ve class haritasinda iddiali davranmaz demektir.

Yeni komut:

`projectlens capabilities .`

Bu komut bir repo icin "neyi iyi anliyorum, nerede sinirliyim" raporu verir. Bu,
sistemin kilitlenmemesini saglar: desteklenmeyen dil hata degildir, fallback
moddur. Ama kullaniciya etkisi acikca soylenir.

JS/TS parser su yapilari cikarmaya basladi:

- import / export-from / require,
- function ve async function,
- class,
- interface, type, enum,
- arrow function,
- React component ve hook benzeri adlandirmalar.

Bu adimdaki profesyonel ders: Iyi bir AI developer tool sadece cevap uretmez,
cevabin hangi kapsama ve hangi guven seviyesine dayandigini da gosterir.
## Ayak 8: Eval + Polish

Bu adimda ProjectLens'e `eval` katmani eklendi. Eval'i bir sinav anahtari gibi
dusunebilirsin: soru var, beklenen dosya var, ProjectLens'in o dosyayi ust
sirada bulup bulmadigi olculuyor.

Ornek case mantigi:

- soru: "where is the MCP stdio server implemented?"
- beklenen dosya: `src/projectlens_ai/mcp_server.py`
- basari olcutu: bu dosya `top_k` sonuc icinde mi ve `ask` modu bu dosyadan kaynak gosteriyor mu?

Bu, normal unit testlerden farklidir. Unit test "kod bozuldu mu" diye bakar.
Eval ise "arama/ask kalitesi dogru mu" diye bakar. AI ve retrieval projelerinde
bu ayrim cok onemlidir; cunku sistem calisiyor olabilir ama yanlis dosyayi one
cikariyor olabilir.

Eval sonucunda confidence etiketi de uretilir:

- `high`: beklenen dosya 1. sirada, ask kaynak gosteriyor, dil destegi guclu.
- `medium`: beklenen dosya bulunuyor ama daha alt sirada veya sinirli kanit var.
- `low`: beklenen dosya bulunmuyor ya da kanit zayif.

Bu adimdaki profesyonel ders: Bir developer tool sadece ozellik listesinden
ibaret degildir. Kendi kalitesini olcen, sinirini gosteren ve tekrar tekrar
calistirilabilen kontrol mekanizmalari varsa daha guvenilir olur.