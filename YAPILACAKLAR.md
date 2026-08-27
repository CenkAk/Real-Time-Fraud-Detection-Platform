# Real-Time Fraud Detection Platform — Eski Yol Haritası

> Bu dosya ilk durum analizinin arşivlenmiş iş kırılımıdır. Güncel tamamlanma kanıtı için
> `docs/V1_RELEASE_CHECKLIST_TR.md`, sonraki faz kapsamı için onaylanan ana plana bakın.

Bu doküman, projenin mevcut çalışan hâlinden daha güçlü, doğrulanmış ve mülakatlarda savunulabilir bir production-style fraud detection platformuna ilerlemesi için hazırlanmıştır. Bir fikir havuzu değil; öncelikler, bağımlılıklar, kabul kriterleri ve doğrulama adımları içeren uygulama planıdır.

## 1. Mevcut durum özeti

Şu anda repository aşağıdaki yetenekleri içeriyor:

- FastAPI üzerinden senkron fraud skorlama ve sorgulama.
- Redpanda/Kafka uyumlu producer, consumer ve topic yapısı.
- PostgreSQL/SQLAlchemy veri modeli ve Alembic migration'ları.
- Point-in-time feature engineering ve veri sızıntısı kontrolleri.
- Logistic Regression, Random Forest, XGBoost, undersampling ve SMOTE karşılaştırması.
- Kronolojik train/selection/calibration/threshold/test ayrımı.
- İş maliyetine göre ayrı review ve block eşiklerinin optimizasyonu.
- APPROVE, MANUAL_REVIEW ve BLOCK karar motoru.
- Transactional outbox ve idempotent işlem yaklaşımı.
- Gecikmeli confirmed-label akışı.
- SHAP/reason-code açıklama mimarisi.
- PSI, KS ve Jensen–Shannon tabanlı drift ölçümleri.
- MLflow deney takibi ve champion/challenger kavramı.
- Next.js/TypeScript Fraud Command Center.
- Prometheus/Grafana yapılandırması.
- Dockerfile, Docker Compose, Locust ve pytest altyapısı.

Ölçülen demo sonucu:

- Veri: 249.992 kronolojik sentetik ödeme olayı.
- Champion: Random Forest.
- Precision: 0.9266.
- Recall: 0.3108.
- F1: 0.4654.
- PR-AUC: 0.3363.
- ROC-AUC: 0.6677.
- Review threshold: 0.15.
- Block threshold: 0.40.

Temel eksik doğrulama alanları:

- Temiz-volume Docker Compose ve ana uçtan uca akış 2026-08-27 tarihinde doğrulandı.
- PostgreSQL ve Redpanda ile gerçek Testcontainers integration testleri mevcut ve geçti.
- Locust benchmark'ı çalıştırılmadı; p50/p95/p99 ve throughput ölçülmedi.
- Recall düşüktür ve modelin en önemli geliştirme alanıdır.
- Authentication, authorization, secrets management ve production security kontrolleri eksik.
- Cloud deployment ve CI/CD akışı henüz yoktur.

## 2. Öncelik ve durum sözlüğü

Her iş aşağıdaki önceliklerden biriyle değerlendirilmelidir:

- **P0 — Kritik:** Projenin doğru çalıştığının veya güvenilir olduğunun kanıtlanması için zorunlu.
- **P1 — Yüksek:** Portfolio ve mülakat değerini belirgin şekilde artırır.
- **P2 — Orta:** Production benzerliğini ve teknik derinliği artırır.
- **P3 — İleri seviye:** Ölçekleme, araştırma veya uzun vadeli geliştirme.

Durumlar:

- `[ ]` Başlanmadı.
- `[~]` Devam ediyor.
- `[x]` Tamamlandı ve doğrulandı.
- `[!]` Bloke veya dış bağımlılık bekliyor.

Bir madde yalnızca kod yazıldığında değil, kabul kriterleri çalıştırılıp kanıt üretildiğinde tamamlanmış sayılmalıdır.

---

# Faz 1 — Tam Docker Compose Doğrulaması

**Öncelik:** P0
**Amaç:** README'deki tek komutla çalışma iddiasını gerçek ortamda doğrulamak.

## 1.1 Ortam hazırlığı

- [ ] Docker Desktop veya uyumlu Docker Engine kurulumunu doğrula.
- [ ] `docker version` ve `docker compose version` çıktılarını kaydet.
- [ ] Docker'a ayrılan CPU, RAM ve disk limitlerini belgele.
- [ ] Repository kökünde `.env.example` dosyasından `.env` üret.
- [ ] `.env` içindeki portların yerel servislerle çakışmadığını kontrol et.
- [ ] Eski container, network ve volume'ların test sonucunu etkilemediğinden emin ol.

## 1.2 Image build doğrulaması

- [ ] `docker compose build --no-cache` çalıştır.
- [ ] Tüm image'ların hata olmadan oluşturulduğunu doğrula.
- [ ] Dependency sürüm çakışmalarını gider.
- [ ] Container'ların root olmayan kullanıcıyla çalıştığını doğrula.
- [ ] Image boyutlarını kaydet ve gereksiz büyük katmanları incele.
- [ ] Build sırasında secret veya `.env` içeriğinin image layer'larına girmediğini doğrula.

## 1.3 Servislerin ayağa kalkması

- [ ] `docker compose up --build` ile sistemi başlat.
- [ ] PostgreSQL health check'inin başarılı olduğunu doğrula.
- [ ] Redpanda broker health check'ini doğrula.
- [ ] MLflow servisinin artifact ve metadata yazabildiğini doğrula.
- [ ] Bootstrap container'ının veri indirme ve model eğitimini tamamladığını doğrula.
- [ ] Alembic migration'larının sırasıyla uygulandığını doğrula.
- [ ] API readiness ve liveness endpoint'lerini test et.
- [x] Next.js Fraud Command Center, Prometheus ve Grafana sayfalarına eriş.
- [ ] Worker, explainer ve monitor process'lerinin hata döngüsüne girmediğini kontrol et.

