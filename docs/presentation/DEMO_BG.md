# Демо на Diff Precision Recall и Percentage Model

## Подготовка

```bash
cd /Users/I551270/Documents/GitHub/code-compare
```

Отвори презентацията:

```text
docs/presentation/diff-precision-recall-vs-percentage-model.pptx
```

## Стъпка 1 Пусни сравнението

```bash
UV_CACHE_DIR=.uv-cache uv run --locked --extra train \
  python -m pr_suggestion_metrics.compare_diff_precision_recall
```

Очакваните основни резултати са:

```text
aggregate Diff P/R: MAE=62.03, within-10=10.0%, dangerous=58.6%
percentage model: MAE=9.74, within-10=74.3%, dangerous=1.4%
```

Кажи: **И двата метода връщат процент от 0 до 100. Aggregate Diff F1 измерва сходството на целия diff, а моделът е много по-близо до референтния процент за запазване на draft-а.**

## Стъпка 2 Покажи реален пример

```bash
UV_CACHE_DIR=.uv-cache uv run --locked --extra train \
  python -m pr_suggestion_metrics.demo_diff_precision_recall
```

Примерът показва:

```text
model percentage: 100%
token: precision=100% recall=61%
file:  precision=100% recall=100%
line:  precision=100% recall=50%
aggregate F1: 81%
```

Обясни разликата така:

- **Precision** пита колко от draft-а е запазено.
- **Recall** пита колко от целия final diff вече е било в draft-а.
- **F1** балансира precision и recall за едно ниво.
- **Aggregate Diff F1** е средното от token F1, file F1 и line F1.
- В примера draft редът е запазен изцяло, затова line precision е 100%.
- Final diff-ът съдържа и премахнатия стар ред, затова line recall е 50%.
- Aggregate F1 е 81%, а моделът и референцията са 100%.

## Стъпка 3 Обясни MAE

Кажи: **MAE е средната абсолютна грешка в процентни точки.**

Прост пример:

```text
Грешки: 5, 10 и 15 точки
MAE = (5 + 10 + 15) / 3 = 10 точки
```

По-ниско MAE е по-добре.

## Стъпка 4 Обясни защо моделът има три части

- **50% Random Forest** — стабилна основа; хваща нелинейни връзки и има най-добрия RMSE сред отделните компоненти.
- **30% two-stage** — първо различава 0, частичен резултат и 100%; има най-добрия резултат в рамките на 5 точки.
- **20% CatBoost MAE** — работи добре с категорийни feature-и и е по-малко чувствителен към outliers; има най-добрия резултат в рамките на 10 точки и няма тежки грешки в теста.
- Теглата са избрани с повторена grouped validation по pull request, не на ръка.

## Стъпка 5 Завърши с решението

- Показваме `model_percentage` като основен резултат.
- Пазим `aggregate_diff_f1` като сравним процент за сходството на целия diff.
- Пазим шестте Diff Precision/Recall стойности за диагностика.
- При голяма разлика между модела и aggregate Diff F1 създаваме сигнал за преглед.
- Преди важно автоматично решение добавяме confidence или abstention.

## Ако командата не тръгне

Покажи готовия отчет:

```text
reports/diff_precision_recall_model_comparison.json
```
