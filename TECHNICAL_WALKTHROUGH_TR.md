# Teknik Açıklamalı Rehber

Bu doküman, bir ödemenin sisteme girdiği andan monitoring ekranlarında göründüğü ana kadar doğrulanmış V1 sistemini ve trade-off'larını anlatır.

## 1. Bir işlem sisteme girer

Çağıran sistem, `src/fraud_detection/domain.py` içindeki sürümlendirilmiş `Transaction` sözleşmesini gönderir. Pydantic; bilinmeyen alanları, timezone içermeyen timestamp'leri, pozitif olmayan tutarları, geçersiz ülke/para birimi uzunluklarını, geçersiz IP adreslerini ve desteklenmeyen kanalları reddeder. Etiketler bilinçli olarak bu sözleşmeye dahil edilmemiştir: bir ödeme, inference sırasında kendi doğru cevabını beraberinde getiremez.

İki ingestion yolu vardır:

1. `apps/api/main.py` içindeki `POST /transactions`, authorization çağrısı yapan sistemlere hizmet verir ve kararı senkron döndürür.
2. `apps/simulator/main.py`, olayları `transactions.v1` topic'ine yayınlar; `apps/worker/main.py` bunları tüketir.

Her iki yol da `src/fraud_detection/database.py` içindeki `score_and_persist()` fonksiyonunu çağırır. Bu ortak sınır önemlidir: HTTP ve Kafka yolları fark edilmeden farklı feature veya politika uygulayamaz.

### Neden FastAPI?

FastAPI; Python ile doğal çalışan tip güvenli sözleşmeler, OpenAPI/Swagger, dependency injection ile veritabanı session'ları ve basit health/metrics endpoint'leri sağlar. Gerçek bir şirket daha sıkı gecikme kontrolü için Go/Java kullanıp Python modelini ayrı barındırabilir. Bu yerel proje için tek ve tip güvenli Python yolu daha değerlidir.

### Neden Redpanda?

Redpanda, ZooKeeper gerektirmeden Kafka producer/consumer semantiği sunar. `transactions.v1` girdi; `fraud_predictions.v1` ve `fraud_alerts.v1` çıktı topic'leridir. Kafka tekrar oynatılabilir ve bağımsız ölçeklenebilir sınırlar oluşturur. Ancak tek başına tam olarak bir kez iş etkisi garantisi vermez; bu nedenle kod ayrıca veritabanı idempotency'si ve outbox kullanır.

## 2. Point-in-time geçmiş ve feature üretimi

`SQLHistoryProvider.prior_transactions()`, `(user_id, timestamp)` indeksini kullanarak önceki 30 günü sorgular ve açıkça `history.timestamp < current.timestamp` koşulunu uygular. SQLite testleri ve in-memory provider aynı sözleşmeye uyar.

`src/fraud_detection/features.py` içindeki `calculate_features()`, mevcut `Transaction` ile daha önceki işlemlerin dizisini alır ve `FeatureVector(values: dict[str, float])` döndürür.

Önemli mantık:

- Geçmiş yeniden filtrelenir ve sıralanır. Bu savunmacı kontrol, hatalı bir provider'ın bile gelecekteki bir olayı dahil etmesini önler.
- Yerel `recent(window)` çağrıları 1 dakika, 5 dakika, 1 saat ve 24 saatlik işlem sayılarını hesaplar.
- Geçmiş tutarlar ortalama, medyan, tutar sapması ve saatlik toplam tutarı üretir.
- Geçmiş merchant, ülke ve device ID kümeleri yenilik göstergelerini üretir.
- Son konum ve geçen süre `_haversine_km()` fonksiyonuna verilerek seyahat hızı tahmin edilir; 900 km/s üzeri hız `impossible_travel` olur.
- Geçmiş boşsa nötr tutar baseline'ları kullanılır ve ilk ödeme otomatik olarak tüm yenilik risklerini almaz.

Bu fonksiyon olmasaydı model yalnızca mevcut tutarı görür, fraud detection'ı anlamlı kılan davranışsal bağlamı kaybederdi. Yerel uygulamanın zayıflığı, her ödeme için kullanıcının yakın geçmişini çekmenin ve hesaplamanın veritabanı/CPU işi olmasıdır. Production ortamında önceden hesaplanmış online aggregate'ler Redis, Flink veya yönetilen bir feature store içinde atomik olarak güncellenirdi.

### Offline/online tutarlılığı

`pipelines/training/data.py`, batch point-in-time dönüşümlerini uygular. Rolling window'lar `closed="left"` kullanır; expanding tutar istatistikleri bir satır kaydırılır. `tests/test_features.py`, gelecekteki yüksek tutarlı bir ödemeyi özellikle girdiye ekler ve bunun mevcut feature vector'ünü değiştiremediğini kanıtlar.