## 1.4 Uçtan uca smoke test

- [ ] Simülatörden normal bir işlem yayınla.
- [ ] İşlemin `transactions.v1` topic'ine ulaştığını doğrula.
- [ ] Consumer'ın işlemi okuyup feature ürettiğini doğrula.
- [ ] Prediction kaydının PostgreSQL'e yazıldığını doğrula.
- [ ] Risk skoru ve kararın üretildiğini doğrula.
- [ ] REVIEW/BLOCK işleminde alert kaydı oluştuğunu doğrula.
- [ ] Prediction ve alert outbox event'lerinin yayınlandığını doğrula.
- [ ] Dashboard'da işlemi ve alert'i görüntüle.
- [ ] Analyst workflow ile alert'i fraud veya legitimate olarak çöz.
- [ ] Confirmed label kaydının oluştuğunu doğrula.
- [ ] Model-performance endpoint'inin etiketi hesaba kattığını doğrula.
- [ ] Prometheus'ta sayaçların, Grafana'da panellerin güncellendiğini doğrula.

## 1.5 Hata senaryoları

- [ ] Redpanda'yı geçici durdur ve API üzerinden işlem gönder.
- [ ] Transaction/prediction verisinin PostgreSQL'de kaldığını doğrula.
- [ ] Outbox satırlarının yayınlanmamış durumda beklediğini doğrula.
- [ ] Redpanda yeniden açıldığında outbox'ın event'leri yayınladığını doğrula.
- [ ] Worker'ı işlem sırasında durdur ve offset'in erken commit edilmediğini doğrula.
- [ ] Aynı transaction ID'yi tekrar gönder ve duplicate prediction/alert oluşmadığını doğrula.
- [ ] Geçersiz event gönder ve DLQ akışını doğrula.
- [ ] PostgreSQL kapalıyken readiness endpoint'inin başarısız olduğunu doğrula.

## Faz 1 kabul kriterleri

- [ ] Temiz bir makinede belgelenmiş komutlarla sistem başlatılabiliyor.
- [ ] En az bir APPROVE, bir MANUAL_REVIEW ve bir BLOCK akışı uçtan uca çalışıyor.
- [ ] Broker kesintisi ve duplicate event testleri veri tutarlılığını bozmuyor.
- [ ] Doğrulama sonuçları ekran görüntüsü veya log çıktılarıyla belgeleniyor.
- [ ] `PROJECT_REPORT.md` ve Türkçe sürümü gerçek doğrulama sonucuna göre güncelleniyor.

---

# Faz 2 — Integration ve Contract Testleri

**Öncelik:** P0
**Amaç:** SQLite birim testlerinin ötesinde gerçek altyapı davranışını otomatik doğrulamak.

## 2.1 PostgreSQL integration testleri

- [ ] Testcontainers veya ayrı test Compose profili seç.
- [ ] Migration'ların boş PostgreSQL üzerinde baştan sona çalışmasını test et.
- [ ] Downgrade/upgrade davranışını desteklenen ölçüde test et.
- [ ] Transaction, prediction, alert, outbox ve label atomicity'sini test et.
- [ ] `(user_id, timestamp)` geçmiş sorgusunun doğru sıralama ve filtreleme yaptığını test et.
- [ ] Aynı transaction ID ile eşzamanlı isteklerde idempotency'yi test et.
- [ ] Connection pool exhaustion ve timeout davranışını test et.
- [ ] JSON kolonları ve timezone-aware timestamp davranışını doğrula.

## 2.2 Redpanda/Kafka integration testleri

- [ ] Test sırasında gerekli topic'leri otomatik oluştur.
- [ ] Producer serialization contract'ını doğrula.
- [ ] Consumer'ın başarılı işlem sonrası offset commit ettiğini doğrula.
- [ ] Veritabanı hatasında offset'in commit edilmediğini doğrula.
- [ ] Poison message'ın DLQ'ya taşındığını doğrula.
- [ ] Outbox publisher retry ve duplicate-delivery davranışını test et.
- [ ] Consumer group restart sonrasında doğru offset'ten devam edildiğini doğrula.
- [ ] Event key olarak transaction ID kullanımını doğrula.

## 2.3 API contract testleri

- [ ] OpenAPI şemasını test artifact'ı olarak üret.
- [ ] Request/response örneklerinin şemayla uyumlu olduğunu doğrula.
- [ ] Geçersiz timezone, amount, IP, country, currency ve channel girdilerini test et.
- [ ] Pagination, limit ve tüm transaction filtrelerini test et.
- [ ] Investigation response'un eski/null snapshot durumunu test et.
- [ ] Alert state transition tablosunu eksiksiz test et.
- [ ] Fraud/legitimate resolution'ın atomik label upsert yaptığını test et.
- [ ] Aynı resolution tekrarının idempotent, çelişen resolution'ın `409` olduğunu doğrula.

## 2.4 Schema compatibility

- [ ] Event payload'larına açık `schema_version` alanı eklenmesini değerlendir.
- [ ] Backward-compatible alan ekleme kurallarını belgeleyin.
- [ ] Consumer'ın bilinmeyen opsiyonel alanları nasıl ele alacağını belirleyin.
- [ ] Breaking change için yeni topic veya yeni major schema sürümü politikası oluşturun.
- [ ] JSON Schema, Pydantic schema veya Schema Registry seçeneklerinden birini uygulayın.

## Faz 2 kabul kriterleri

- [ ] CI içinde gerçek PostgreSQL ve Redpanda kullanan testler çalışıyor.
- [ ] Başarısız altyapı senaryoları deterministic olarak test ediliyor.
- [ ] Event ve API contract değişiklikleri otomatik yakalanıyor.
- [ ] Testler yerel geliştirme için tek komutla çalıştırılabiliyor.

---

# Faz 3 — Performans Benchmark'ı ve Optimizasyon

**Öncelik:** P0/P1
**Amaç:** Uydurma sayı kullanmadan gerçek latency ve throughput sonucu üretmek.

## 3.1 Benchmark metodolojisi

