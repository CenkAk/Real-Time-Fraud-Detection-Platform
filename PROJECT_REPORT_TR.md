# V1 Release Candidate Raporu

Core kabul doğrulaması: 2026-08-27. Final release gate benchmark matrisine bağlıdır.

## Teslim edilenler

V1; FastAPI ve Redpanda ingestion, point-in-time PostgreSQL feature'ları, kalibre risk skoru, ayrı
APPROVE/MANUAL_REVIEW/BLOCK politikası, atomik transaction/prediction/alert/outbox kaydı, asenkron SHAP,
gecikmeli analyst label'ları, drift/performance tetikli challenger işleri, denetlenebilir manuel
promotion, MLflow ve Next.js Fraud Command Center içerir. Prometheus/Grafana yerel sistem görünürlüğü
sağlar.

Eğitim; Logistic Regression ve imbalance baseline'larını Random Forest ile XGBoost için ayrı ayrı 20
Optuna trial ile karşılaştırır. Trial'lar nested MLflow run olarak kaydedilir; calibration, threshold ve
dokunulmamış zamansal test dönemleri ayrıdır. Registry hiçbir modeli otomatik production'a almaz.

## Doğrulama kanıtı

- Boş volume ile `docker compose -p fraud-phase6-clean up -d --build`: public veri bootstrap'ı, 40
  Optuna trial, model kaydı, Alembic `0004_promotion_idempotency` head ve tüm servislerle geçti.
- Simulator → Redpanda → worker → PostgreSQL akışı transaction, prediction ve alert üretti; outbox sıfıra
  indi; explainer SHAP açıklamalarını yazdı.
- Playwright analyst akışı bir alert'i FRAUD olarak çözdü ve atomik confirmed label oluşturdu.
- Backend: Ruff, 34 kaynak dosyada strict mypy ve 33 unit/contract testi geçti.
- Gerçek altyapı: Testcontainers PostgreSQL 16 ve Redpanda testlerinin 2'si de geçti.
- Frontend: ESLint, TypeScript, production build ve 2 Playwright E2E testi geçti.

Komutlar ve gözlenen kanıtlar `docs/PHASE6_ACCEPTANCE.md` dosyasındadır.

## Ölçülen model sonucu

`artifacts/challenger_model_report.json`, 2026-08-26 tarihinde 249.992 açık sentetik event ile üretildi.
Seçilen Random Forest; dokunulmamış zamansal testte 0.9266 precision, 0.3108 recall, 0.4654 F1, 0.3363
PR-AUC, 0.6677 ROC-AUC, 0.000215 false-positive rate ve 0.6892 false-negative rate ölçtü. Review/block
eşikleri 0.15/0.40'tır. Expected cost deneysel seçim hedefidir; gerçek finansal tasarruf iddiası değildir.

## Bilinen sınırlamalar

- Veri sentetiktir; demo örneklemi yoğun ardışık velocity davranışını yalnız yaklaşık temsil eder.
- Recall temel model geliştirme alanıdır.
- 10/50/100 kullanıcı ve streaming benchmark matrisi henüz yayınlanmadı; latency/throughput iddiası yoktur.
- V1'de authentication/RBAC, schema registry, Redis feature store, tracing, cloud deployment, managed
  secrets veya PCI kontrolleri yoktur.
- `npm audit` iki high-severity bulgu raporlar; force-fix uygulanmadı ve Faz 7 supply-chain kapsamına kaydedildi.

## Çalıştırma

`.env.example` dosyasını `.env` olarak kopyalayıp `docker compose up --build` çalıştırın. Fraud Command
Center 8501, Swagger 8000, MLflow 5000, Prometheus 9090 ve Grafana 3000 portundadır.
