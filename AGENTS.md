# AGENTS.md — Stego-Guard

Файл для AI-агентов, работающих с этим репозиторием. Описывает архитектуру,
команды сборки/тестирования и соглашения, **актуальные для текущего кода**.
Главные проектные документы (на русском): `docs/STEGO-GUARD_ARCHITECTURE_v2.md`
(полная архитектура и план фаз) и `docs/STEGO-GUARD_STRUCTURE_v2.txt`
(структура репозитория). Этот файл — сжатая рабочая выжимка; при расхождении
проверяй код.

---

## 1. Что это за проект

Stego-Guard — система защиты цифровых документов (первый домен — сканы
избирательных протоколов) от подделки с помощью невидимых цифровых водяных
знаков. Умеет:

1. **Внедрять метку** в изображение (PNG/JPEG) при выпуске документа;
2. **Проверять подлинность** любой копии: извлекать метку и сверять код
   содержимого с реальным изображением;
3. **Локализовать вмешательство**: тепловая карта (heatmap) зон, изменённых
   после внедрения метки.

Статус и план фаз:

- **Phase 1 — ГОТОВО.** Классический DSP-пайплайн на DWT, три сервиса
  (Go gateway, React frontend, ML на Python), Docker Compose, e2e-тест.
- **Phase 2 — В РАБОТЕ.** Нейросетевой кодировщик–декодировщик
  (encoder-decoder на U-Net): обучение в Google Colab, датасет 2000 + 200
  (train/val) генерируется через `ml-service/scripts/generate_dataset.py`,
  цикл: обучение → веса `.pth` → экспорт в ONNX.
- **Phase 3 — в плане.** PostgreSQL, JWT-аутентификация, пакетная проверка
  (batch verification), поддержка PDF.
- **Phase 4 — в плане.** UI/UX hardening + кибербезопасность
  frontend/backend.
- **Phase 5 — в плане.** Подготовка к сдаче (школьный + региональный этап,
  февраль).

## 2. Стек и архитектура рантайма

Три независимых сервиса, поднимаются одним `docker compose`:

```
Browser ──HTTP──► frontend (nginx, :80, React SPA, прокси /api)
                    │ HTTP/REST
                    ▼
              api-gateway (Go 1.27, Fiber, :8080) ──gRPC──► ml-service (Python 3.13, :50051)
```

- **frontend** — React 18 + TypeScript + Mantine v7 + Vite. Сборка в nginx:alpine.
- **api-gateway** — Go 1.27, Fiber v2, gRPC-клиент к ML-сервису. Мультистейдж
  Dockerfile, статический бинарник (`CGO_ENABLED=0`), рантайм debian:bookworm-slim.
- **ml-service** — Python 3.13, PyWavelets + OpenCV + NumPy (Пока НЕ PyTorch в
  рантайме — torch ставится только в Dockerfile из CPU-индекса PyTorch,
  `requirements.txt` его не содержит намеренно). gRPC-сервер.

Ключевые принципы:

- **ML-сервис наружу не публикуется** — только внутри docker-сети `stego-net`
  (DNS-имя сервиса = имя хоста, см. `deployments/docker-compose.yml`).
- **Единственный источник правды API** — `proto/stego.proto` (пакет `stego.v1`,
  сервис `StegoService`: `EmbedWatermark`, `VerifyDocument`). Менять контракт
  можно только там, затем регенерировать код обеих сторон. Сгенерированный код
  **закоммичен**: `api-gateway/proto-gen/`, `ml-service/app/proto_gen/`.
- **Конфигурация — только переменные окружения** (gateway) или константы в
  `ml-service/app/config.py`. Никаких конфиг-файлов.
- Сервисы stateless; аутентификации и TLS пока нет (внутренний контур, Фаза 1).

### REST-эндпоинты гейтвея

| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/v1/embed` | multipart: `file`, `user_id`. Ответ — защищённый файл на скачивание + заголовки `X-Content-SHA256`, `X-User-Id` |
| POST | `/api/v1/verify` | multipart: `file`. Ответ — JSON: `status` (`AUTHENTIC`/`TAMPERED`/`NO_WATERMARK`), `ber`, `hash_match`, `user_id`, `sha256`, `heatmap_base64` (только при TAMPERED) |
| GET | `/healthz` | healthcheck |

Env-переменные гейтвея: `PORT` (8080), `ML_SERVICE_ADDR` (`ml-service:50051`
в compose / `localhost:50051` локально), `MAX_UPLOAD_MB` (25). Лимит тела и
валидация по магическим байтам PNG/JPEG — на гейтвее (`internal/validation`).

### ML-пайплайн (ml-service/app/)

- `server.py` — gRPC-сервер; все ошибки превращаются в статусы контракта, не
  вылетают. Встроена **защита от перезащиты**: перед embed проверяется преамбула.
- `dwt/transform.py` — внедрение/извлечение: DWT (Haar) по каналу яркости,
  квантование коэффициентов субполос LH/HL с шагом `DELTA=20`; бит несёт группа
  из `REDUNDANCY=5` коэффициентов; метка внедряется **дважды** (копии A и B
  разнесены по изображению — локальное вмешательство разносит копии → растёт
  BER; JPEG портит обе одинаково). Также `content_digest` — код содержимого.
- `dwt/payload.py` — формат метки: 71 байт = магия `"SG"` + версия схемы
  (преамбула, 24 бита) + 32 байта content_hash + user_id (32 байта) + CRC32.
- `dwt/attacks.py` — симулятор атак (JPEG, ресайз, кроп, поворот, шум) для
  обучения и оценки стойкости.
- `verification/ber.py` — BER двух копий; `verification/authenticity.py` —
  дерево вердиктов: `header_ber > 0.3` → `NO_WATERMARK`; `payload_ok` и
  `hash_match` → `AUTHENTIC`; иначе → `TAMPERED`; `verification/heatmap.py` —
  тепловая карта расхождений копий, наложенная на документ.
- Код содержимого — 8×8-сетка субполосы LL, 2 бита/ячейка (16 байт); сравнение
  пороговое: ≤ `CODE_CELL_TOLERANCE=2` расходящихся ячеек. Криптографическая
  сверка SHA-256 сознательно не используется (шум uint8-округления ±2), она
  запланирована на Фазу 2/4 через реестр в БД.
- Пороги и параметры в `app/config.py`: `BER_THRESHOLD=0.05`,
  `HEADER_BER_THRESHOLD=0.3`, `CODE_CELL_TOLERANCE=2`, `MAX_IMAGE_BYTES=25 МБ`.

## 3. Структура репозитория

```
proto/stego.proto            # Контракт stego.v1 — ЕДИНСТВЕННЫЙ источник правды API
api-gateway/                 # Go: cmd/gateway/main.go, internal/{config,handler,
                             #   grpcclient,validation,hashing,store,audit},
                             #   proto-gen/ (сгенерировано), test/
ml-service/                  # Python: app/{server.py,config.py,proto_gen/,
                             #   dwt/,verification/,encoder/}, tests/, scripts/,
                             #   models/ (веса, в .gitignore), data/ (датасеты)
frontend/                    # React: src/{App.tsx,api/,types/,components/}
deployments/                 # docker-compose.yml, .env.example
docs/                        # ARCHITECTURE v2 (полная), STRUCTURE v2, PROTOCOL,
                             #   MODELS (последние два — пустые заглушки)
scripts/                     # gen_proto.sh, setup_dev.sh — ПУСТЫЕ заглушки
venv/                        # Windows-venv для локальной разработки (в .gitignore)
```

### Заглушки и неиспользуемые файлы (не путайся)

- `ml-service/app/encoder/` (`model.py`, `layers.py`, `train.py`),
  `ml-service/scripts/train.py`, `evaluate.py`, `tests/test_ber.py` —
  пустые файлы-плейсхолдеры Фазы 2.
- `scripts/gen_proto.sh`, `scripts/setup_dev.sh`,
  `ml-service/scripts/generate_proto.sh` — пустые. Реальная регенерация proto:
  `grpcio-tools` для Python; для Go — `protoc-gen-go` через Docker-контейнер
  (на машинах с Device Guard).
- `README.md`, `docs/ARCHITECTURE.md`, `docs/PROTOCOL.md`, `docs/MODELS.md` —
  пустые. Актуальные доки: `docs/STEGO-GUARD_ARCHITECTURE_v2.md`,
  `docs/STEGO-GUARD_STRUCTURE_v2.txt`.
- `frontend/src/pages/HomePage.tsx`, `components/HeatmapViewer.tsx`,
  `components/ModeSwitch.tsx` — пустые; роль этих компонентов выполняют
  `App.tsx` и `ResultCard.tsx`. Единственный экран — `App.tsx`.
- `api-gateway/internal/store/document.go` — заглушка (только `package store`)
  для слоя данных Фазы 4 (PostgreSQL).
- В корне и в `deployments/` лежат тестовые артефакты (`protected.png`,
  `forged.png`, `heatmap.png`, `verify_result.json`, `server.txt`,
  `test_document.png`, `protected2.png`) — они в `.gitignore`, не трогай их
  как «код».

## 4. Сборка и запуск

```bash
# Полный подъём всех трёх сервисов (prod-like)
cd deployments && docker compose up -d --build
# Пересборка одного сервиса / логи / остановка
docker compose up -d --build <service>
docker compose logs <service>
docker compose down
```

Порты: frontend — 80, gateway — 8080, ML — 50051 (только внутри сети).
`deployments/.env.example` — шаблон env для прод-переопределений (локально
значения уже заданы в compose-файле).

### Локальная разработка (без Docker)

- **ml-service**: venv в корне репозитория (`venv/`, Windows). Запуск:
  `python -m app.server` из каталога `ml-service/` (нужны `pywavelets`,
  `opencv-python`, `numpy`, `grpcio` и сгенерированный `app/proto_gen/`).
- **api-gateway**: `go run ./cmd/gateway` из `api-gateway/`
  (нужен `ML_SERVICE_ADDR=localhost:50051`).
- **frontend**: `npm run dev` — Vite на :5173 с прокси `/api → localhost:8080`
  (см. `frontend/vite.config.ts`); в контейнере nginx проксирует `/api` на
  `api-gateway:8080` (`frontend/nginx.conf`).

## 5. Тестирование

```bash
# Python: 11 юнит-тестов (roundtrip, payload, код содержимого, вердикты,
# атаки JPEG q90/q70, ресайз). Синтетические документы генерируются внутри тестов.
cd ml-service && python -m pytest tests/ -v

