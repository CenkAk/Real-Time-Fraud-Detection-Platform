# Model Monitoring ve Retraining Yaşam Döngüsü

Analyst resolution kararları gecikmeli ground-truth etikettir. Alert çözümüyle atomik biçimde
`confirmed_labels` tablosuna yazılır ve `confirmed_labels.v1` event'i yayınlanır. Etiket monitoring
kanıtını hemen değiştirir; çalışan modelin ağırlığını veya aktif model alias'ını doğrudan değiştirmez.

## Tetikler

- Drift: İki ardışık pencerede PSI `>= 0.20` veya Jensen-Shannon divergence `>= 0.10`.
- Performance: En az 200 confirmed label sonrasında champion test raporuna göre PR-AUC'de göreli
  `>= %10` düşüş veya expected cost'ta `>= %15` artış.
- Manuel: İstek sahibi ve gerekçeyle `POST /admin/retraining-jobs`.

Amount, velocity, country, merchant category, channel ve fraud probability izlenir. Overall population
yanında country/category/channel segment raporları PostgreSQL'de saklanır. Calibration (Brier score)
ve ortalama label gecikmesi trigger metriklerinden ayrı raporlanır.

## Challenger ve promotion

Trigger yalnız idempotent bir queued job oluşturur. Retraining worker temporal pipeline'ı çalıştırır,
MLflow'a challenger kaydeder ve PR-AUC, recall ve business-cost gate'lerini uygular. Gate'leri geçen
challenger bile pasif kalır. Promotion açık API isteği gerektirir; MLflow `champion` alias'ı,
`model_versions` stage'i ve immutable `model_promotions` kaydı birlikte güncellenir. Database hatasında
önceki MLflow alias'ı geri yüklenir.

Aktif API prosesi promoted artifact'i hot-reload etmez. Kontrollü servis restart/model reload hâlâ
gereklidir; bu sınır koordinasyonsuz kısmi rollout'u önler.