- [ ] Test makinesinin CPU, RAM, işletim sistemi ve Docker kaynaklarını kaydet.
- [ ] Bootstrap model ile trained champion sonuçlarını ayrı ölç.
- [ ] Soğuk başlangıç ve sıcak çalışma sonuçlarını ayır.
- [ ] En az 5 dakikalık warm-up uygula.
- [ ] En az üç bağımsız benchmark koşusu yap.
- [ ] Ortalama, p50, p95, p99, maksimum latency ve requests/sec kaydet.
- [ ] Hata oranı ve timeout sayısını raporla.
- [ ] API latency ile Kafka end-to-end processing latency'yi ayrı ölç.
- [ ] Veritabanı query süreleri ve connection-pool kullanımını izle.
- [ ] Consumer lag'i benchmark boyunca kaydet.

## 3.2 Locust senaryoları

- [ ] Düşük yük: 1–5 eşzamanlı kullanıcı.
- [ ] Orta yük: 25–50 eşzamanlı kullanıcı.
- [ ] Yüksek yük: sistem hata oranı yükselene kadar kademeli artış.
- [ ] Normal/review/block işlem oranları gerçekçi karışımda üret.
- [ ] Unique transaction ID ve tekrarlanan idempotency isteklerini ayrı senaryo yap.
- [ ] Transaction oluşturma, feed sorgulama ve investigation endpoint'lerini ayrı ölç.
- [ ] Dashboard kaynaklı read yükünü benchmark'a dahil et.

## 3.3 Profiling ve iyileştirme

- [ ] Feature hesaplama CPU süresini profille.
- [ ] PostgreSQL geçmiş sorgularını `EXPLAIN ANALYZE` ile incele.
- [ ] Gerekli composite/partial indeksleri değerlendir.
- [ ] SQLAlchemy session ve connection pool ayarlarını optimize et.
- [ ] Model yüklemenin yalnızca process başlangıcında gerçekleştiğini doğrula.
- [ ] Gereksiz DataFrame oluşturma/copy işlemlerini azalt.
- [ ] SHAP işlemlerinin authorization latency'sine girmediğini ölçerek kanıtla.
- [ ] Dashboard cache TTL ve API sorgu hacmini optimize et.

## 3.4 Benchmark raporu

- [ ] `docs/BENCHMARKS.md` oluştur.
- [ ] Test ortamını ve komutları eksiksiz yaz.
- [ ] Ham Locust CSV/JSON çıktılarını artifact olarak sakla.
- [ ] Sonuç grafiklerinde hata barları veya koşular arası varyansı göster.
- [ ] Ölçülmeyen değerleri açıkça “ölçülmedi” olarak işaretle.
- [ ] CV maddelerine yalnızca tekrar üretilebilir sonuçları ekle.

## Faz 3 kabul kriterleri

- [ ] Gerçek p50/p95/p99 ve throughput ölçümleri mevcut.
- [ ] Benchmark komutları başka bir geliştirici tarafından tekrar çalıştırılabilir.
- [ ] En az bir ölçülmüş bottleneck bulunup iyileştirilmiş.
- [ ] Önce/sonra sonuçları dürüst biçimde karşılaştırılmış.

---

# Faz 4 — Model Recall ve Kalite İyileştirmesi

**Öncelik:** P1
**Amaç:** 0.3108 recall değerini müşteri sürtünmesini kontrol altında tutarak iyileştirmek.

## 4.1 Veri ve feature analizi

- [ ] False-negative işlemleri ayrı analiz et.
- [ ] False-positive işlemleri ayrı analiz et.
- [ ] Hataları amount, country, merchant category, channel, hour ve user history segmentlerine ayır.
- [ ] Fraud örneklerinde eksik sinyal veya pattern olup olmadığını incele.
- [ ] Feature distribution'larını train/selection/test arasında karşılaştır.
- [ ] Missing-value ve outlier davranışını belgeleyin.
- [ ] Feature importance ile SHAP global summary üretin.
- [ ] Yüksek importance gösteren feature'larda leakage ihtimalini yeniden denetleyin.

## 4.2 Yeni feature adayları

- [ ] Merchant risk rate'i yalnızca geçmiş veriden ve smoothing ile hesapla.
- [ ] Device başına benzersiz user sayısı ekle.
- [ ] IP başına kısa süreli user/transaction velocity ekle.
- [ ] User-device ve user-merchant ilişki yaşını ekle.
- [ ] Merchant-category bazında kullanıcı harcama sapması ekle.
- [ ] Gece/saat alışkanlığı sapması ekle.
- [ ] Country transition ve geo-distance feature'larını geliştir.
- [ ] Terminal/entity frequency encoding ekle.
- [ ] Rolling decline/approval pattern feature'larını değerlendir.
- [ ] Graph tabanlı shared-device/shared-IP risk feature'larını prototiple.

Her yeni feature için:

- [ ] Inference anında gerçekten mevcut olduğunu kanıtla.
- [ ] Online ve offline hesaplamanın aynı sonucu verdiğini test et.
- [ ] Feature'ın target veya gelecek olay bilgisi kullanmadığını doğrula.
- [ ] Ablation test ile gerçek katkısını ölç.

## 4.3 Model deneyleri

- [ ] XGBoost için kontrollü hyperparameter search yap.
- [ ] LightGBM adayını ekle.
- [ ] CatBoost'u kategorik feature'lar için değerlendir.
- [ ] Focal-loss veya custom cost-sensitive objective seçeneklerini incele.
- [ ] Segment bazlı model ile tek global modeli karşılaştır.
- [ ] Isolation Forest gibi unsupervised skorları yalnızca ek feature olarak değerlendir.
- [ ] Probability calibration için sigmoid ve isotonic yöntemlerini karşılaştır.
- [ ] Calibration curve, Brier score ve expected calibration error raporla.

## 4.4 Eşik ve maliyet duyarlılığı

