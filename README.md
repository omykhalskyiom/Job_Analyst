# Парсер вакансій з freelancer.com.ua

Скрипт збирає вакансії зі сторінки `https://www.freelancer.com.ua/jobs` та зберігає результат у `CSV` і `JSON`.

## 1) Встановлення

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) Запуск

```powershell
python freelancer_jobs_parser.py --pages 3
```

Після запуску будуть створені файли:

- `freelancer_jobs.csv`
- `freelancer_jobs.json`

У кожному записі є поля:

- `vacancy_url` — пряме посилання на саму вакансію
- `hard_skills` — список навичок/технологій із тегів вакансії
- `search_query` — рядок, за якими ключовими словами виконано пошук
- `search_keywords` — масив ключових слів пошуку
- `search_mode` — режим пошуку (`any` або `all`)
- `search_timestamp` — дата/час запуску парсингу (UTC, ISO 8601)
- `source_pages` — діапазон сторінок, які були оброблені (наприклад `1-3`)

## 3) Корисні параметри

```powershell
python freelancer_jobs_parser.py --pages 5 --csv data/jobs.csv --json data/jobs.json --min-delay 1.5 --max-delay 3.5
```

- `--pages` — скільки сторінок парсити
- `--csv` — шлях до CSV файлу
- `--json` — шлях до JSON файлу
- `--min-delay`, `--max-delay` — пауза між сторінками (сек)

## 4) Фільтрація за ключовими словами

Будь-яке слово (режим `any`, за замовчуванням):

```powershell
python freelancer_jobs_parser.py --pages 3 --keywords python automation telegram
```

Усі слова одночасно (режим `all`):

```powershell
python freelancer_jobs_parser.py --pages 3 --keywords "python, scraping" --keywords-mode all
```

- `--keywords` — ключові слова через пробіл або кому
- `--keywords-mode any` — якщо знайдено хоча б одне слово
- `--keywords-mode all` — якщо знайдено всі слова

## Примітка

Перед запуском перевіряйте актуальні правила сайту (`robots.txt` та ToS).