Demo için tüm zaman çizelgesine dağıtılan 249.992 satırlık örnek kullanıcı geçmişlerini seyrekleştirir. Kaynakları sınırlı bir gösterim için uygundur ancak velocity'yi yalnızca yaklaşık temsil eder. `full` profil her satırı işler.

## 3. Model inference

`src/fraud_detection/model.py` içindeki `load_model()`, joblib bundle'ını okur. Bundle şunları içerir:

- kalibre edilmiş scikit-learn uyumlu model;
- sürüm ve feature'ların kesin sırası;
- optimize edilmiş review/block eşikleri;
- SHAP background örneği;
- referans tutar, ülke ve olasılık dağılımları.

`SklearnModel.predict_probability()`, isimlendirilmiş tek satırlık yapıyı `predict_proba()` üzerinden geçirir ve pozitif sınıf olasılığını döndürür. Wrapper, scikit-learn ayrıntılarını servisten uzak tutar.

Artifact yoksa `HeuristicBootstrapModel` yerel endpoint'leri gösterilebilir hâle getirir ve `/model/info`, `bootstrap_model: true` döndürür. Bu eğitilmiş model değildir ve CV metriği için kesinlikle kullanılmamalıdır. Compose, API başlamadan önce bootstrap eğitimini çalıştırdığı için normal container yolu champion modeli yükler.

`src/fraud_detection/service.py` içindeki `ScoringService.score()` şu sırayı zamanlar:

1. önceki geçmişi iste;
2. feature'ları hesapla;
3. olasılığı tahmin et;
4. politikaya göre karar ver;
5. sürümlendirilmiş `Prediction` yanıtını oluştur.

Modelin görevi olasılıkta biter. Veritabanına yazmaz, Kafka çağırmaz ve business action seçmez.

## 4. Risk skoru ve karar motoru

`DecisionEngine.decide()`, olasılığı `round(probability * 100)` ile skora çevirir ve sıralı eşikleri uygular. Eğitilmiş bundle şu anda review için `0.15`, block için `0.40` sağlar; environment politikası model eşiklerini açıkça override edebilir.

Kurallar daha sonra feature'ları inceler:

- beş dakika içinde en az sekiz işlem → hızlı işlem patlaması nedeni;
- önceki ortalamanın en az sekiz katı tutar → olağan dışı büyük tutar nedeni;
- impossible travel → seyahat nedeni;
- impossible travel ve yeni device birlikteyse → BLOCK;
- diğer nedenler APPROVE kararını MANUAL_REVIEW'a yükseltebilir;
- kurallar model kararının risk seviyesini düşürmez.

Bu ayrım temel tasarım kararlarından biridir. Kalibre edilmiş olasılık istatistiksel tahmindir; review kapasitesi ve müşteri sürtünmesi iş kısıtlarıdır. Risk ekipleri estimator'ı yeniden eğitmeden politikayı değiştirebilir. `tests/test_decision.py`, kesin eşik sınırlarını, escalation'ı ve geçersiz olasılıkları test eder.

## 5. Atomik kalıcılık ve event yayınlama

`score_and_persist()` önce `predictions.transaction_id` değerini kontrol eder. Çağıran sistem yeniden denerse mevcut tahmini döndürür. Yeni ödemede user, merchant, transaction, prediction, isteğe bağlı alert ve outbox satırlarını tek SQL transaction içinde hazırlar.

Temel desen transactional outbox'tır:

```text
veritabanı transaction'ı
  ├─ transaction
  ├─ prediction
  ├─ isteğe bağlı alert
  └─ yayınlama niyetleri
        ├─ transactions.v1
        ├─ fraud_predictions.v1
        └─ fraud_alerts.v1
```

`publish_outbox_batch()`, yayınlanmamış satırları kilitler, idempotent producer ile JSON yayınlar ve satırları yayınlandı olarak işaretler. Kafka olayı kabul ettikten fakat `published_at` commit edilmeden önce process çökerse olay tekrar yayınlanabilir. Bu nedenle consumer'lar transaction ID üzerinden key/idempotency uygular. “Exactly once”, broker sloganı varsayılarak değil, iş etkisi seviyesinde sağlanır.

Worker otomatik commit'i kapatır. Kafka offset'i yalnızca PostgreSQL commit'inden sonra commit edilir. Geçersiz olaylar özgün payload ve hata ile `transactions.dlq.v1` topic'ine gönderilir; ardından commit edilerek poison message'ın partition'ı kalıcı biçimde durdurması önlenir.