- [ ] Review capacity değerini %1, %3, %5 ve %10 için test et.
- [ ] Fraud catch rate varsayımına sensitivity analysis uygula.
- [ ] Customer friction ve investigation cost değişimlerini test et.
- [ ] Precision/recall/cost frontier grafiği üret.
- [ ] Tek eşik ile çift eşik politikasını karşılaştır.
- [ ] Segment bazlı threshold kullanımını değerlendir.
- [ ] Eşiklerin calibration değişimine karşı stabilitesini ölç.

## Faz 4 kabul kriterleri

- [ ] Yeni model dokunulmamış zamansal testte değerlendirilmiş.
- [ ] Recall iyileşmesi precision, review kapasitesi ve expected cost ile birlikte raporlanmış.
- [ ] Eski test setine tekrar tekrar bakılarak model seçimi yapılmamış.
- [ ] Gerekirse yeni bir final holdout dönemi ayrılmış.
- [ ] Champion değişimi açık gate'lerden ve manuel onaydan geçmiş.

---

# Faz 5 — Feature Store ve Online/Offline Tutarlılık

**Öncelik:** P1/P2
**Amaç:** Her işlemde PostgreSQL geçmişi taramak yerine ölçeklenebilir point-in-time feature yaklaşımı geliştirmek.

## 5.1 Feature sözleşmesi

- [ ] Tüm model feature'larını isim, tip, varsayılan değer ve açıklamayla merkezi registry'de tanımla.
- [ ] Feature schema/version bilgisini model artifact'ına ekle.
- [ ] API/worker yüklenen model ile feature schema uyumsuzsa readiness'i başarısız yap.
- [ ] Feature null/NaN/inf politikalarını açıkça tanımla.
- [ ] Feature freshness ve event-time alanlarını belirle.

## 5.2 Online aggregate prototipi

- [ ] Redis veya uygun local online store ekle.
- [ ] 1m/5m/1h/24h transaction count aggregate'lerini tut.
- [ ] Rolling amount ve unique entity state'ini tut.
- [ ] Atomic update ve TTL davranışını tasarla.
- [ ] Out-of-order event davranışını açıkça belirle.
- [ ] Redis unavailable durumunda fallback politikasını tanımla.
- [ ] PostgreSQL history sonucu ile online store sonucunu shadow mode'da karşılaştır.

## 5.3 Stream processing seçeneği

- [ ] Flink, Kafka Streams veya Python tabanlı basit stateful worker seçeneklerini karşılaştır.
- [ ] Event-time ve watermark gereksinimlerini yaz.
- [ ] Late event correction yaklaşımını tasarla.
- [ ] State checkpoint/recovery davranışını test et.
- [ ] Partition key'in user/entity state doğruluğunu koruduğunu doğrula.

## Faz 5 kabul kriterleri

- [ ] Online feature üretimi belirlenen latency bütçesine uyuyor.
- [ ] Offline ve online feature parity otomatik testle doğrulanıyor.
- [ ] Store kesintisindeki sistem davranışı açık ve test edilmiş.
- [ ] Feature version, model version ile birlikte izlenebiliyor.

---

# Faz 6 — Dashboard ve Fraud Investigation Deneyimi

**Öncelik:** P1
**Amaç:** Dashboard'u gerçek bir fraud operations arayüzüne yaklaştırmak.

## 6.1 Overview geliştirmeleri

- [ ] KPI kartlarına önceki dönem karşılaştırması ekle.
- [ ] Zaman aralığına göre fraud rate ve karar oranlarını göster.
- [ ] Estimated fraud prevented değerini yalnızca açık varsayımlarla hesapla.
- [ ] Veri yokken veya API erişilemezken profesyonel empty/error state göster.
- [ ] Otomatik refresh aralığını kullanıcı tarafından ayarlanabilir yap.
- [ ] Filtrelerin URL/session state içinde korunmasını değerlendir.

## 6.2 Investigation paneli

- [ ] Transaction özetini okunabilir kartlarla göster.
- [ ] Risk score ile fraud probability ayrımını açıklığa kavuştur.
- [ ] Model faktörleri ile rule trigger'larını ayrı bölümlerde göster.
- [ ] Current amount ile user mean/median karşılaştırmasını grafikleştir.
- [ ] Velocity feature'larını zaman çizelgesinde göster.
- [ ] Device, IP, country ve merchant novelty bilgilerini belirginleştir.
- [ ] Impossible travel için önceki/mevcut konum ve hesaplanan hızı göster.
- [ ] Aynı kullanıcının son işlemlerini karar renkleriyle göster.
- [ ] Feature snapshot eksikse nedenini açıkça bildir.
- [ ] SHAP pending/fallback/complete durumlarını ayrı göster.

## 6.3 Analyst workflow

- [ ] Analyst kimliği ekle.
- [ ] Case assignment desteği ekle.
- [ ] OPEN, IN_REVIEW, ESCALATED, RESOLVED durumlarını değerlendir.
- [ ] Note history'yi tek metin alanı yerine zaman damgalı kayıtlar olarak sakla.
- [ ] Resolution reason code'ları ekle.
- [ ] Fraud type seçenekleri ekle: account takeover, stolen card, merchant fraud vb.
- [ ] SLA süresi ve aging göstergesi ekle.
- [ ] Case state değişiklikleri için audit log tut.
- [ ] Optimistic locking ile iki analyst'in çakışan güncellemelerini önle.

## 6.4 Analitik görünümler

- [ ] Fraud by country haritası.
- [ ] Merchant category bazında fraud oranı.
- [ ] Saat/gün bazında fraud trendi.
- [ ] Risk score histogram ve karar eşikleri.
- [ ] Model version bazında karar/performance karşılaştırması.
- [ ] Confirmed label maturity grafiği.
- [ ] Drift geçmişi ve feature bazında drift trendi.
- [ ] Alert resolution time ve analyst queue metrikleri.

## Faz 6 kabul kriterleri

- [ ] Bir analyst transaction feed'den vakayı açıp kanıtları inceleyebiliyor.
- [ ] Case üzerinde not, durum ve resolution güvenli şekilde saklanıyor.
- [ ] Resolution confirmed label'a dönüşüyor ve performance metriğine yansıyor.
- [ ] Dashboard hata/boş/yavaş API durumlarında anlaşılır davranıyor.

