# Modelleme ve Veri Sızıntısı Kontrolleri

## Veri kümesi

Açık Fraud Detection Handbook simülatörü; 183 günlük kronolojik müşteri, terminal, tutar ve fraud etiketi verisi sağlar. Demo, seçilen 249.992 satırı tüm zaman aralığına dağıtır; `full` profil bütün satırları işler. Canlı ödeme şeması `amount > 0` koşulunu gerektirdiği için sıfır tutarlı simülatör artifact'ları temizleme adımında çıkarılır.

Deterministik zenginleştirme, API ile uyumlu merchant category, ülke, kanal, device ve IP değerleri üretir. Fraud satırlarına kuralları çalıştırmak amacıyla account-takeover tarzı device/ülke bağlamı eklenir. Bu bağlam doğrudan etiketten üretildiği için `new_country` ve `new_device`, `FEATURE_COLUMNS` listesinden açıkça çıkarılmıştır ve raporlanan model metriklerine hiçbir zaman katkıda bulunmaz.

## Point-in-time feature'lar

Model girdileri; tutar, saat, haftanın günü, kullanıcının önceki ortalama/medyan tutarı, tutarın ortalamaya oranı, önceki 5 dakika/1 saat/24 saat işlem sayıları ve yeni merchant durumudur. Canlı feature engine ayrıca kurallar ve monitoring için 1 dakikalık işlem sayısını, saatlik tutarı, benzersiz merchant/ülke sayılarını, ülke/device/IP yenilik durumunu, seyahat hızını ve impossible travel değerini hesaplar.

Her rolling hesaplama sol taraftan kapalıdır veya `timestamp < current.timestamp` filtresini uygular. Target, fraud scenario, işlem sonrası outcome, rolling aggregate içindeki mevcut satır ve gelecekteki bütün event'ler kesinlikle kullanılmaz.

## Zamansal değerlendirme

Zamana göre sıralanmış veri; %50 training, %15 model selection, %10 calibration, %10 threshold tuning ve %15 final test olarak ayrılır. Aday seçimi ve calibration final test verisini göremez. Bu yaklaşım, daha sonraki davranışlara yapılan deployment'ı taklit eder ve random karıştırmanın oluşturacağı iyimser sonuçları önler.

## Class imbalance, tuning ve adaylar

Pipeline; class-weighted Logistic Regression, random undersampling ve SMOTE baseline'larını tune edilmiş Random Forest ve XGBoost adaylarıyla karşılaştırır. Sampling yalnızca training partition içinde gerçekleşir. Optuna, varsayılan olarak her tree ailesi için yalnız train ve selection dönemlerini kullanarak 20 trial çalıştırır. Accuracy optimizasyon dışında bırakılmıştır. Seçim expected business cost değerini minimize eder; eşitlikte PR-AUC kullanılır.

Ölçülen Faz 4 koşusunda expected cost değerine göre Random Forest seçilmiştir. Test precision değeri 0.9266, recall 0.3108, F1 0.4654, PR-AUC 0.3363 ve ROC-AUC 0.6677 olarak ölçülmüştür. Yüksek precision ile düşük recall arasındaki ilişki gerçek bir trade-off ve açık geliştirme hedefidir; accuracy arkasına saklanan bir sonuç değildir.

## Deney takibi ve registry

Tek MLflow parent run içinde beş candidate run ve 40 Optuna trial run bulunur. Her nested run dataset SHA-256 fingerprint, Git SHA, parametreler, expected cost ve model metriklerini kaydeder. Final taşınabilir artifact ayrıca feature contract, preprocessing metadata, threshold ve reference distribution bilgilerini içerir. Tamamlanan koşu model version 2'yi `challenger` olarak kaydetmiştir; mevcut version 1 `champion` olarak korunur. Training hiçbir zaman `champion` alias'ını değiştirmez. Bu işlem için ayrı komutta açık `--confirm-champion` bayrağı gerekir.

## Calibration ve eşikler

Fit edilmiş champion model dondurulur ve kendisine ayrılmış dönemde sigmoid ile kalibre edilir. Threshold araması şu maliyetleri kullanır:

- approve edilen ve kaçırılan fraud: işlem tutarı;
- review edilen fraud: yapılandırılmış %80 review yakalama oranından sonra kalan tutar;
- her review: 5 maliyet birimi;
- legitimate block: 25 sürtünme birimi;
- maksimum review kuyruğu: trafiğin %5'i.

Grid search, threshold partition üzerinde review için `0.15`, block için `0.40` üretmiştir. Bu değerler modelle birlikte paketlenir ve configuration, model eşiklerini açıkça devre dışı bırakmadığı sürece deployment sırasında kullanılır. Maliyet birimleri deneyin objective değerleridir; tasarruf edilen gerçek para değildir.

## Açıklanabilirlik ve drift

Artifact, yalnızca alarmlarda çalışan permutation SHAP için 200 satırlık background saklar. Okunabilir feature adları ve signed impact değerleri alert ile birlikte kalıcı olarak saklanır. Drift referans örnekleri tutar, ülke ve fraud probability değerlerini kapsar. Monitoring, numeric dağılımlara PSI ve KS; ülkeye Jensen–Shannon divergence uygular. Eşikler operasyon sinyalidir, concept drift kanıtı değildir; ayrıca doğrulanmış etiketlerde performans düşüşü görülmesi gerekir.

## Sınırlamalar

Sentetik davranış, production ortamındaki saldırgan fraud davranışından daha basittir. Demonun tüm zaman aralığına dağıtılmış örneklemesi geçmişi seyrekleştirir ve bu nedenle velocity'yi yaklaşık olarak temsil eder; daha iyi ardışık doğruluk için `full` profil kullanılmalıdır. Ölçülen tuning koşusu full sequential profil yerine distributed demo dataset'ini kullanmıştır. Etiketler simüle edilmiştir ve probability calibration gerçek ödeme popülasyonlarında değişebilir.
