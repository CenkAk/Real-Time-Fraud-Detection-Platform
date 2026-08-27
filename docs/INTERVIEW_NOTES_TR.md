# Mülakat Notları

## Otuz saniyelik anlatım

Bir notebook modeli yerine gerçek zamanlı fraud platformu geliştirdim. İşlemler FastAPI veya Redpanda üzerinden geliyor; point-in-time davranışsal feature'lar önceki PostgreSQL geçmişinden hesaplanıyor; kalibre edilmiş Random Forest champion risk üretiyor ve ayrı bir politika approve, review veya block kararı veriyor. Durum ve dışarı giden event'ler transactional outbox üzerinden birlikte commit ediliyor. MLflow eğitimleri takip ediyor, SHAP alarmları açıklıyor, gecikmeli etiketler performansı güncelliyor; Prometheus/Grafana ve Next.js command center operasyon görünürlüğü sağlıyor.

## Muhtemel sorular ve kısa yanıtlar

### Neden Random Forest seçildi?

Önceden kararlaştırılmadı. Logistic Regression, Random Forest, XGBoost, undersampling ve SMOTE'u daha sonraki bir selection window üzerinde karşılaştırdım. Random Forest, yapılandırılmış beklenen maliyet ve eşitlikte PR-AUC kuralıyla kazandı. Dokunulmamış demo testinde 0.3363 PR-AUC ve 0.9266 precision elde etti; recall 0.3108 olduğu için bunu açıkça sınırlama olarak belirtiyorum.

### Neden accuracy optimize edilmedi?

Fraud nadirdir; her işlemi legitimate tahmin etmek hiç fraud yakalamadan yüksek accuracy gösterebilir. Precision, recall, F1, PR-AUC, ROC-AUC, false-positive/negative oranları ve iş maliyetini kullanıyorum.

### Neden PR-AUC?

Negatif sınıf baskınken pozitif sınıfın bulunmasına ve precision'a odaklanır. True-negative hacmi çok büyük olduğu için ROC-AUC görsel olarak güçlü kalabilir. Yine de her ikisini raporluyorum.

### Class imbalance nasıl ele alındı?

Class weighting, balanced tree sampling, random undersampling ve SMOTE karşılaştırıldı. Resampling yalnızca en eski training partition içinde yapılır; time split öncesinde uygulamak değerlendirmeyi kirletirdi. Ölçülen aday tablosu `artifacts/challenger_model_report.json` içindedir.

### Veri sızıntısı nasıl önlendi?

Tüm veriler zamana göre sıralanır, rolling window'lar mevcut satırı dışlar, preprocessing yalnızca training üzerinde fit edilir; selection, calibration, threshold ve test dönemleri ayrıdır. Target, fraud-scenario alanları, outcome'lar ve label'a bağlı sentetik ülke/device feature'ları model şemasına alınmaz.

### Olasılık neden kalibre edildi?

Karar eşikleri ve beklenen maliyetler, olasılıkları yalnızca sıralama değil risk tahmini olarak kullanır. Sigmoid calibration, dondurulmuş champion kullanılarak ayrı bir sonraki dönemde fit edilir; model yeniden fit edilmez ve threshold/test dönemleri kullanılmaz.

### Eşikler nasıl seçildi?

Sıralı review/block çiftlerini tarıyorum. Amaç fonksiyonu kaçırılan fraud için işlem tutarını, legitimate block için friction maliyetini, her review için investigation maliyetini ve review edilen fraud için beklenen kalan kaybı yazar. Ayrıca maksimum review oranını uygular. Demo, keyfî 0.50 yerine 0.15 ve 0.40'ı seçti.

### Prediction ve decision neden ayrıldı?

Olasılık modelin iddiasıdır; APPROVE/REVIEW/BLOCK iş politikasıdır. Ayrım, risk ekiplerinin modeli yeniden eğitmeden kapasite/maliyeti değiştirmesine veya impossible-travel kuralı eklemesine izin verir ve her escalation'ı denetlenebilir yapar.