---

# Faz 7 — Observability ve Operasyonel Güvenilirlik

**Öncelik:** P1/P2
**Amaç:** Sistemin yalnızca çalışması değil, neden çalışmadığının hızlı anlaşılması.

## 7.1 Structured logging

- [ ] Tüm servislerde ortak log schema tanımla.
- [ ] `request_id`, `transaction_id`, `model_version`, `event_id` ve `service` alanlarını standardize et.
- [ ] PII ve secret değerlerin log'lanmasını engelle.
- [ ] Exception stack trace'lerinin gerekli bağlamı içerdiğini doğrula.
- [ ] Log level'ları environment üzerinden yönet.
- [ ] Kritik olay isimlerini standardize et: `transaction_received`, `features_generated`, `prediction_completed`, `alert_created`, `outbox_retry`, `drift_detected`.

## 7.2 Metrics

- [ ] API request count, status ve latency histogram'ları.
- [ ] Inference p50/p95/p99.
- [ ] Feature computation latency.
- [ ] Decision dağılımı.
- [ ] Prediction probability/risk-score dağılımı.
- [ ] Kafka consumer lag.
- [ ] Outbox pending/oldest age/retry count.
- [ ] DLQ message count.
- [ ] Database pool usage ve query latency.
- [ ] Alert queue size ve resolution latency.
- [ ] Label arrival delay.
- [ ] Model version ve feature schema version bilgisi.

## 7.3 Tracing

- [ ] OpenTelemetry entegrasyonunu değerlendir.
- [ ] HTTP request'ten database ve outbox'a trace context taşı.
- [ ] Kafka header'larında trace context yayınla.
- [ ] Consumer, explainer ve monitoring span'lerini bağla.
- [ ] Sampling oranı ve high-cardinality politikasını belirle.

## 7.4 Alerting ve SLO

- [ ] API availability SLO tanımla.
- [ ] p95 inference latency SLO tanımla; gerçek benchmark sonrası değer ver.
- [ ] Error-rate alarmı oluştur.
- [ ] Consumer lag alarmı oluştur.
- [ ] Outbox age alarmı oluştur.
- [ ] DLQ artış alarmı oluştur.
- [ ] Drift alarmının bilgi/uyarı seviyesini belirle.
- [ ] Label-based performance düşüş alarmı oluştur.
- [ ] Runbook linklerini Grafana alarm açıklamalarına ekle.

## Faz 7 kabul kriterleri

- [ ] Tek bir transaction'ın API veya Kafka'dan son duruma kadar izi bulunabiliyor.
- [ ] Broker, database ve model hataları dashboard/alarm üzerinden ayırt edilebiliyor.
- [ ] SLO değerleri gerçek ölçümlere dayanıyor.
- [ ] Her kritik alarm için uygulanabilir runbook mevcut.

---

# Faz 8 — Security, Privacy ve Compliance Temelleri

**Öncelik:** P1/P2
**Amaç:** Portfolio seviyesinde dahi güvenlik sınırlarını gerçekçi biçimde göstermek.

## 8.1 Authentication ve authorization

- [ ] API için OAuth2/OIDC veya JWT doğrulaması ekle.
- [ ] `payment_service`, `analyst`, `admin`, `monitoring` rollerini tanımla.
- [ ] Endpoint bazında least-privilege authorization uygula.
- [ ] Analyst resolution işlemlerini kimlik ile audit et.
- [ ] Service-to-service credential yaklaşımını belgeleyin.

## 8.2 Secret ve configuration güvenliği

- [ ] `.env` dosyasının Git'e girmediğini doğrula.
- [ ] Örnek credential'ların yalnızca local development için olduğunu açıkça yaz.
- [ ] Production için secrets manager yaklaşımı belgele.
- [ ] Credential rotation prosedürü ekle.
- [ ] Container log ve error mesajlarında connection string sızıntısını engelle.

## 8.3 Veri güvenliği

- [ ] TLS kullanımını local/prod ayrımıyla tanımla.
- [ ] PostgreSQL encryption-at-rest beklentisini belgeleyin.
- [ ] IP/device gibi alanlar için retention süresi belirle.
- [ ] Gereksiz PII toplamamayı temel kural yap.
- [ ] Dashboard'da hassas alanları maskele.
- [ ] Analyst export işlemlerini sınırla ve audit et.
- [ ] Veri silme/anonimleştirme workflow'unu tasarla.

## 8.4 Abuse ve API koruması

- [ ] Request body size limiti.
- [ ] Rate limiting.
- [ ] Replay koruması ve idempotency key politikası.
- [ ] CORS politikasını production için sınırla.
- [ ] Dependency vulnerability scanning ekle.
- [ ] Container image scanning ekle.
- [ ] Static security scan ve secret scan ekle.

## 8.5 Compliance sınırları

- [ ] Projenin PCI-DSS uyumlu olduğu iddia edilmemeli.
- [ ] Hangi PCI/GDPR kontrollerinin eksik olduğu belgelenmeli.
- [ ] Model kararlarının human-review ve appeal gereksinimleri tartışılmalı.
- [ ] Bias/fairness ve yasaklı feature kullanım politikası eklenmeli.

## Faz 8 kabul kriterleri

- [ ] Public endpoint'ler authentication olmadan kritik mutation yapamıyor.
- [ ] Analyst işlemleri kimlik ve audit izi içeriyor.
- [ ] Secret/PII sızıntısı için otomatik kontroller mevcut.
- [ ] Compliance iddiaları projenin gerçek kapsamıyla uyumlu.

---

# Faz 9 — MLOps ve Model Yaşam Döngüsü

**Öncelik:** P1
**Amaç:** Eğitimden production champion'a kadar kontrollü ve tekrar üretilebilir süreç.

## 9.1 Reproducibility

