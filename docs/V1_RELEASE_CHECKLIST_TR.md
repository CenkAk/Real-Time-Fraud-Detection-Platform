# V1 Release Kontrol Listesi

Durum: core kabul 2026-08-27 tarihinde yerelde doğrulandı; final V1 release koşulludur.

- [x] Boş named volume ile Compose, iki production image'ını build etti.
- [x] Açık veri hazırlığı, 40 Optuna trial, MLflow takibi ve registry kaydı tamamlandı.
- [x] Boş PostgreSQL, Alembic head'e kadar migrate edildi.
- [x] Simulator → Redpanda → worker → model → PostgreSQL akışı ID başına tek kalıcı karar üretti.
- [x] APPROVE, MANUAL_REVIEW ve BLOCK kararları gözlendi.
- [x] Alert'lere asenkron SHAP açıklamaları yazıldı.
- [x] Analyst fraud/legitimate çözümü delayed label'ı atomik yazdı.
- [x] Sağlıklı çalışmada outbox pending sayısı sıfıra indi.
- [x] Drift/performance, retraining ve manuel promotion kontrolleri erişilebilir.
- [x] Next.js dashboard, API, MLflow, Prometheus ve Grafana erişilebilir.
- [x] Ruff, strict mypy ve 33 backend unit/contract testi geçti.
- [x] Gerçek PostgreSQL/Redpanda kullanan 2 Testcontainers testi geçti.
- [x] ESLint, TypeScript, Next.js build ve 2 Playwright E2E testi geçti.
- [x] README, rapor, walkthrough, CV ve portföy metinleri ölçülen Random Forest sonucuyla senkron.
- [x] Ölçülmemiş benchmark, fraud prevention veya finansal tasarruf iddiası yok.
- [ ] Üç tekrarlı 10/50/100 kullanıcı API ve 10/50/100 event/s streaming benchmark matrisini yayınla.

Bilinen notlar:

- Kapsamlı performance benchmark matrisi açık kalan tek V1 kanıt kapısıdır; `BENCHMARKS.md` dosyasına bakın.
- `npm audit` iki high-severity bulgu raporluyor; düzeltme Faz 7 kapsamındadır.
- OIDC/RBAC, Redis, schema registry, tracing ve cloud deployment V1 kapsamı dışındadır.