## 6. Alarmlar ve açıklanabilirlik

REVIEW ve BLOCK kararları `FraudAlertRecord` oluşturur. İlk yanıt ucuz rule reason code'larını içerir; authorization thread'i üzerinde SHAP hesaplanmaz.

`apps/worker/explainer.py`, `fraud_alerts.v1` olaylarını tüketir, işlemin point-in-time feature'larını yeniden oluşturur ve `src/fraud_detection/explainability.py` içindeki `shap_explanation()` fonksiyonunu çağırır. Paketlenmiş background ve permutation explainer signed impact değerleri üretir; bunlar okunabilir risk faktörlerine çevrilip alert üzerinde saklanır. Eğitilmiş artifact yoksa `reason_code_explanation()` şeffaf fallback sağlar.

`GET /predictions/{id}/explanation`, işlem tamamlanana kadar `pending` döndürür. Açıklama hatası authorization kararını geciktiremez veya geri çeviremez. Yüksek hacimde SHAP worker'ları ayrı autoscale edilir, iş yükleri sınırlandırılır ve tree champion için büyük olasılıkla model-specific TreeSHAP kullanılırdı.

## 7. Dashboard ve sistem monitoring

`apps/web`, FastAPI sözleşmelerini BFF route handler'ları üzerinden kullanan Next.js/TypeScript Fraud Command Center'dır. PostgreSQL'i doğrudan sorgulamaz; 24 saatlik hacmi, kararları, risk dağılımını, alarmları, investigation ayrıntılarını, açıklamaları ve model lifecycle durumunu gösterir.

`src/fraud_detection/observability.py`, Prometheus counter ve histogram'larını tanımlar. API `/metrics` endpoint'ini; worker process'leri 9101/9102 portlarını sunar. Prometheus bunları scrape eder; hazır Grafana dashboard'u karar oranlarını, p95 inference gecikmesini ve hataları gösterir. Structured JSON log'lar mümkün olan yerlerde transaction, request ve model kimliklerini kullanır.

`locustfile.py` içindeki Locust görevi benzersiz ve geçerli ödemeler gönderir. Bu gerçek ve çalıştırılabilir load-test kodudur ancak bu ortamda çalıştırılmamıştır. Ortalama/p50/p95/p99 gecikme ve throughput değerleri **ölçülmemiştir**.

## 8. Gecikmeli etiketler ve model performansı

Fraud gerçeği çoğunlukla chargeback veya analyst kararı olarak daha sonra gelir; authorization sırasında mevcut değildir. `POST /transactions/{id}/label`, `ConfirmedLabelRecord` için upsert yapar ve outbox'a `confirmed_labels.v1` yazar. `/analytics/model-performance`, etiketleri özgün tahminlerle birleştirir ve yalnızca etiket olduğunda precision, recall ve F1 döndürür.

Bu yaklaşım, etiketsiz yeni approval'ların gerçek legitimate işlemmiş gibi değerlendirilmesini önler. Production metric servisi ayrıca label maturity window'larını, investigation selection bias'ını, geç chargeback'leri ve segment bazında güven aralıklarını hesaba katardı.

## 9. Drift monitoring

`apps/worker/monitor.py` her beş dakikada çalışır ve en az 100 yakın tarihli işlem bekler. Son günü model bundle referanslarıyla karşılaştırır:

- tutar ve fraud probability: Population Stability Index ile Kolmogorov–Smirnov statistic/p-value;
- ülke: Jensen–Shannon divergence.

PSI 0.20 veya ülke JS 0.10 olduğunda `drift_detected` işaretlenir. Rapor model sürümü ve zaman aralığı sınırlarıyla saklanır. Drift, input veya sıralama davranışının değiştiğine dair kanıttır; accuracy'nin düştüğünün kanıtı değildir. Data drift ile concept/performance drift ayrımı için gecikmeli etiketler gerekir.

## 10. Eğitim nasıl çalışır?

`scripts/bootstrap.py` idempotent'tir. Açık veri kümesi yoksa indirir, SHA-256 manifest'i yazar, sıfır tutarlı simülatör satırlarını temizler, demo örneğini tüm zaman çizelgesine dağıtır, feature'ları materialize eder ve `train()` fonksiyonunu çağırır.

### Classification ve olasılık

Binary classification, transaction feature'larından fraud/nonfraud sonucuna giden ilişkiyi öğrenir. `predict_proba()` kesinlik değil, sıralama/risk değeri döndürür. Calibration, ham model skorlarını gözlenen olay oranlarına yaklaştırır; böylece maliyet eşikleri daha anlamlı olur.