- [ ] Python/dependency lock dosyası oluştur.
- [ ] Random seed'leri merkezi yapılandır.
- [ ] Dataset URL, hash ve preprocessing sürümünü artifact'a yaz.
- [ ] Git commit SHA'sını MLflow run'a kaydet.
- [ ] Feature schema sürümünü kaydet.
- [ ] Eğitim environment bilgisini kaydet.
- [ ] Aynı input ve configuration ile sonucu yeniden üretme testi yap.

## 9.2 Model registry

- [ ] Candidate, challenger, champion ve archived state'lerini netleştir.
- [ ] Model alias veya stage geçiş sürecini tanımla.
- [ ] Manual approval kaydını tut.
- [ ] Promotion gate sonuçlarını artifact olarak sakla.
- [ ] Rollback prosedürü oluştur.
- [ ] API'nin model reload veya restart davranışını belirle.

## 9.3 Model validation gate'leri

- [ ] Feature schema eşleşmesi.
- [ ] NaN/inf kontrolü.
- [ ] Probability range kontrolü.
- [ ] PR-AUC minimum gate.
- [ ] Recall decline gate.
- [ ] Expected-cost gate.
- [ ] Calibration gate.
- [ ] Segment performance gate.
- [ ] Inference latency ve artifact size gate.
- [ ] Explainability compatibility kontrolü.

## 9.4 Canary ve shadow yaklaşımı

- [ ] Challenger'ı shadow mode'da çalıştır.
- [ ] Champion/challenger prediction farklarını sakla.
- [ ] Karar değişikliklerini ve segment bazlı farkları analiz et.
- [ ] Canary trafik oranını yapılandırılabilir yap.
- [ ] Otomatik rollback kriterlerini tanımla.
- [ ] Gerçek label'lar olgunlaşmadan performans sonucu iddia etme.

## 9.5 Retraining trigger'ları

- [ ] Manuel trigger.
- [ ] Drift eşiği trigger'ı.
- [ ] Label-based performance düşüşü trigger'ı.
- [ ] Zaman bazlı periyodik trigger.
- [ ] Minimum yeni etiket sayısı koşulu.
- [ ] Trigger'ın otomatik training başlatabileceğini fakat otomatik promotion yapmayacağını koru.

## Faz 9 kabul kriterleri

- [ ] Her production modelinin veri, kod, config ve metric lineage'ı bulunuyor.
- [ ] Challenger başarısız gate ile production'a geçemiyor.
- [ ] Champion rollback işlemi belgeli ve test edilmiş.
- [ ] MLflow UI model yaşam döngüsünü anlaşılır biçimde gösteriyor.

---

# Faz 10 — CI/CD ve Kod Kalitesi

**Öncelik:** P1
**Amaç:** Her değişiklikte kalite, test ve build kontrollerini otomatikleştirmek.

## 10.1 Pull request kontrolleri

- [ ] Ruff lint.
- [ ] Ruff format check.
- [ ] Mypy.
- [ ] Pytest unit testleri.
- [ ] PostgreSQL/Redpanda integration testleri.
- [ ] Alembic migration testi.
- [ ] Docker image build.
- [ ] Dependency ve secret scan.
- [ ] Minimum coverage threshold.
- [ ] OpenAPI/schema diff kontrolü.

## 10.2 Release pipeline

- [ ] Semantic version yaklaşımı belirle.
- [ ] Git tag ile image tag eşleştir.
- [ ] Immutable image digest kullan.
- [ ] Artifact/model ile servis sürümü compatibility kontrolü yap.
- [ ] Migration'ları deployment öncesinde güvenli adım olarak çalıştır.
- [ ] Staging smoke test uygula.
- [ ] Canary/rolling deployment ekle.
- [ ] Başarısız health/SLO durumunda rollback yap.

## 10.3 Repository hijyeni

- [ ] Generated data, model artifact, MLflow run ve local database politikasını netleştir.
- [ ] Büyük binary'ler için Git LFS veya external artifact storage değerlendir.
- [ ] Pre-commit hook ekle.
- [ ] CODEOWNERS ve PR template ekle.
- [ ] Issue template ve contribution rehberi ekle.
- [ ] Commit mesajı ve branch standardı belirle.

## Faz 10 kabul kriterleri

- [ ] Hatalı lint/type/test/build içeren değişiklik merge edilemiyor.
- [ ] Release artifact'ları sürümlü ve tekrar üretilebilir.
- [ ] Deployment ve rollback otomatik veya açıkça belgeli.

---

# Faz 11 — Cloud Deployment

**Öncelik:** P2
**Amaç:** Sistemi public demo veya staging ortamına güvenli biçimde taşımak.

## 11.1 Mimari seçimi

- [ ] AWS, GCP veya Azure hedefini seç.
- [ ] Kubernetes ile daha yönetilen container platformunu karşılaştır.
- [ ] Managed PostgreSQL seç.
- [ ] Managed Kafka/Redpanda Cloud seçeneğini değerlendir.
- [ ] Artifact storage için object storage kullan.
- [ ] Managed secrets ve monitoring hizmetlerini belirle.
- [ ] Tahmini aylık maliyeti çıkar.

## 11.2 Infrastructure as Code

- [ ] Terraform veya Pulumi seç.
- [ ] Network/VPC/subnet/firewall tanımları.
- [ ] Database ve broker kaynakları.
- [ ] Container registry.
- [ ] Compute ve autoscaling.
- [ ] Secret/identity/role tanımları.
- [ ] Monitoring ve log sink'leri.
- [ ] Staging ve production environment ayrımı.

## 11.3 Deployment doğrulaması

- [ ] HTTPS endpoint.
- [ ] Authentication.
- [ ] Migration.
- [ ] Model artifact erişimi.
- [ ] Kafka event akışı.
- [ ] Dashboard erişimi.
- [ ] Prometheus/Grafana veya managed observability.
- [ ] Backup/restore testi.
- [ ] Zone failure veya instance restart testi.

## Faz 11 kabul kriterleri

- [ ] Public veya sınırlı erişimli staging URL'si mevcut.
- [ ] Secret'lar source code veya image içinde değil.
- [ ] Deployment IaC ile tekrar kurulabiliyor.
- [ ] Maliyet ve operasyonel sınırlamalar belgelenmiş.