### Neden Kafka/Redpanda?

Ingestion, scoring, alert, explanation ve gelecekteki consumer'ları ayrıştırır; replay sağlar ve partition/consumer group'larla ölçeklenir. Redpanda, daha basit yerel stack ile Kafka semantiği verir.

### Redpanda çökerse ne olur?

Senkron API kararları saklanmaya devam eder. Outbox satırları yayınlanmadan bekler ve broker geri geldiğinde yeniden denenir. Simülatör trafiği Redpanda düzelene kadar sisteme giremez. Source of truth veritabanıdır.

### Prediction servisi çökerse ne olur?

Readiness başarısız olur ve ödeme çağrısı yapan sistem, kaydedilmemiş karar yerine hata alır. Streaming mesajları commit edilmez ve replay edilir. Gerçek şirket risk tabanlı fallback tanımlar: küçük ve güvenilir ödemelerde fail open, yüksek riskte fail closed. Bu proje böyle bir politika varmış gibi davranmaz.

### Idempotency nasıl uygulandı?

`transaction_id` veritabanı primary key'idir. Yeniden denemede mevcut prediction döndürülür. Kafka offset'i yalnızca veritabanı commit'inden sonra commit edildiği için replay ikinci bir prediction veya alert oluşturamaz.

### Gecikmeli etiketler nasıl çalışır?

`POST /transactions/{id}/label`, analyst/chargeback gerçeğini upsert eder ve `confirmed_labels.v1` yayınlar. Performance endpoint'leri etiketleri, tahmini üreten model sürümüyle birleştirir. Drift hemen hesaplanabilir; gerçek performans etiketleri bekler.

### Drift nasıl izlenir?

Model bundle referans tutar, ülke ve olasılık dağılımlarını saklar. Scheduled worker numeric değerler için PSI/KS, ülke için Jensen–Shannon divergence hesaplar, raporu saklar ve drift event'i log'lar. Drift investigation/retraining başlatır; otomatik terfi başlatmaz.

### Fraudster'lar problemi nasıl değiştirir?

Statik kurallara uyum sağlar, eşikleri test eder ve hesaplar/device'lar arasında koordinasyon kurarlar. Production sistemde hızlı kural iterasyonu, graph/entity feature'ları, investigator feedback, adversarial monitoring ve segment modelleri gerekir. Ayrıca yalnızca incelenen vakalar hızlı doğrulandığı için etiketlerde selection bias oluşur.

### Retraining nasıl çalışır?

Doğrulanmış etiketler ve yakın tarihli event'ler yeni kronolojik veri kümesi oluşturur. Pipeline challenger eğitir; schema, iş maliyeti, PR-AUC, recall ve latency kontrolleri yapar. Sürümü kaydeder ancak otomatik terfi ettirmez; açık bir operasyon kararı champion'ı değiştirir.

### AWS veya GCP'ye nasıl deploy edilir?

Container'lar EKS/GKE üzerinde çalıştırılır; MSK/Pub/Sub veya managed Kafka, RDS/Cloud SQL, managed Redis/feature store, artifact'lar için object storage, managed Prometheus ve secrets manager kullanılır. CI test/migration çalıştırır, image'ları imzalar, challenger/canary deploy eder ve SLO veya model gate ihlalinde rollback yapar.

### Saniyede 100.000 işlemde ne değişir?

Kafka user/entity bazında partition edilir; yüzlerce partition ve ölçekli consumer group kullanılır; rolling state distributed online feature store'a taşınır; latency izin verdiğinde batching kullanan distributed model serving uygulanır; operational storage shard edilir; analytics columnar warehouse'a gönderilir; schema zorunlu tutulur. Kubernetes üzerinde autoscaling, backpressure, multi-region failover ve uçtan uca tracing gerekir. Yerel proje bu hızı desteklemez.