### Zamansal partition'lar

`chronological_slices()` şu ayrımları oluşturur:

- %50 training;
- %15 aday seçimi;
- %10 calibration;
- %10 threshold optimization;
- %15 dokunulmamış test.

Random split kullanmak, eski tarihli training verisinin daha sonra gerçekleşmiş müşteri/merchant davranışlarından öğrenmesine yol açabilirdi. Son dönemi tamamen dokunulmamış tutmak deployment'a daha dürüst bir benzetim sağlar.

### Class imbalance deneyleri

`candidate_models()`; class-weighted Logistic Regression, balanced Random Forest, weighted XGBoost, undersampled Logistic Regression ve SMOTE Logistic Regression üretir. Yalnızca training verisi resample edilir. Split işleminden önce SMOTE uygulamak, gelecekteki/test komşularını kullanarak sentetik noktalar üretir ve veri sızıntısına yol açar.

### Bu projedeki metrikler

- **Precision:** block edilen işlemler arasında kaç tanesinin fraud olduğu. Test: 0.9266. Yüksek precision müşteri zararını sınırlar.
- **Recall:** fraud işlemleri arasında kaç tanesinin block edildiği. Test: 0.3108. Bu değer, kaçırılan fraud riskini açıkça gösterir.
- **F1:** precision ile recall'un harmonik ortalaması. Test: 0.4654.
- **PR-AUC:** tüm eşiklerdeki precision/recall performansı. Test: 0.3363; nadir fraud sınıfı için kullanışlıdır.
- **ROC-AUC:** farklı eşiklerde pozitifleri negatiflerden yukarı sıralama performansı. Test: 0.6677; raporlanır ancak birincil metrik değildir.
- **False-positive rate:** yanlışlıkla block edilen legitimate işlemlerin tüm legitimate işlemlere oranı.
- **False-negative rate:** block edilmeyen fraud işlemlerinin tüm fraud işlemlerine oranı; test değeri 0.6892.
- **Confusion matrix:** belirli eşikteki true/false positive/negative sayıları. Bileşen oranları raporda yer alır; çizilmiş bir confusion matrix artifact'ı eklemek mantıklı bir sunum geliştirmesidir.

### İş maliyeti ve eşik ayarlama

`expected_cost()`; approve edilen fraud işlemine tutarı kadar, review işlemine sabit investigation maliyeti ile varsayılan yakalama oranından sonra kalan fraud kaybı kadar, legitimate block işlemine ise müşteri sürtünmesi maliyeti kadar bedel yazar. `optimize_thresholds()` sıralı iki eşiği tarar ve %5 review kapasitesini aşan politikaları reddeder. Ayrı threshold döneminde 0.15/0.40 seçilmiştir. Bu maliyet birimleri karar metodolojisini gösterir; önlendiği iddia edilen gerçek dolar tutarları değildir.

### Champion paketleme ve MLflow

En düşük maliyetli aday kazanır; eşitlik durumunda PR-AUC kullanılır. Ölçülen demo Random Forest'ı seçmiştir. Champion, selection sınırına kadar yeniden fit edilir, dondurulur, sigmoid ile kalibre edilir ve testte yalnızca bir kez değerlendirilir. Joblib ve MLflow; modeli, metrikleri, raporu, feature sözleşmesini, referansları ve eşikleri saklar. Kayıtlı model adı `fraud-detector`dır.

## 11. Retraining ve güvenli terfi

`pipelines/retraining/run.py`, `challenger.joblib` modelini eğitir, champion raporunu okur ve şu kontrolleri yapar:

- PR-AUC en fazla 0.01 düşebilir;
- recall en fazla 0.02 düşebilir;
- beklenen test maliyeti artmamalıdır.

Pipeline, `promotion_recommended` ile birlikte `automatic_promotion: false` yazar. Böylece yeni model fark edilmeden production champion olamaz. Gerçek onay süreci ayrıca gecikme, calibration, segment fairness, model-risk review ve canary monitoring gerektirirdi.

## 12. Eksiksiz örnek: 1.250 dolarlık ödeme

`user-883` kullanıcısının normalde yaklaşık 100 dolar harcadığını ve yakın zamanda device/konum değiştirdiğini varsayalım.