---

# Faz 12 — Veri ve Model Monitoring Olgunlaştırma

**Öncelik:** P2
**Amaç:** Tek drift alarmı yerine anlamlı ve segment bazlı model sağlığı takibi.

## 12.1 Data quality

- [ ] Şema uyuşmazlığı.
- [ ] Null oranları.
- [ ] Geçersiz kategoriler.
- [ ] Amount sınırları ve outlier oranı.
- [ ] Timestamp gecikmesi ve future timestamp.
- [ ] Duplicate transaction oranı.
- [ ] Country/currency/channel cardinality değişimi.
- [ ] Feature NaN/inf oranı.

## 12.2 Drift

- [ ] Numeric feature'lar için PSI/KS geçmişi.
- [ ] Categorical feature'lar için Jensen–Shannon geçmişi.
- [ ] Prediction/risk-score drift.
- [ ] Segment bazında country/channel/merchant-category drift.
- [ ] Multiple-testing ve küçük sample etkisini değerlendir.
- [ ] Drift threshold'larını reference window'a göre kalibre et.
- [ ] Seasonal davranış için karşılaştırma pencereleri ekle.

## 12.3 Performance monitoring

- [ ] Label maturity window tanımla.
- [ ] Model version bazında precision/recall/F1/PR-AUC.
- [ ] Segment bazında performance.
- [ ] Review acceptance ve fraud-confirmation oranı.
- [ ] Calibration drift.
- [ ] Expected business cost trendi.
- [ ] Confidence interval veya minimum sample uyarısı.
- [ ] Selection bias ve yalnızca incelenen vakaların hızlı etiketlenmesi sorununu belgeleyin.

## 12.4 Rapor saklama

- [ ] Drift/performance report schema'sını sürümlendir.
- [ ] Reference ve current window sınırlarını sakla.
- [ ] Kullanılan metric implementation sürümünü sakla.
- [ ] Dashboard'da report history ve karşılaştırma sun.
- [ ] Alert/retraining trigger ile rapor arasında lineage kur.

## Faz 12 kabul kriterleri

- [ ] Drift ve gerçek performans düşüşü birbirinden ayrılıyor.
- [ ] Yetersiz etiket olduğunda sistem yanıltıcı metric göstermiyor.
- [ ] Her model sürümünün zaman içindeki sağlığı izlenebiliyor.

---

# Faz 13 — Fault Tolerance ve Disaster Recovery

**Öncelik:** P2
**Amaç:** Kritik dependency kesintilerinde tanımlı ve test edilmiş davranış.

## 13.1 Retry politikaları

- [ ] Database, broker ve external artifact erişimi için ayrı retry politikaları.
- [ ] Exponential backoff ve jitter.
- [ ] Retry edilebilir/edilemez hata sınıfları.
- [ ] Maksimum deneme ve DLQ politikası.
- [ ] Retry storm önlemek için circuit breaker.

## 13.2 Graceful shutdown

- [ ] API yeni istek almayı bırakıp devam edenleri tamamlıyor.
- [ ] Worker offset commit sırasını koruyor.
- [ ] Outbox batch yarım kalırsa güvenli tekrar çalışıyor.
- [ ] Consumer group rebalance sırasında duplicate business effect oluşmuyor.

## 13.3 Backup ve restore

- [ ] PostgreSQL otomatik backup politikası.
- [ ] Point-in-time recovery.
- [ ] Model artifact backup/versioning.
- [ ] MLflow metadata backup.
- [ ] Restore tatbikatı ve ölçülen RPO/RTO.

## 13.4 Runbook'lar

- [ ] API down.
- [ ] PostgreSQL unavailable.
- [ ] Kafka unavailable veya high lag.
- [ ] Outbox backlog.
- [ ] DLQ spike.
- [ ] Model artifact load failure.
- [ ] Drift alarmı.
- [ ] Performance düşüşü.
- [ ] Yanlış model rollout ve rollback.

## Faz 13 kabul kriterleri

- [ ] Her kritik kesinti senaryosu için beklenen davranış tanımlı.
- [ ] Chaos/smoke testiyle en az temel senaryolar doğrulanmış.
- [ ] Backup'tan restore işlemi gerçekten denenmiş.

---

# Faz 14 — Dokümantasyon ve Portfolio Sunumu

**Öncelik:** P1
**Amaç:** Teknik recruiter'ın birkaç dakikada değeri görmesi, adayın her kararı savunabilmesi.

## 14.1 README

- [ ] Güncel architecture diagram.
- [ ] Tek komutlu quick start.
- [ ] Servis URL ve port tablosu.
- [ ] Demo işlem komutları.
- [ ] Dashboard ekran görüntüleri.
- [ ] Gerçek model sonuç tablosu.
- [ ] Gerçek benchmark tablosu; ölçülmediyse açıkça belirt.
- [ ] “Implemented”, “verified” ve “planned” ayrımını koru.
- [ ] Known limitations bölümünü güncel tut.

## 14.2 Mimari ve modelleme dokümanları

- [ ] Diyagramları gerçek kodla eşleştir.
- [ ] Topic ve event akışlarını güncelle.
- [ ] Database schema/ER diagram ekle.
- [ ] Feature availability ve leakage tablosu ekle.
- [ ] Model comparison tablosunu otomatik artifact'tan üret.
- [ ] Threshold/cost frontier grafiği ekle.
- [ ] Calibration ve confusion matrix artifact'ları ekle.

## 14.3 Teknik walkthrough

- [ ] Kod değiştikçe İngilizce ve Türkçe sürümleri senkron tut.
- [ ] Her ana component için input/output ve failure mode yaz.
- [ ] Gerçek transaction örneğini güncel endpoint ve sınıflarla eşleştir.
- [ ] Uygulanan ile production'da gerekeni açıkça ayır.
- [ ] Stripe-scale bölümündeki hiçbir throughput değerini proje sonucu gibi göstermeme kuralını koru.

## 14.4 Mülakat ve CV çıktıları

