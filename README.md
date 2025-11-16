# TV Series Organizer

Автоматическая организация файлов сериалов для Jellyfin с помощью DeepSeek LLM.

![Docker Build](https://github.com/verncat/jellyfin-ai-series-organizer/actions/workflows/docker-publish.yml/badge.svg)

## Возможности

- 🤖 Использует DeepSeek API для интеллектального распознавания структуры сериалов
- 🌐 Веб-интерфейс на Flask с Material Design
-  Автоматически определяет название сериала, сезоны и эпизоды
- 👁️ Показывает предпросмотр структуры перед применением
- 🔗 **Создаёт символические ссылки вместо перемещения файлов** - оригиналы сохраняются
- 💾 Экономия места на диске - файлы физически не дублируются
- 🌍 Работает между разными файловыми системами (разные диски/разделы)
- ↩️ Безопасный откат - просто удаление ссылок, данные не теряются
- 📝 Сохраняет маппинг старых/новых имён в JSON
- 🐳 Docker контейнер с автоматической публикацией в GHCR

## Быстрый старт с Docker

### Docker Run

```bash
# Запуск из GitHub Container Registry
docker run -d \
  -p 9002:9002 \
  -v ./tv:/app/tv \
  -v ./tv_unordered:/app/tv_unordered \
  -e DEEPSEEK_API_KEY=your-api-key \
  ghcr.io/verncat/jellyfin-ai-series-organizer:latest
```

### Docker Compose (рекомендуется)

```bash
# Создайте .env файл
echo "DEEPSEEK_API_KEY=your-api-key" > .env

# Запустите из GHCR
docker-compose -f docker-compose.ghcr.yml up -d

# Или соберите локально
docker-compose up -d
```

Откройте http://localhost:9002

## Установка без Docker

```bash
pip install -r requirements.txt
```

## Использование

### Веб-интерфейс

1. Получите API ключ от DeepSeek: https://platform.deepseek.com/

2. Запустите приложение:

**С Docker Compose:**
```bash
# Создайте .env файл
echo "DEEPSEEK_API_KEY=your-key" > .env

# Запустите
docker-compose up -d
```

**Локально:**
```bash
# Установите зависимости
pip install -r requirements.txt

# Установите API ключ
export DEEPSEEK_API_KEY=your-key  # Linux/Mac
# или
$env:DEEPSEEK_API_KEY = "your-key"  # Windows PowerShell

# Запустите
python app.py
```

3. Откройте http://localhost:9002

4. Выберите папку, просмотрите предложенную структуру и примените изменения

### CLI (консольный интерфейс)

```bash
python organize_series.py
```

## Docker

### Сборка локально

```bash
docker build -t tv-organizer .
docker run -d -p 9002:9002 \
  -v ./tv:/app/tv \
  -v ./tv_unordered:/app/tv_unordered \
  -e DEEPSEEK_API_KEY=your-key \
  tv-organizer
```

### Использование из GHCR

Образы автоматически публикуются в GitHub Container Registry при каждом коммите:

```bash
# Последняя версия
docker pull ghcr.io/verncat/jellyfin-ai-series-organizer:latest

# Конкретная ветка
docker pull ghcr.io/verncat/jellyfin-ai-series-organizer:main

# Конкретный коммит
docker pull ghcr.io/verncat/jellyfin-ai-series-organizer:main-abc1234
```

## GitHub Actions

Проект настроен для автоматической сборки и публикации Docker образа:

- ✅ Триггер на каждый push в main/master
- ✅ Публикация в GitHub Container Registry (ghcr.io)
- ✅ Мультиплатформенная сборка (amd64, arm64)
- ✅ Кэширование слоёв для ускорения
- ✅ Автоматическое тегирование (latest, branch, sha)

## Структура

### Входные данные (tv_unordered/)
```
tv_unordered/
└── Sousou no Frieren/
    ├── Sousou_no_Frieren_[01].mkv
    ├── Sousou_no_Frieren_[02].mkv
    └── ...
```

### Выходные данные (tv/)
```
tv/
└── Sousou no Frieren (2023)/
    └── Season 01/
        ├── Sousou no Frieren S01E01.mkv  ← символическая ссылка
        ├── Sousou no Frieren S01E01.nfo  ← символическая ссылка
        ├── Sousou no Frieren S01E02.mkv  ← символическая ссылка
        └── ...
```

Подробнее: https://jellyfin.org/docs/general/server/media/shows/