1. `TransactionSimulator.next()` veya API caller olayı oluşturur.
2. `publish_json()` olayı `transactions.v1` topic'ine koyar veya FastAPI doğrudan persistence katmanını çağırır.
3. `worker.run()`, `Transaction` doğrulaması yapar ve SQL session açar.
4. `SQLHistoryProvider.prior_transactions()` yalnızca daha eski user event'lerini döndürür.
5. `calculate_features()` örneğin amount ratio 12.5, new device 1 ve impossible travel 1 üretebilir.
6. `SklearnModel.predict_probability()` 0.91 döndürebilir. Bu değer yalnızca örnektir; saklanmış bir transaction için ölçülen tahmin değildir.
7. `DecisionEngine.decide()`, risk skoru 91 ve BLOCK döndürür; impossible travel/new device ayrıca denetlenebilir escalation nedeni sağlar.
8. `score_and_persist()`, transaction, prediction, alert ve outbox satırlarını atomik olarak ekler.
9. `publish_outbox_batch()`, prediction ve alert event'lerini yayınlar.
10. Explainer alert'i tüketir ve en önemli SHAP faktörlerini saklar.
11. Next.js Fraud Command Center; `/alerts`, `/transactions/{id}`, `/predictions/{id}` ve explanation endpoint'ini okur.
12. Prometheus/Grafana sayıları ve gecikmeyi gözlemler; daha sonra gelen doğrulanmış etiket model performansını günceller.

0.91 değeri bilinçli olarak akış örneğidir; uydurulmuş benchmark değildir.

## 13. Docker ve yapılandırma

Çok aşamalı görünüme sahip tek runtime `Dockerfile`, tüm servis extra'larını kurar ve UID 10001 ile çalışır. Compose; PostgreSQL, Redpanda, MLflow, bootstrap, API, worker'lar, simülatör, dashboard, Prometheus ve Grafana'yı sağlar. Named volume'lar veri/artifact'ları kalıcılaştırır. Health tabanlı dependency'ler, migration/bootstrap bağımlılıkları hazır olmadan API'nin yüklenmesini önler.

`.env.example` yerel varsayılanları içerir; secret'lar commit edilmez. Environment variable'lar veritabanı, broker, artifact, eşik, maliyet, simülatör ve dashboard ayarlarını override eder. Production ortamında ortak yerel credential yerine secrets manager ve ayrı servis identity'leri kullanılırdı.

2026-08-27 V1 kabul koşusu; production image build'lerini, boş-volume Compose bootstrap'ını, eğitim/kayıt, migration, sağlıklı servisler ve analyst label akışına kadar doğrulamıştır.

## 14. Stripe ölçeğinde nasıl çalışırdı?

### Saniyede yaklaşık 100 işlem

Kavramsal topoloji korunabilir. User bazında key kullanılan birkaç Kafka partition, birden fazla API/worker replica, connection pooling, sıcak rolling feature'lar için Redis ve kesin latency/error SLO'ları eklenir. PostgreSQL, read replica ve partition edilmiş tablolarla primary olarak kalabilir.

### Saniyede yaklaşık 1.000 işlem

Kubernetes kullanılır, stateless inference autoscale edilir, onlarca partition açılır, outbox publishing ayrıştırılır, feature'lar stream processor içinde önceden hesaplanır, model artifact'ları yerelde cache edilir ve alert analytics transactional veritabanından ayrılır. Schema registry uyumluluğu ve distributed tracing kullanılır.

### Saniyede yaklaşık 10.000 işlem

Event-time doğruluğuna sahip dedicated online feature store, shard/partition edilmiş operational store'lar, distributed model serving, bölge başına Kafka, backpressure, load shedding, circuit breaker ve otomatik canary modeller gerekir. Offline ve online feature'lar ortak declarative tanımlardan üretilmelidir.

### Saniyede 100.000+ işlem

Ölçülen throughput'a göre yüzlerce/binlerce partition, bölgesel ingestion ve model-serving cell'leri, multi-region fault isolation, replicated entity state, global olarak koordine edilen model/config rollout, columnar lakehouse analytics, sürekli label pipeline'ları, uzmanlaşmış graph-risk servisleri ve olgun on-call/SLO/error-budget uygulamaları gerekir. Kubernetes autoscaling tek başına yeterli değildir; storage, feature tutarlılığı, network, failover, observability cardinality ve operasyonel governance temel mimari problemlere dönüşür.

Uygulanan yerel sistem bu throughput iddialarının hiçbirini desteklemez. Yalnızca ölçekli bir sistemin tartışılabileceği component sınırlarını ve doğruluk desenlerini gösterir.

## 15. Sonraki geliştirmeler

Tam Locust/streaming p50/p95/p99 benchmark matrisi yayınlanmalı; full sequential veri kümesi eğitilmeli; terminal/entity encoding ve graph feature'larıyla recall artırılmalı; calibration grafikleri ve confusion-matrix artifact'ları eklenmeli; API'ler authentication ile korunmalı ve yönetilen bulut altyapısında canary deployment yapılmalıdır.