- [ ] CV maddelerini yalnızca gerçek sonuçlara göre güncelle.
- [ ] Benchmark sonrası doğrulanmış latency/throughput maddesi ekle.
- [ ] Recall sınırlamasını saklamadan açıklamaya devam et.
- [ ] STAR formatında 3–5 proje hikâyesi hazırla.
- [ ] Architecture trade-off, incident ve model trade-off anlatımları hazırla.
- [ ] 30 saniye, 2 dakika ve 10 dakikalık proje anlatımları hazırla.

## Faz 14 kabul kriterleri

- [ ] Dokümantasyon gerçek kod ve doğrulanmış sonuçlarla tutarlı.
- [ ] İngilizce ve Türkçe kritik dokümanlar aynı kapsamı taşıyor.
- [ ] Ölçülmemiş hiçbir metric CV veya portfolio'da sonuç gibi sunulmuyor.

---

# Faz 15 — İleri Seviye Fraud Detection Araştırmaları

**Öncelik:** P3
**Amaç:** Temel production doğrulaması tamamlandıktan sonra modelleme derinliğini artırmak.

## 15.1 Graph fraud detection

- [ ] User-device-IP-merchant ilişkilerinden graph oluştur.
- [ ] Connected component ve shared-entity feature'ları üret.
- [ ] Degree, pagerank ve community risk sinyallerini değerlendir.
- [ ] Graph feature'larında point-in-time doğruluğu koru.
- [ ] GNN yaklaşımını basit graph feature baseline'ından sonra değerlendir.

## 15.2 Sequence modeling

- [ ] Kullanıcının işlem dizisini sequence olarak temsil et.
- [ ] RNN/Transformer yaklaşımını tree baseline ile karşılaştır.
- [ ] Event-time gap, amount ve category embedding'lerini değerlendir.
- [ ] Latency ve açıklanabilirlik maliyetini ölç.
- [ ] Online inference state yönetimini tasarla.

## 15.3 Anomaly detection

- [ ] Isolation Forest.
- [ ] Autoencoder.
- [ ] Robust z-score veya peer-group anomaly.
- [ ] Unsupervised skorları nihai karar yerine supervised modele ek sinyal olarak kullan.
- [ ] Alert hacmi ve false-positive etkisini ölç.

## 15.4 Adversarial ve feedback-aware sistem

- [ ] Fraudster threshold probing senaryoları simüle et.
- [ ] Rule/model decay için zaman bazlı analiz yap.
- [ ] Investigator feedback kalitesi ve disagreement ölçümü ekle.
- [ ] Active learning ile etiketlenecek vakaları önceliklendirmeyi değerlendir.
- [ ] Exploration/exploitation ve müşteri riski trade-off'unu belgele.

---

# Kısa Vadeli Uygulama Sırası

İlk uygulanması önerilen sıra:

1. **Docker Compose'u gerçek ortamda ayağa kaldır ve uçtan uca doğrula.**
2. **PostgreSQL/Redpanda integration testlerini ekle.**
3. **Locust benchmark'ını çalıştır ve gerçek p50/p95/p99/throughput üret.**
4. **False-negative analizi yaparak recall geliştirmelerine başla.**
5. **Dashboard analyst workflow ve investigation deneyimini olgunlaştır.**
6. **CI pipeline ile test/lint/type/build kontrollerini zorunlu yap.**
7. **Authentication, audit log ve temel security kontrollerini ekle.**
8. **Model registry, shadow/challenger ve rollback akışını güçlendir.**
9. **Cloud staging deployment gerçekleştir.**
10. **Dokümantasyon, CV ve portfolio sonuçlarını yalnızca doğrulanmış yeni bulgularla güncelle.**

---

# Her Değişiklik İçin Definition of Done

Bir görev aşağıdaki koşulların tamamını karşılamadan tamamlandı sayılmamalıdır:

- [ ] Kod modüler ve mevcut architecture sınırlarıyla uyumlu.
- [ ] Type hint'lar ve schema'lar güncel.
- [ ] Unit test eklendi veya mevcut test güncellendi.
- [ ] Gerekliyse integration test eklendi.
- [ ] Ruff başarılı.
- [ ] Mypy başarılı.
- [ ] Pytest başarılı.
- [ ] Migration gerekiyorsa upgrade path test edildi.
- [ ] API/event contract değiştiyse compatibility değerlendirildi.
- [ ] Monitoring/logging etkisi değerlendirildi.
- [ ] Security/privacy etkisi değerlendirildi.
- [ ] README/architecture/modeling/walkthrough dokümanları güncellendi.
- [ ] İngilizce ve Türkçe dokümanlar senkronize edildi.
- [ ] Uydurma metric veya doğrulanmamış iddia eklenmedi.
- [ ] Çalıştırılan komutlar ve gerçek sonuçlar kaydedildi.

---

# Başarı Kriterleri

Projenin bir sonraki olgunluk seviyesine ulaştığı şu kanıtlarla gösterilmelidir:

- Temiz makinede `docker compose up --build` ile çalışan sistem.
- API → model → PostgreSQL → outbox → Redpanda → dashboard uçtan uca doğrulaması.
- Gerçek PostgreSQL ve Redpanda integration testleri.
- Tekrar üretilebilir latency ve throughput benchmark'ı.
- Recall iyileştirmesinin precision, review kapasitesi ve iş maliyetiyle birlikte ölçülmesi.
- Model/data drift ile gecikmeli label performansının ayrı izlenmesi.
- Authentication, role-based access ve analyst audit trail.
- CI/CD ile otomatik lint, type, test, integration ve image-build kontrolleri.
- Champion/challenger, manual promotion, canary ve rollback süreci.
- Gerçek kodu, sonuçları ve sınırlamaları doğru anlatan güncel iki dilli dokümantasyon.

Bu roadmap'in temel ilkesi şudur: yeni bir özellik yalnızca yazıldığı için değil, test edildiği, ölçüldüğü, gözlemlenebildiği ve dürüstçe belgelendiği zaman proje değeri üretir.
