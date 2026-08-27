# Doğrulanmış CV Maddesi Seçenekleri

Yalnızca başvurulan role uygun maddeleri kullanın. Aşağıdaki metrikler repository'deki model raporundan alınmıştır; gecikme ve throughput ölçülmediği için bu alanlarda herhangi bir sayı verilmemiştir.

- FastAPI, Redpanda, PostgreSQL, Random Forest/XGBoost deneyleri, MLflow, SHAP, Prometheus/Grafana, Next.js ve Docker Compose kullanarak uçtan uca gerçek zamanlı fraud detection platformu geliştirdim.
- Veri sızıntısını önleyen kronolojik feature pipeline'ları geliştirdim; 249.992 açık sentetik ödeme olayı üzerinde model/class-imbalance stratejilerini karşılaştırarak iş maliyeti optimizasyonuyla Random Forest'ı seçtim.
- Ayrı tutulan zamansal test kümesinde 0.3363 PR-AUC, 0.9266 precision ve 0.4654 F1 elde ederken, ortaya çıkan 0.3108 recall trade-off'unu açıkça belgeledim.
- Kaçırılan fraud, müşteri sürtünmesi, inceleme maliyeti ve review kapasitesini dikkate alarak ayrı 0.15/0.40 review/block eşiklerini optimize eden yapılandırılabilir APPROVE/REVIEW/BLOCK politikası tasarladım.
- Tahminlerin, alarmların ve veritabanı durumunun yeniden denemelerden ve broker kesintilerinden güvenli biçimde toparlanması için idempotent Kafka consumer'ları ve transactional outbox uyguladım.
- Yalnızca alarm işlemlerinde çalışan SHAP açıklamaları, gecikmeli etiketlerle performans takibi, PSI/KS/Jensen–Shannon drift raporları ve otomatik terfi yapmayan kontrollü champion/challenger yeniden eğitim akışı ekledim.
