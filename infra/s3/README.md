# S3 Storage Setup (Backblaze B2 / Wasabi / MinIO)

MindVault raw dosyaları (mail ekleri, telegram foto/voice, calendar export vb.) 
S3 uyumlu bir object storage üzerinde saklanır.

## 🛠️ Seçenekler
- **Prod**: Backblaze B2 veya Wasabi (ucuz, S3 uyumlu, ~ $5/TB)
- **Dev**: MinIO (lokalde, docker compose içinde)

## 📦 Bucket
Varsayılan bucket adı: `mindvault`

### Backblaze B2
1. [Backblaze console](https://secure.backblaze.com/b2_buckets.htm) üzerinden bucket oluştur.
2. Uygulama key ve secret al.
3. `.env` içine ekle:
S3_ENDPOINT=https://s3.eu-central-003.backblazeb2.com
S3_BUCKET=mindvault
S3_REGION=eu-central-003
S3_ACCESS_KEY_ID=xxx
S3_SECRET_ACCESS_KEY=xxx

### Wasabi
1. [Wasabi console](https://console.wasabisys.com) → bucket oluştur.
2. `.env` içine ekle:
S3_ENDPOINT=https://s3.eu-central-1.wasabisys.com
S3_BUCKET=mindvault
S3_REGION=eu-central-1
S3_ACCESS_KEY_ID=xxx
S3_SECRET_ACCESS_KEY=xxx

### MinIO (Local Dev)
Docker compose ile 9000 (S3 API) + 9001 (console) portları açılır.
Kullanıcı/şifre: `minioadmin:minioadmin`

.env içine:
S3_ENDPOINT=http://minio:9000
S3_BUCKET=mindvault
S3_REGION=local
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin

Bucket oluşturmak için:
```bash
docker compose -f docker-compose.dev.yml exec minio \
  mc alias set local http://minio:9000 minioadmin minioadmin && \
  mc mb -p local/mindvault