# Go: тесты магических байт и лимитов
cd api-gateway && go test ./test/

# TypeScript: строгая проверка типов (входит в npm run build)
cd frontend && npx tsc -b

# Сквозной e2e через HTTP-гейтвей (5 проверок: embed→AUTHENTIC,
# подделка→TAMPERED+heatmap, чистый файл→NO_WATERMARK).
# ТРЕБУЕТ запущенных gateway :8080 и ml-service :50051.
# Артефакты пишет в ml-service/data/samples/ (в .gitignore).
cd ml-service && python scripts/e2e_check.py
```

Фронтенд-тестов нет. Проверено: 11/11 pytest зелёные, `go test ./test/` ок,
`tsc -b` чистый.

## 6. Соглашения по коду

- **Язык комментариев, docstrings, логов и UI-текстов — русский.** Соблюдай
  его во всех новых файлах. Сообщения об ошибках в API тоже русские.
- **Go**: стандартный layout (`cmd/`, `internal/`); пакетные doc-комментарии
  начинаются с имени пакета; обработчики получают зависимости через
  `handler.Deps` (config + gRPC-клиент + интерфейс `Auditor`) — через
  интерфейсы, не конкретные типы; конфиг — env-only в `internal/config`.
- **Python**: docstring-стиль Google/NumPy, type hints в сигнатурах, импорты
  сгенерированного proto через `sys.path.insert` в `server.py` (не пакетный
  импорт); генерируемый код в `app/proto_gen/` и `api-gateway/proto-gen/`
  не редактировать руками.
- **TypeScript**: strict (`noUnusedLocals`, `noUnusedParameters`), функциональные
  компоненты, типы ответов API зеркалят JSON гейтвея в `src/types/api.ts`.
- Имена коммитов — conventional commits (`feat(ml-service): …`,
  `docs: …`, `test(e2e): …`).
- Магические числа протокола (пороги, DELTA, формат payload) — только в
  `ml-service/app/config.py` и `app/dwt/payload.py`, не размазывай по коду.

## 7. Безопасность

- Валидация загрузок **по магическим байтам**, не по расширению/Content-Type
  (`api-gateway/internal/validation/file.go`); лимит 25 МБ на обеих сторонах
  (Fiber `BodyLimit` + ручная проверка + `MAX_IMAGE_BYTES` в ML).
- **Перезащита запрещена**: уже защищённый файл отклоняется со статусом
  `EMBED_ERROR_INVALID_IMAGE`.
- gRPC внутри сети без TLS — осознанно (Фаза 1); порт 50051 наружу не
  публикуется. Аутентификация, TLS, rate limiting — Фаза 3.
- Секреты — только в переменных окружения; `.env` и `deployments/.env` в
  `.gitignore`.
- Аудит операций embed/verify: JSON-строки с префиксом `AUDIT ` в stdout
  (`api-gateway/internal/audit/audit.go`) — собираются Docker-логированием.
- Привязка метки к содержимому пороговая (не криптографическая) — это
  задокументированное ограничение Фазы 1, а не баг.
- Формат payload считается частью модели угроз (не публикуется; без кода
  извлечения метку не восстановить) — не выносите детали формата в открытые
  API-ответы.

## 8. Типичные задачи агента

- **Меняешь API?** Сначала `proto/stego.proto`, затем регенерируй оба
  `proto-gen` (см. §3 про способ генерации), затем правь гейтвей и/или
  ML-сервис, затем типы `frontend/src/types/api.ts`. Синхронизируй
  `docs/STEGO-GUARD_*` при изменении архитектуры.
- **Меняешь параметры внедрения/верификации?** Только `ml-service/app/config.py`;
  проверь, что pytest и e2e_check.py остаются зелёными.
- **Добавляешь ML-функциональность Фазы 2?** Точки входа: `app/encoder/`,
  `scripts/generate_dataset.py` (генератор синтетических документов, уже
  работает), `dwt/attacks.py` (атаки для обучения на лету), веса — в
  `ml-service/models/*.pth` (в .gitignore).
