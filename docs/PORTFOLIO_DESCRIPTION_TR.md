# Portföy Açıklamaları

## GitHub açıklaması

FastAPI, Redpanda, PostgreSQL, kalibre tree modelleri, MLflow, SHAP, drift takibi, Next.js, Grafana ve Docker Compose ile production tarzı gerçek zamanlı fraud detection platformu.

## Portföy sitesi

Senkron API isteklerini ve stream edilen olayları skorlayan, veri sızıntısını önleyen davranışsal özellikler hesaplayan, kararları idempotent olarak saklayan ve şüpheli ödemeleri review veya block akışına yönlendiren uçtan uca bir ödeme fraud platformu geliştirdim. Ayrı bir kronolojik eğitim pipeline'ı model ve class-imbalance stratejilerini karşılaştırıyor, olasılıkları kalibre ediyor, iş eşiklerini optimize ediyor ve sürümleri MLflow'da takip ediyor. Operasyon tarafı gecikmeli etiketler, SHAP, drift takibi, Next.js, Prometheus ve Grafana ile destekleniyor.

## LinkedIn projesi

Kalibre edilmiş bir Random Forest champion model, Kafka uyumlu streaming, PostgreSQL ve FastAPI etrafında production tarzı fraud detection sistemi geliştirdim. 249.992 satırlık ölçülmüş demo, ayrı tutulan zamansal test kümesinde 0.3363 PR-AUC ve 0.9266 precision elde etti. Ayrıca transactional-outbox güvenilirliği, iş maliyetine dayalı karar eşikleri, yalnızca alarmlarda çalışan SHAP, gecikmeli etiket takibi, drift raporları, MLflow, Next.js, Grafana, Docker Compose ve otomatik testler uyguladım. Recall (0.3108), modelin temel geliştirme alanı olarak açıkça belgelenmiştir.

## Teknik özet

Platform, HTTP ve Redpanda consumer'ları arasında tek bir skorlama orchestrator'ı paylaşır. PostgreSQL yalnızca geçmişe dayalı özellikleri sağlar; işlem, tahmin, alarm ve outbox kayıtlarını atomik olarak saklar. Model kalibre edilmiş risk üretirken bağımsız kurallar APPROVE, MANUAL_REVIEW veya BLOCK kararı verir. Beş eğitim stratejisi kronolojik olarak değerlendirilir ve challenger terfisi otomatik değil kontrollüdür.

## Recruiter odaklı özet

Bu proje, bir ML modelini notebook'un ötesine taşıyabildiğimi gösterir: güvenilir veri akışı tasarlamak, tahmin sunmak, streaming ve veritabanlarını bağlamak, dengesiz sınıflar için doğru metrikleri ölçmek, kararları açıklamak, drift'i izlemek, servisleri paketlemek, davranışı test etmek ve sınırlamaları dürüstçe aktarmak.
